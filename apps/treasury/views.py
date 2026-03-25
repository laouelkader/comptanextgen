from __future__ import annotations

from urllib.parse import urlencode

from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from django.core.paginator import Paginator
from django.db.models import Sum

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.utils.decorators import method_decorator

from apps.core.decorators import company_required
from apps.core.models import Company
from apps.core.permissions import can_access_treasury_sensitive_operations

from .forms import BankReconciliationForm, CashForecastItemForm, ForecastFilterForm, ImportReconciliationUploadForm
from .models import BankAccount, BankTransaction, CashForecastItem
from .services import (
    import_transactions_from_csv,
    import_transactions_from_excel,
    simulate_bank_transactions,
    suggest_entry_lines_for_transaction,
)


def _cabinet_admin(request: HttpRequest) -> bool:
    return getattr(request.user, "role", None) == "CABINET_ADMIN"


def _resolve_company(request: HttpRequest):
    if _cabinet_admin(request):
        company_name = request.GET.get("company_name") or request.POST.get("company_name")
        if company_name:
            return Company.objects.filter(is_active=True, nom__iexact=company_name.strip()).first()
        company_id = request.GET.get("company_id") or request.POST.get("company_id")
        if not company_id:
            return None
        return get_object_or_404(Company, pk=company_id)
    return getattr(request, "company", None)


def _companies_for_request(request: HttpRequest):
    if _cabinet_admin(request):
        return Company.objects.filter(is_active=True).order_by("nom")
    return None


@method_decorator(company_required, name="dispatch")
class TreasuryDashboardView(LoginRequiredMixin, View):
    template_name = "treasury/treasury_dashboard.html"

    def get(self, request: HttpRequest):
        company = _resolve_company(request)
        accounts = BankAccount.objects.none()
        solde = Decimal("0.00")
        horizon_days = int(request.GET.get("horizon_days") or 90)
        forecasts = CashForecastItem.objects.none()

        if company is not None:
            accounts = BankAccount.objects.filter(company=company).order_by("-is_main", "name")[:5]
            solde = BankAccount.objects.filter(company=company).aggregate(total=Sum("current_balance")).get("total") or Decimal("0.00")
            end_date = timezone.now().date() + timedelta(days=horizon_days)
            forecasts = CashForecastItem.objects.filter(company=company, date__lte=end_date, is_actual=False).order_by("date")[:15]
        elif _cabinet_admin(request):
            messages.info(request, "Sélectionnez une entreprise pour afficher la trésorerie.")

        return render(
            request,
            self.template_name,
            {
                "company": company,
                "accounts": accounts,
                "solde": solde,
                "forecasts": forecasts,
                "horizon_days": horizon_days,
                "company_name": request.GET.get("company_name"),
                "companies": _companies_for_request(request),
            },
        )


