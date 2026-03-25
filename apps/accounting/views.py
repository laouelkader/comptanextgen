from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View
from django.utils.decorators import method_decorator

from openpyxl import Workbook

from apps.core.decorators import company_required
from apps.core.models import Company
from apps.core.permissions import can_export_financial_reports, can_validate_accounting_entries

from .forms import AccountingEntryForm, EntryLineFormSet
from .models import AccountingEntry, ChartOfAccount, EntryLine


def _is_cabinet_admin(request: HttpRequest) -> bool:
    return getattr(request.user, "role", None) == "CABINET_ADMIN"


def _get_company_for_scope(request: HttpRequest):
    if _is_cabinet_admin(request):
        return None
    return getattr(request, "company", None)


def _resolve_company_cabinet_scope(request: HttpRequest):
    """
    Pour un utilisateur cabinet : filtre l'entreprise via le nom (prioritaire) ou l'ID (rétrocompatibilité).
    """
    company_name = request.GET.get("company_name") or request.POST.get("company_name")
    if company_name:
        return Company.objects.filter(is_active=True, nom__iexact=company_name.strip()).first()
    company_id = request.GET.get("company_id") or request.POST.get("company_id")
    if company_id:
        return get_object_or_404(Company, pk=company_id)
    return None


def _shift_year(date_obj):
    try:
        return date_obj.replace(year=date_obj.year - 1)
    except ValueError:
        # Cas ex: 29 février
        return date_obj - timedelta(days=365)


def build_financial_statements_context(request: HttpRequest) -> dict:
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    validated_only = request.GET.get("validated_only", "1") == "1"

    company = _get_company_for_scope(request)
    cabinet = _is_cabinet_admin(request)

    if not start_date or not end_date:
        now = timezone.now().date()
        start_date = request.GET.get("start_date") or now.replace(day=1).isoformat()
        end_date = request.GET.get("end_date") or now.isoformat()

    start = timezone.datetime.fromisoformat(start_date).date()
    end = timezone.datetime.fromisoformat(end_date).date()

    prev_start = _shift_year(start)
    prev_end = _shift_year(end)

    base_lines = EntryLine.objects.select_related("entry", "account").filter(entry__date__range=(start, end))
    prev_lines = EntryLine.objects.select_related("entry", "account").filter(entry__date__range=(prev_start, prev_end))

    scope = None
    if cabinet:
        scope = _resolve_company_cabinet_scope(request)
        if scope:
            base_lines = base_lines.filter(entry__company=scope)
            prev_lines = prev_lines.filter(entry__company=scope)
    else:
        base_lines = base_lines.filter(entry__company=company)
        prev_lines = prev_lines.filter(entry__company=company)

    if validated_only:
        base_lines = base_lines.filter(entry__validated=True)
        prev_lines = prev_lines.filter(entry__validated=True)

    def compute_totals(lines):
        totals = {"ACTIF": Decimal("0.00"), "PASSIF": Decimal("0.00"), "CHARGE": Decimal("0.00"), "PRODUIT": Decimal("0.00")}
        for line in lines:
            t = line.account.type
            net_debit_credit = (line.debit or Decimal("0.00")) - (line.credit or Decimal("0.00"))
            if t in ("ACTIF", "CHARGE"):
                totals[t] += net_debit_credit
            else:
                totals[t] += -net_debit_credit  # crédit - débit
        return totals

    totals_n = compute_totals(base_lines)
    totals_n_1 = compute_totals(prev_lines)

    resultat_n = totals_n["PRODUIT"] - totals_n["CHARGE"]
    resultat_n_1 = totals_n_1["PRODUIT"] - totals_n_1["CHARGE"]

    if cabinet:
        report_entity_label = scope.nom if scope else "Consolidé — toutes les sociétés"
    else:
        report_entity_label = company.nom if company else ""

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "prev_start_date": prev_start.isoformat(),
        "prev_end_date": prev_end.isoformat(),
        "start_date_fr": start.strftime("%d/%m/%Y"),
        "end_date_fr": end.strftime("%d/%m/%Y"),
        "prev_start_date_fr": prev_start.strftime("%d/%m/%Y"),
        "prev_end_date_fr": prev_end.strftime("%d/%m/%Y"),
        "validated_only": validated_only,
        "report_entity_label": report_entity_label,
        "company_name": request.GET.get("company_name"),
        "companies": Company.objects.filter(is_active=True).order_by("nom") if cabinet else None,
        "bilan": {
            "actif": totals_n["ACTIF"],
            "passif": totals_n["PASSIF"],
            "actif_prev": totals_n_1["ACTIF"],
            "passif_prev": totals_n_1["PASSIF"],
        },
        "compte_resultat": {
            "charges": totals_n["CHARGE"],
            "produits": totals_n["PRODUIT"],
            "resultat": resultat_n,
            "charges_prev": totals_n_1["CHARGE"],
            "produits_prev": totals_n_1["PRODUIT"],
            "resultat_prev": resultat_n_1,
        },
    }


@method_decorator(company_required, name="dispatch")
class EntryListView(LoginRequiredMixin, View):
    template_name = "accounting/entry_list.html"

    def get(self, request: HttpRequest):
        cabinet = _is_cabinet_admin(request)
        company = getattr(request, "company", None)

        qs = AccountingEntry.objects.select_related("created_by").order_by("-date", "-id")
        if not cabinet:
            qs = qs.filter(company=company)
        else:
            scope = _resolve_company_cabinet_scope(request)
            if scope:
                qs = qs.filter(company=scope)

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        account_number = request.GET.get("account")
        validated = request.GET.get("validated")

        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)
        if validated in ("0", "1"):
            qs = qs.filter(validated=(validated == "1"))
        if account_number:
            qs = qs.filter(lines__account__account_number=account_number).distinct()

        paginator = Paginator(qs, 25)
        page = int(request.GET.get("page") or 1)
        page_obj = paginator.get_page(page)

        ctx = {
            "page_obj": page_obj,
            "start_date": start_date,
            "end_date": end_date,
            "account": account_number,
            "validated": validated,
            "accounts": ChartOfAccount.objects.filter(is_active=True).order_by("account_number")[:50],
            "is_cabinet_admin": cabinet,
            "company_name": request.GET.get("company_name"),
            "companies": Company.objects.filter(is_active=True).order_by("nom") if cabinet else None,
        }
        return render(request, self.template_name, ctx)


@method_decorator(company_required, name="dispatch")
class EntryValidateView(LoginRequiredMixin, View):
    """POST uniquement : valider une écriture (gérant, comptable ou admin cabinet)."""

    def post(self, request: HttpRequest, pk: int):
        if not can_validate_accounting_entries(request.user):
            messages.error(request, "Seuls le gérant et le comptable peuvent valider une écriture.")
            return redirect("accounting:entry_list")

        entry = get_object_or_404(AccountingEntry.objects.select_related("company"), pk=pk)
        cabinet = _is_cabinet_admin(request)
        company = getattr(request, "company", None)

        if cabinet:
            scope = _resolve_company_cabinet_scope(request)
            if scope and entry.company_id != scope.pk:
                messages.error(request, "Écriture hors périmètre entreprise sélectionnée.")
                return redirect("accounting:entry_list")
        else:
            if company is None or entry.company_id != company.pk:
                messages.error(request, "Accès refusé.")
                return redirect("accounting:entry_list")

        if entry.validated:
            messages.info(request, "Cette écriture est déjà validée.")
            return redirect("accounting:entry_list")

        entry.validated = True
        entry.validation_by = request.user
        entry.validation_date = timezone.now()
        entry.save(update_fields=["validated", "validation_by", "validation_date"])
        messages.success(request, "Écriture validée.")
        cn = (request.POST.get("company_name") or "").strip()
        if cabinet and cn:
            return redirect(f"{reverse('accounting:entry_list')}?{urlencode({'company_name': cn})}")
        return redirect("accounting:entry_list")