@method_decorator(company_required, name="dispatch")
class BankReconciliationView(LoginRequiredMixin, View):
    template_name = "treasury/bank_reconciliation.html"

    def get(self, request: HttpRequest):
        company = _resolve_company(request)
        account_id = request.GET.get("bank_account_id")
        txs = BankTransaction.objects.none()
        accounts_qs = BankAccount.objects.none()

        if company is not None:
            txs = BankTransaction.objects.filter(reconciled=False).order_by("-date")
            if account_id:
                txs = txs.filter(bank_account_id=account_id)
            else:
                txs = txs.filter(bank_account__company=company)
            accounts_qs = BankAccount.objects.filter(company=company).order_by("-is_main", "name")
        elif _cabinet_admin(request):
            messages.info(request, "Sélectionnez une entreprise pour le rapprochement.")

        paginator = Paginator(txs, 25)
        page = int(request.GET.get("page") or 1)
        page_obj = paginator.get_page(page)

        rows_with_suggestions = []
        for t in page_obj.object_list:
            suggs = suggest_entry_lines_for_transaction(t) if company is not None else []
            rows_with_suggestions.append((t, suggs))

        return render(
            request,
            self.template_name,
            {
                "page_obj": page_obj,
                "rows_with_suggestions": rows_with_suggestions,
                "form": BankReconciliationForm(),
                "upload_form": ImportReconciliationUploadForm(),
                "bank_account_id": account_id,
                "accounts": accounts_qs,
                "company_name": request.GET.get("company_name"),
                "company_id": company.pk if company else None,
                "companies": _companies_for_request(request),
            },
        )

    def post(self, request: HttpRequest):
        if not can_access_treasury_sensitive_operations(request.user):
            messages.error(request, "Import et rapprochement réservés au gérant et au comptable.")
            return redirect("treasury:reconciliation")

        company = _resolve_company(request)
        if company is None:
            messages.error(request, "Entreprise introuvable (nom ou ID).")
            return redirect("treasury:reconciliation")

        # Import CSV/XLSX
        if "file" in request.FILES:
            upload_form = ImportReconciliationUploadForm(request.POST, request.FILES)
            if not upload_form.is_valid():
                messages.error(request, "Fichier invalide.")
                return redirect("treasury:reconciliation")

            bank_account_id = request.POST.get("bank_account_id")
            if not bank_account_id:
                messages.error(request, "Sélectionnez un compte bancaire pour l'import.")
                return redirect("treasury:reconciliation")

            bank_account = get_object_or_404(BankAccount, pk=bank_account_id)
            if not _cabinet_admin(request) and bank_account.company_id != company.pk:
                messages.error(request, "Accès refusé.")
                return redirect("treasury:reconciliation")

            f = upload_form.cleaned_data["file"]
            raw = f.read()
            ext = f.name.lower().split(".")[-1] if "." in f.name else ""
            try:
                if ext == "csv":
                    rows = import_transactions_from_csv(raw)
                elif ext in ("xlsx", "xlsm", "xltx", "xltm"):
                    rows = import_transactions_from_excel(raw)
                else:
                    messages.error(request, "Format non supporté. Utilisez CSV ou XLSX.")
                    return redirect("treasury:reconciliation")
            except Exception as exc:
                messages.error(request, f"Import impossible: {exc}")
                return redirect("treasury:reconciliation")

            created = 0
            for r in rows:
                tx_type = r["transaction_type"] if r["transaction_type"] in ("DEBIT", "CREDIT") else "DEBIT"
                BankTransaction.objects.create(
                    bank_account=bank_account,
                    date=r["date"],
                    description=r["description"][:255],
                    amount=r["amount"],
                    transaction_type=tx_type,
                    reconciled=False,
                    import_id=f"import-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                )
                created += 1

            messages.success(request, f"{created} transaction(s) importée(s).")
            if _cabinet_admin(request):
                return redirect(f'{reverse("treasury:reconciliation")}?{urlencode({"company_name": company.nom})}')
            return redirect("treasury:reconciliation")

        # Rapprochement manuel
        form = BankReconciliationForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Formulaire invalide.")
            return redirect("treasury:reconciliation")

        tx = get_object_or_404(BankTransaction, pk=form.cleaned_data["bank_transaction_id"])
        if not _cabinet_admin(request) and tx.bank_account.company_id != company.pk:
            messages.error(request, "Accès refusé.")
            return redirect("treasury:reconciliation")

        tx.reconciled = True
        tx.reconciled_entry_id = form.cleaned_data.get("reconciled_entry_id")
        tx.reconciliation_date = timezone.now()
        tx.save(update_fields=["reconciled", "reconciled_entry_id", "reconciliation_date"])
        messages.success(request, "Transaction rapprochée (MVP).")
        if _cabinet_admin(request):
            return redirect(f'{reverse("treasury:reconciliation")}?company_name={company.nom}')
        return redirect("treasury:reconciliation")


@method_decorator(company_required, name="dispatch")
class CashForecastView(LoginRequiredMixin, View):
    template_name = "treasury/cash_forecast.html"

    def get(self, request: HttpRequest):
        company = _resolve_company(request)
        horizon_days = int(request.GET.get("horizon_days") or 90)
        today = timezone.now().date()
        end_date = today + timedelta(days=horizon_days)

        items = CashForecastItem.objects.none()
        # Courbe : cumul net uniquement sur les lignes dont la date est dans l'horizon (aujourd'hui → +N jours)
        by_date = {}
        if company is not None:
            # Liste tableau : dernières prévisions (toutes dates), sinon une ligne au-delà de l'horizon « disparaît »
            items = CashForecastItem.objects.filter(company=company).order_by("-date")[:50]

            for it in CashForecastItem.objects.filter(company=company, date__lte=end_date).order_by("date"):
                sign = Decimal("1.00") if it.type == CashForecastItem.Types.INCOME else Decimal("-1.00")
                by_date[it.date.isoformat()] = by_date.get(it.date.isoformat(), Decimal("0.00")) + (it.amount * sign)
        elif _cabinet_admin(request):
            messages.info(request, "Sélectionnez une entreprise pour afficher le prévisionnel.")

        dates = sorted(by_date.keys())
        cum = Decimal("0.00")
        series = []
        for d in dates:
            cum += by_date[d]
            series.append(float(cum))

        return render(
            request,
            self.template_name,
            {
                "horizon_days": horizon_days,
                "dates": dates,
                "series": series,
                "items": items,
                "company_name": request.GET.get("company_name"),
                "companies": _companies_for_request(request),
            },
        )

    def _forecast_redirect(self, request: HttpRequest, company: Company | None) -> HttpResponse:
        """Redirect GET avec company_name + horizon (évite perte de contexte après POST)."""
        q = {}
        if company and _cabinet_admin(request):
            q["company_name"] = company.nom
        hd = request.POST.get("horizon_days") or request.GET.get("horizon_days")
        if hd:
            q["horizon_days"] = str(hd)
        if q:
            return redirect(f"{reverse('treasury:forecast')}?{urlencode(q)}")
        return redirect("treasury:forecast")

    def post(self, request: HttpRequest):
        if not can_access_treasury_sensitive_operations(request.user):
            messages.error(request, "La saisie des prévisions est réservée au gérant et au comptable.")
            company = _resolve_company(request)
            return self._forecast_redirect(request, company)

        company = _resolve_company(request)
        if company is None:
            messages.error(
                request,
                "Entreprise introuvable. En tant qu’admin cabinet, sélectionnez une entreprise en haut de page avant d’enregistrer.",
            )
            return self._forecast_redirect(request, None)

        form = CashForecastItemForm(request.POST)
        if not form.is_valid():
            messages.error(request, f"Formulaire invalide : {form.errors.as_text()}")
            return self._forecast_redirect(request, company)

        CashForecastItem.objects.create(
            company=company,
            date=form.cleaned_data["date"],
            description=form.cleaned_data["description"],
            amount=form.cleaned_data["amount"],
            type=form.cleaned_data["type"],
            category=form.cleaned_data.get("category") or None,
        )
        messages.success(request, "Prévision enregistrée.")
        return self._forecast_redirect(request, company)


def simulated_bank_transactions_api(request: HttpRequest, company_id: int):
    """
    Endpoint: GET /api/simulated-bank-transactions/<company_id>/
    MVP : renvoie des données aléatoires.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication requise."}, status=401)

    if not _cabinet_admin(request) and getattr(request.user, "company_id", None) != company_id:
        return JsonResponse({"detail": "Accès refusé."}, status=403)

    txs = simulate_bank_transactions(company_id=company_id, count=20)
    return JsonResponse({"company_id": company_id, "transactions": txs})