@method_decorator(company_required, name="dispatch")
class EntryCreateView(LoginRequiredMixin, View):
    template_name = "accounting/entry_form.html"

    def get(self, request: HttpRequest):
        entry_form = AccountingEntryForm()
        formset = EntryLineFormSet(initial=[{}, {}])
        ctx = {
            "entry_form": entry_form,
            "formset": formset,
            "is_cabinet_admin": _is_cabinet_admin(request),
            "companies": None,
            "prefill_company_name": request.GET.get("company_name"),
        }
        if _is_cabinet_admin(request):
            ctx["companies"] = Company.objects.filter(is_active=True).order_by("nom")
        return render(request, self.template_name, ctx)

    def post(self, request: HttpRequest):
        cabinet = _is_cabinet_admin(request)
        company = getattr(request, "company", None)
        company_obj = None
        if cabinet:
            company_obj = _resolve_company_cabinet_scope(request)
            if company_obj is None:
                messages.error(request, "Pour un accès cabinet, sélectionnez une entreprise (nom).")
                return redirect("accounting:entry_add")
        else:
            company_obj = company

        if not cabinet and company is None:
            messages.error(request, "Entreprise introuvable.")
            return redirect("accounting:entry_add")
        entry_form = AccountingEntryForm(request.POST)
        formset = EntryLineFormSet(request.POST)

        if not entry_form.is_valid() or not formset.is_valid():
            messages.error(request, "Vérifiez le formulaire (lignes et champs).")
            ctx = {
                "entry_form": entry_form,
                "formset": formset,
                "is_cabinet_admin": cabinet,
                "companies": Company.objects.filter(is_active=True).order_by("nom") if cabinet else None,
                "prefill_company_name": request.POST.get("company_name"),
            }
            return render(request, self.template_name, ctx)

        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        for f in formset.forms:
            if not f.cleaned_data:
                continue
            if f.cleaned_data.get("__is_empty"):
                continue
            debit = f.cleaned_data.get("debit") or Decimal("0.00")
            credit = f.cleaned_data.get("credit") or Decimal("0.00")
            total_debit += debit
            total_credit += credit

        if total_debit <= 0 and total_credit <= 0:
            messages.error(request, "Ajoutez au moins une ligne avec débit et crédit (écriture non vide).")
            ctx = {
                "entry_form": entry_form,
                "formset": formset,
                "is_cabinet_admin": cabinet,
                "companies": Company.objects.filter(is_active=True).order_by("nom") if cabinet else None,
                "prefill_company_name": request.POST.get("company_name"),
            }
            return render(request, self.template_name, ctx)

        if total_debit.quantize(Decimal("0.01")) != total_credit.quantize(Decimal("0.01")):
            messages.error(request, "Écriture non équilibrée : somme des débits = somme des crédits requise.")
            ctx = {
                "entry_form": entry_form,
                "formset": formset,
                "is_cabinet_admin": cabinet,
                "companies": Company.objects.filter(is_active=True).order_by("nom") if cabinet else None,
                "prefill_company_name": request.POST.get("company_name"),
            }
            return render(request, self.template_name, ctx)

        entry = AccountingEntry.objects.create(
            company=company_obj,
            date=entry_form.cleaned_data["date"],
            description=entry_form.cleaned_data.get("description") or "",
            reference=entry_form.cleaned_data.get("reference") or "",
            created_by=request.user,
            validated=False,
        )

        for f in formset.forms:
            if not f.cleaned_data:
                continue
            if f.cleaned_data.get("__is_empty"):
                continue
            debit = f.cleaned_data.get("debit") or Decimal("0.00")
            credit = f.cleaned_data.get("credit") or Decimal("0.00")
            EntryLine.objects.create(entry=entry, account=f.cleaned_data["account"], debit=debit, credit=credit)

        messages.success(request, "Écriture enregistrée (statut : non validée).")
        return redirect("accounting:entry_list")


@method_decorator(company_required, name="dispatch")
class FinancialStatementsView(LoginRequiredMixin, View):
    template_name = "accounting/financial_statements.html"

    def get(self, request: HttpRequest):
        ctx = build_financial_statements_context(request)
        return render(request, self.template_name, ctx)


@method_decorator(company_required, name="dispatch")
class FinancialStatementsExcelView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest):
        if not can_export_financial_reports(request.user):
            messages.error(request, "Export réservé au gérant et au comptable.")
            return redirect("accounting:statements")
        ctx = build_financial_statements_context(request)

        wb = Workbook()
        ws_bilan = wb.active
        ws_bilan.title = "Bilan"
        ws_bilan.append(["Période", "Actif", "Passif"])
        ws_bilan.append([f'{ctx["start_date"]} -> {ctx["end_date"]}', float(ctx["bilan"]["actif"]), float(ctx["bilan"]["passif"])])
        ws_bilan.append([f'{ctx["prev_start_date"]} -> {ctx["prev_end_date"]}', float(ctx["bilan"]["actif_prev"]), float(ctx["bilan"]["passif_prev"])])

        ws_cr = wb.create_sheet("Compte de résultat")
        ws_cr.append(["Période", "Charges", "Produits", "Résultat"])
        ws_cr.append([
            f'{ctx["start_date"]} -> {ctx["end_date"]}',
            float(ctx["compte_resultat"]["charges"]),
            float(ctx["compte_resultat"]["produits"]),
            float(ctx["compte_resultat"]["resultat"]),
        ])
        ws_cr.append([
            f'{ctx["prev_start_date"]} -> {ctx["prev_end_date"]}',
            float(ctx["compte_resultat"]["charges_prev"]),
            float(ctx["compte_resultat"]["produits_prev"]),
            float(ctx["compte_resultat"]["resultat_prev"]),
        ])

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f'etats_financiers_{ctx["start_date"]}_{ctx["end_date"]}.xlsx'
        response = HttpResponse(
            output.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


@method_decorator(company_required, name="dispatch")
class FinancialStatementsPDFView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest):
        if not can_export_financial_reports(request.user):
            messages.error(request, "Export réservé au gérant et au comptable.")
            return redirect("accounting:statements")
        ctx = build_financial_statements_context(request)
        html = render_to_string("accounting/financial_statements_pdf.html", ctx, request=request)

        try:
            from weasyprint import HTML  # import "lazy" (évite échec au démarrage si libs manquantes)

            pdf_file = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        except Exception:
            return render(request, "accounting/financial_statements_pdf.html", ctx)

        filename = f'etats_financiers_{ctx["start_date"]}_{ctx["end_date"]}.pdf'
        response = HttpResponse(pdf_file, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

