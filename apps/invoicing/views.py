from __future__ import annotations

from urllib.parse import urlencode

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.utils.decorators import method_decorator

from openpyxl import Workbook

from apps.core.decorators import company_required
from apps.core.models import Company
from apps.core.permissions import (
    can_cancel_invoice,
    can_cancel_quote,
    can_convert_quote_to_invoice,
    can_edit_invoice,
    can_edit_quote,
    can_export_invoice_excel,
    is_collaborator,
)

from .forms import InvoiceForm, InvoiceLineFormSet, InvoiceLineForm, QuoteForm
from .models import BillingDocumentHistory, Invoice, InvoiceLine, Quote
from .utils import (
    log_billing_history,
    next_invoice_number,
    next_quote_number,
    process_overdue_invoice_reminders,
    recalc_totals_for_invoice,
    recalc_totals_for_quote,
    snapshot_invoice,
    snapshot_quote,
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


def _can_access_company_document(request: HttpRequest, doc_company_id: int) -> bool:
    if _cabinet_admin(request):
        return True
    company = getattr(request, "company", None)
    return company is not None and company.pk == doc_company_id


def _cabinet_company_query(request: HttpRequest, company: Company) -> str:
    if _cabinet_admin(request):
        return f"?{urlencode({'company_name': company.nom})}"
    return ""


def _base_lines_formset_from_quote(quote: Quote):
    # Pré-remplissage via initial dicts
    initial = []
    for line in quote.lines.all().order_by("id"):
        initial.append(
            {
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "tax_rate": str(line.tax_rate),
            }
        )
    # formset_factory ne permet pas initial_list directement pour chaque POST,
    # donc on passe via kwargs dans le template (MVP).
    return initial


@method_decorator(company_required, name="dispatch")
class QuoteListView(LoginRequiredMixin, View):
    template_name = "invoicing/quote_list.html"

    def get(self, request: HttpRequest):
        company = _resolve_company(request)
        qs = Quote.objects.none()
        if company is not None:
            qs = Quote.objects.filter(company=company).order_by("-date", "-id")
        elif _cabinet_admin(request):
            messages.info(request, "Sélectionnez une entreprise pour afficher les devis.")

        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)

        paginator = Paginator(qs, 25)
        page = int(request.GET.get("page") or 1)
        page_obj = paginator.get_page(page)

        return render(
            request,
            self.template_name,
            {
                "page_obj": page_obj,
                "status": status,
                "company_name": request.GET.get("company_name"),
                "companies": _companies_for_request(request),
            },
        )


@method_decorator(company_required, name="dispatch")
class QuoteCreateView(LoginRequiredMixin, View):
    template_name = "invoicing/quote_form.html"

    def get(self, request: HttpRequest):
        company = _resolve_company(request)

        now = timezone.now().date()
        form = QuoteForm(
            initial={
                "date": now.isoformat(),
                "valid_until": (now + timedelta(days=30)).isoformat(),
            }
        )

        formset = InvoiceLineFormSet(initial=[{"description": "", "quantity": "", "unit_price": "", "tax_rate": "20.0"} for _ in range(2)])

        return render(
            request,
            self.template_name,
            {
                "quote_form": form,
                "formset": formset,
                "company_name": request.GET.get("company_name") or (company.nom if company and _cabinet_admin(request) else ""),
                "companies": _companies_for_request(request),
            },
        )

    def post(self, request: HttpRequest):
        company = _resolve_company(request)
        if company is None:
            messages.error(request, "Entreprise introuvable (nom ou ID).")
            return redirect("invoicing:quote_add")

        quote_form = QuoteForm(request.POST)
        formset = InvoiceLineFormSet(request.POST)
        if not quote_form.is_valid() or not formset.is_valid():
            messages.error(request, "Vérifiez le formulaire (devis/lignes).")
            return render(
                request,
                self.template_name,
                {
                    "quote_form": quote_form,
                    "formset": formset,
                    "company_name": request.POST.get("company_name"),
                    "companies": _companies_for_request(request),
                },
            )

        has_line = any(
            f.cleaned_data and not f.cleaned_data.get("__is_empty") for f in formset.forms
        )
        if not has_line:
            messages.error(request, "Ajoutez au moins une ligne avec description, quantité et prix unitaire.")
            return render(
                request,
                self.template_name,
                {
                    "quote_form": quote_form,
                    "formset": formset,
                    "company_name": request.POST.get("company_name"),
                    "companies": _companies_for_request(request),
                },
            )

        with transaction.atomic():
            quote = Quote.objects.create(
                company=company,
                number=next_quote_number(company),
                date=quote_form.cleaned_data["date"],
                valid_until=quote_form.cleaned_data["valid_until"],
                client_name=quote_form.cleaned_data["client_name"],
                client_email=quote_form.cleaned_data.get("client_email") or None,
                client_address=quote_form.cleaned_data.get("client_address") or None,
                client_siret=quote_form.cleaned_data.get("client_siret") or None,
                status=Quote.Status.DRAFT,
                notes=quote_form.cleaned_data.get("notes") or None,
            )

            for lf in formset.forms:
                if not lf.cleaned_data:
                    continue
                if lf.cleaned_data.get("__is_empty"):
                    continue
                InvoiceLine.objects.create(
                    quote=quote,
                    invoice=None,
                    description=lf.cleaned_data["description"],
                    quantity=lf.cleaned_data["quantity"],
                    unit_price=lf.cleaned_data["unit_price"],
                    tax_rate=lf.cleaned_data["tax_rate"],
                )

            recalc_totals_for_quote(quote)
            log_billing_history(
                company=company,
                kind=BillingDocumentHistory.Kind.QUOTE,
                document_id=quote.pk,
                action=BillingDocumentHistory.Action.CREATED,
                user=request.user,
                snapshot=snapshot_quote(quote),
            )

        messages.success(request, "Devis créé.")
        redirect_url = "invoicing:quote_list"
        if _cabinet_admin(request):
            return redirect(f'{reverse("invoicing:quote_list")}?{urlencode({"company_name": company.nom})}')
        return redirect(redirect_url)


@method_decorator(company_required, name="dispatch")
class QuoteConvertView(LoginRequiredMixin, View):
    template_name = "invoicing/invoice_form.html"

    def post(self, request: HttpRequest, quote_id: int):
        if not can_convert_quote_to_invoice(request.user):
            messages.error(request, "La conversion devis → facture est réservée au gérant et au comptable.")
            return redirect("invoicing:quote_list")

        quote = get_object_or_404(Quote, pk=quote_id)
        company = _resolve_company(request)
        if company is None:
            messages.error(request, "Entreprise introuvable.")
            return redirect("invoicing:invoice_add")

        if not _cabinet_admin(request) and quote.company_id != company.pk:
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:quote_list")

        with transaction.atomic():
            invoice = Invoice.objects.create(
                company=quote.company,
                number=next_invoice_number(quote.company),
                date=timezone.now().date(),
                due_date=quote.valid_until,
                client_name=quote.client_name,
                client_email=quote.client_email,
                client_address=quote.client_address,
                client_siret=quote.client_siret,
                status=Invoice.Status.DRAFT,
                notes=quote.notes,
            )

            for line in quote.lines.all().order_by("id"):
                InvoiceLine.objects.create(
                    invoice=invoice,
                    quote=None,
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                )

            recalc_totals_for_invoice(invoice)
            log_billing_history(
                company=quote.company,
                kind=BillingDocumentHistory.Kind.INVOICE,
                document_id=invoice.pk,
                action=BillingDocumentHistory.Action.CREATED,
                user=request.user,
                snapshot=snapshot_invoice(invoice),
                note=f"Conversion depuis devis {quote.number}",
            )

        messages.success(request, "Devis converti en facture.")
        if _cabinet_admin(request):
            return redirect(f'{reverse("invoicing:invoice_list")}?{urlencode({"company_name": quote.company.nom})}')
        return redirect("invoicing:invoice_list")

    # GET : fallback pour sécurité
    def get(self, request: HttpRequest, quote_id: int):
        # MVP : conversion via POST seulement
        messages.info(request, "Conversion devis->facture : utilisez l'action du bouton.")
        return redirect("invoicing:quote_list")


@method_decorator(company_required, name="dispatch")
class InvoiceListView(LoginRequiredMixin, View):
    template_name = "invoicing/invoice_list.html"

    def get(self, request: HttpRequest):
        company = _resolve_company(request)
        qs = Invoice.objects.none()
        if company is not None:
            qs = Invoice.objects.filter(company=company).order_by("-date", "-id")
        elif _cabinet_admin(request):
            messages.info(request, "Sélectionnez une entreprise pour afficher les factures.")

        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)

        paginator = Paginator(qs, 25)
        page = int(request.GET.get("page") or 1)
        page_obj = paginator.get_page(page)

        return render(
            request,
            self.template_name,
            {
                "page_obj": page_obj,
                "status": status,
                "company_name": request.GET.get("company_name"),
                "companies": _companies_for_request(request),
            },
        )


@method_decorator(company_required, name="dispatch")
class InvoiceCreateView(LoginRequiredMixin, View):
    template_name = "invoicing/invoice_form.html"

    def get(self, request: HttpRequest):
        company = _resolve_company(request)

        now = timezone.now().date()
        form = InvoiceForm(
            initial={
                "date": now.isoformat(),
                "due_date": (now + timedelta(days=30)).isoformat(),
            }
        )

        formset = InvoiceLineFormSet(initial=[{"description": "", "quantity": "", "unit_price": "", "tax_rate": "20.0"} for _ in range(2)])

        return render(
            request,
            self.template_name,
            {
                "invoice_form": form,
                "formset": formset,
                "company_name": request.GET.get("company_name") or (company.nom if company and _cabinet_admin(request) else ""),
                "companies": _companies_for_request(request),
            },
        )

    def post(self, request: HttpRequest):
        company = _resolve_company(request)
        if company is None:
            messages.error(request, "Entreprise introuvable (nom ou ID).")
            return redirect("invoicing:invoice_add")

        invoice_form = InvoiceForm(request.POST)
        formset = InvoiceLineFormSet(request.POST)
        if not invoice_form.is_valid() or not formset.is_valid():
            messages.error(request, "Vérifiez le formulaire (facture/lignes).")
            return render(
                request,
                self.template_name,
                {
                    "invoice_form": invoice_form,
                    "formset": formset,
                    "company_name": request.POST.get("company_name"),
                    "companies": _companies_for_request(request),
                },
            )

        has_line = any(
            f.cleaned_data and not f.cleaned_data.get("__is_empty") for f in formset.forms
        )
        if not has_line:
            messages.error(request, "Ajoutez au moins une ligne avec description, quantité et prix unitaire.")
            return render(
                request,
                self.template_name,
                {
                    "invoice_form": invoice_form,
                    "formset": formset,
                    "company_name": request.POST.get("company_name"),
                    "companies": _companies_for_request(request),
                },
            )

        with transaction.atomic():
            invoice = Invoice.objects.create(
                company=company,
                number=next_invoice_number(company),
                date=invoice_form.cleaned_data["date"],
                due_date=invoice_form.cleaned_data["due_date"],
                client_name=invoice_form.cleaned_data["client_name"],
                client_email=invoice_form.cleaned_data.get("client_email") or None,
                client_address=invoice_form.cleaned_data.get("client_address") or None,
                client_siret=invoice_form.cleaned_data.get("client_siret") or None,
                status=Invoice.Status.DRAFT,
                notes=invoice_form.cleaned_data.get("notes") or None,
            )

            for lf in formset.forms:
                if not lf.cleaned_data:
                    continue
                if lf.cleaned_data.get("__is_empty"):
                    continue
                InvoiceLine.objects.create(
                    invoice=invoice,
                    quote=None,
                    description=lf.cleaned_data["description"],
                    quantity=lf.cleaned_data["quantity"],
                    unit_price=lf.cleaned_data["unit_price"],
                    tax_rate=lf.cleaned_data["tax_rate"],
                )

            recalc_totals_for_invoice(invoice)
            log_billing_history(
                company=company,
                kind=BillingDocumentHistory.Kind.INVOICE,
                document_id=invoice.pk,
                action=BillingDocumentHistory.Action.CREATED,
                user=request.user,
                snapshot=snapshot_invoice(invoice),
            )

        messages.success(request, "Facture créée.")
        if _cabinet_admin(request):
            return redirect(f'{reverse("invoicing:invoice_list")}?{urlencode({"company_name": company.nom})}')
        return redirect("invoicing:invoice_list")


@method_decorator(company_required, name="dispatch")
class InvoicePDFView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, invoice_id: int):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        # Cabinet : accès à toute facture (ne pas dépendre de ?company_name= pour le PDF).
        if _cabinet_admin(request):
            pass
        else:
            company = getattr(request.user, "company", None)
            if company is None or invoice.company_id != company.pk:
                messages.error(request, "Accès refusé.")
                return redirect("invoicing:invoice_list")

        ctx = {
            "invoice": invoice,
            "lines": invoice.lines.all().order_by("id"),
            "invoice_date_fr": invoice.date.strftime("%d/%m/%Y"),
            "due_date_fr": invoice.due_date.strftime("%d/%m/%Y"),
        }
        html = render_to_string("invoicing/invoice_pdf.html", ctx, request=request)

        try:
            from weasyprint import HTML as WeasyHTML  # import lazy

            pdf_file = WeasyHTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        except Exception:
            return render(request, "invoicing/invoice_pdf.html", ctx)

        filename = f"{invoice.number}.pdf"
        resp = HttpResponse(pdf_file, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


@method_decorator(company_required, name="dispatch")
class InvoiceExcelExportView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest):
        if not can_export_invoice_excel(request.user):
            messages.error(request, "Export Excel réservé au gérant et au comptable.")
            return redirect("invoicing:invoice_list")
        company = _resolve_company(request)
        if company is None:
            messages.error(request, "Entreprise introuvable.")
            return redirect("invoicing:invoice_list")

        qs = Invoice.objects.filter(company=company).order_by("-date", "-id")

        wb = Workbook()
        ws = wb.active
        ws.title = "Factures"
        ws.append(["Numéro", "Date", "Échéance", "Client", "Statut", "Total HT", "Total TTC"])
        for inv in qs[:500]:
            ws.append([inv.number, inv.date.isoformat(), inv.due_date.isoformat(), inv.client_name, inv.get_status_display(), float(inv.total_ht), float(inv.total_ttc)])

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        resp = HttpResponse(output.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = 'attachment; filename="invoices.xlsx"'
        return resp


@method_decorator(company_required, name="dispatch")
class QuoteEditView(LoginRequiredMixin, View):
    template_name = "invoicing/quote_form.html"

    def get(self, request: HttpRequest, quote_id: int):
        quote = get_object_or_404(Quote, pk=quote_id)
        if not _can_access_company_document(request, quote.company_id):
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:quote_list")
        if not can_edit_quote(request.user, quote):
            messages.error(request, "Modification non autorisée pour ce devis.")
            return redirect("invoicing:quote_list")

        form = QuoteForm(
            initial={
                "date": quote.date,
                "valid_until": quote.valid_until,
                "client_name": quote.client_name,
                "client_email": quote.client_email or "",
                "client_address": quote.client_address or "",
                "client_siret": quote.client_siret or "",
                "status": quote.status,
                "notes": quote.notes or "",
            }
        )
        initial_lines = _base_lines_formset_from_quote(quote)
        formset = InvoiceLineFormSet(initial=initial_lines)

        return render(
            request,
            self.template_name,
            {
                "quote_form": form,
                "formset": formset,
                "edit_mode": True,
                "quote": quote,
                "company_name": request.GET.get("company_name") or (quote.company.nom if _cabinet_admin(request) else ""),
                "companies": _companies_for_request(request),
            },
        )

    def post(self, request: HttpRequest, quote_id: int):
        quote = get_object_or_404(Quote, pk=quote_id)
        if not _can_access_company_document(request, quote.company_id):
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:quote_list")
        if not can_edit_quote(request.user, quote):
            messages.error(request, "Modification non autorisée pour ce devis.")
            return redirect("invoicing:quote_list")

        quote_form = QuoteForm(request.POST)
        formset = InvoiceLineFormSet(request.POST)
        if not quote_form.is_valid() or not formset.is_valid():
            messages.error(request, "Vérifiez le formulaire (devis/lignes).")
            return render(
                request,
                self.template_name,
                {
                    "quote_form": quote_form,
                    "formset": formset,
                    "edit_mode": True,
                    "quote": quote,
                    "company_name": request.POST.get("company_name"),
                    "companies": _companies_for_request(request),
                },
            )

        has_line = any(
            f.cleaned_data and not f.cleaned_data.get("__is_empty") for f in formset.forms
        )
        if not has_line:
            messages.error(request, "Ajoutez au moins une ligne avec description, quantité et prix unitaire.")
            return render(
                request,
                self.template_name,
                {
                    "quote_form": quote_form,
                    "formset": formset,
                    "edit_mode": True,
                    "quote": quote,
                    "company_name": request.POST.get("company_name"),
                    "companies": _companies_for_request(request),
                },
            )

        new_status = quote_form.cleaned_data.get("status") or quote.status
        if is_collaborator(request.user):
            new_status = Quote.Status.DRAFT

        with transaction.atomic():
            quote.date = quote_form.cleaned_data["date"]
            quote.valid_until = quote_form.cleaned_data["valid_until"]
            quote.client_name = quote_form.cleaned_data["client_name"]
            quote.client_email = quote_form.cleaned_data.get("client_email") or None
            quote.client_address = quote_form.cleaned_data.get("client_address") or None
            quote.client_siret = quote_form.cleaned_data.get("client_siret") or None
            quote.status = new_status
            quote.notes = quote_form.cleaned_data.get("notes") or None
            quote.save()

            quote.lines.all().delete()
            for lf in formset.forms:
                if not lf.cleaned_data:
                    continue
                if lf.cleaned_data.get("__is_empty"):
                    continue
                InvoiceLine.objects.create(
                    quote=quote,
                    invoice=None,
                    description=lf.cleaned_data["description"],
                    quantity=lf.cleaned_data["quantity"],
                    unit_price=lf.cleaned_data["unit_price"],
                    tax_rate=lf.cleaned_data["tax_rate"],
                )

            recalc_totals_for_quote(quote)
            log_billing_history(
                company=quote.company,
                kind=BillingDocumentHistory.Kind.QUOTE,
                document_id=quote.pk,
                action=BillingDocumentHistory.Action.UPDATED,
                user=request.user,
                snapshot=snapshot_quote(quote),
            )

        messages.success(request, "Devis enregistré.")
        if _cabinet_admin(request):
            return redirect(f'{reverse("invoicing:quote_list")}?{urlencode({"company_name": quote.company.nom})}')
        return redirect("invoicing:quote_list")


@method_decorator(company_required, name="dispatch")
class QuoteCancelView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, quote_id: int):
        quote = get_object_or_404(Quote, pk=quote_id)
        if not _can_access_company_document(request, quote.company_id):
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:quote_list")
        if not can_cancel_quote(request.user, quote):
            messages.error(request, "Annulation non autorisée (statut ou droits).")
            return redirect("invoicing:quote_list")

        with transaction.atomic():
            quote.status = Quote.Status.CANCELLED
            quote.save(update_fields=["status"])
            log_billing_history(
                company=quote.company,
                kind=BillingDocumentHistory.Kind.QUOTE,
                document_id=quote.pk,
                action=BillingDocumentHistory.Action.CANCELLED,
                user=request.user,
                snapshot=snapshot_quote(quote),
            )

        messages.success(request, "Devis annulé.")
        if _cabinet_admin(request):
            return redirect(f'{reverse("invoicing:quote_list")}?{urlencode({"company_name": quote.company.nom})}')
        return redirect("invoicing:quote_list")


@method_decorator(company_required, name="dispatch")
class QuoteHistoryView(LoginRequiredMixin, View):
    template_name = "invoicing/billing_history.html"

    def get(self, request: HttpRequest, quote_id: int):
        quote = get_object_or_404(Quote, pk=quote_id)
        if not _can_access_company_document(request, quote.company_id):
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:quote_list")

        entries = BillingDocumentHistory.objects.filter(
            company_id=quote.company_id,
            kind=BillingDocumentHistory.Kind.QUOTE,
            document_id=quote.pk,
        )
        return render(
            request,
            self.template_name,
            {
                "document_kind_label": "Devis",
                "document_ref": quote.number,
                "entries": entries,
                "company_name": request.GET.get("company_name") or (quote.company.nom if _cabinet_admin(request) else ""),
                "companies": _companies_for_request(request),
                "back_url": reverse("invoicing:quote_list") + _cabinet_company_query(request, quote.company),
            },
        )


@method_decorator(company_required, name="dispatch")
class InvoiceEditView(LoginRequiredMixin, View):
    template_name = "invoicing/invoice_form.html"

    def get(self, request: HttpRequest, invoice_id: int):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        if not _can_access_company_document(request, invoice.company_id):
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:invoice_list")
        if not can_edit_invoice(request.user, invoice):
            messages.error(request, "Modification non autorisée pour cette facture.")
            return redirect("invoicing:invoice_list")

        initial_lines = []
        for line in invoice.lines.all().order_by("id"):
            initial_lines.append(
                {
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "tax_rate": str(line.tax_rate),
                }
            )
        form = InvoiceForm(
            initial={
                "date": invoice.date,
                "due_date": invoice.due_date,
                "client_name": invoice.client_name,
                "client_email": invoice.client_email or "",
                "client_address": invoice.client_address or "",
                "client_siret": invoice.client_siret or "",
                "status": invoice.status,
                "notes": invoice.notes or "",
            }
        )
        formset = InvoiceLineFormSet(initial=initial_lines)

        return render(
            request,
            self.template_name,
            {
                "invoice_form": form,
                "formset": formset,
                "edit_mode": True,
                "invoice": invoice,
                "company_name": request.GET.get("company_name") or (invoice.company.nom if _cabinet_admin(request) else ""),
                "companies": _companies_for_request(request),
            },
        )

    def post(self, request: HttpRequest, invoice_id: int):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        if not _can_access_company_document(request, invoice.company_id):
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:invoice_list")
        if not can_edit_invoice(request.user, invoice):
            messages.error(request, "Modification non autorisée pour cette facture.")
            return redirect("invoicing:invoice_list")

        invoice_form = InvoiceForm(request.POST)
        formset = InvoiceLineFormSet(request.POST)
        if not invoice_form.is_valid() or not formset.is_valid():
            messages.error(request, "Vérifiez le formulaire (facture/lignes).")
            return render(
                request,
                self.template_name,
                {
                    "invoice_form": invoice_form,
                    "formset": formset,
                    "edit_mode": True,
                    "invoice": invoice,
                    "company_name": request.POST.get("company_name"),
                    "companies": _companies_for_request(request),
                },
            )

        has_line = any(
            f.cleaned_data and not f.cleaned_data.get("__is_empty") for f in formset.forms
        )
        if not has_line:
            messages.error(request, "Ajoutez au moins une ligne avec description, quantité et prix unitaire.")
            return render(
                request,
                self.template_name,
                {
                    "invoice_form": invoice_form,
                    "formset": formset,
                    "edit_mode": True,
                    "invoice": invoice,
                    "company_name": request.POST.get("company_name"),
                    "companies": _companies_for_request(request),
                },
            )

        new_status = invoice_form.cleaned_data.get("status") or invoice.status
        if is_collaborator(request.user):
            new_status = invoice.status

        with transaction.atomic():
            invoice.date = invoice_form.cleaned_data["date"]
            invoice.due_date = invoice_form.cleaned_data["due_date"]
            invoice.client_name = invoice_form.cleaned_data["client_name"]
            invoice.client_email = invoice_form.cleaned_data.get("client_email") or None
            invoice.client_address = invoice_form.cleaned_data.get("client_address") or None
            invoice.client_siret = invoice_form.cleaned_data.get("client_siret") or None
            invoice.status = new_status
            invoice.notes = invoice_form.cleaned_data.get("notes") or None
            invoice.save()

            invoice.lines.all().delete()
            for lf in formset.forms:
                if not lf.cleaned_data:
                    continue
                if lf.cleaned_data.get("__is_empty"):
                    continue
                InvoiceLine.objects.create(
                    invoice=invoice,
                    quote=None,
                    description=lf.cleaned_data["description"],
                    quantity=lf.cleaned_data["quantity"],
                    unit_price=lf.cleaned_data["unit_price"],
                    tax_rate=lf.cleaned_data["tax_rate"],
                )

            recalc_totals_for_invoice(invoice)
            log_billing_history(
                company=invoice.company,
                kind=BillingDocumentHistory.Kind.INVOICE,
                document_id=invoice.pk,
                action=BillingDocumentHistory.Action.UPDATED,
                user=request.user,
                snapshot=snapshot_invoice(invoice),
            )

        messages.success(request, "Facture enregistrée.")
        if _cabinet_admin(request):
            return redirect(f'{reverse("invoicing:invoice_list")}?{urlencode({"company_name": invoice.company.nom})}')
        return redirect("invoicing:invoice_list")


@method_decorator(company_required, name="dispatch")
class InvoiceCancelView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, invoice_id: int):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        if not _can_access_company_document(request, invoice.company_id):
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:invoice_list")
        if not can_cancel_invoice(request.user, invoice):
            messages.error(request, "Annulation non autorisée (statut ou droits).")
            return redirect("invoicing:invoice_list")

        with transaction.atomic():
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=["status"])
            log_billing_history(
                company=invoice.company,
                kind=BillingDocumentHistory.Kind.INVOICE,
                document_id=invoice.pk,
                action=BillingDocumentHistory.Action.CANCELLED,
                user=request.user,
                snapshot=snapshot_invoice(invoice),
            )

        messages.success(request, "Facture annulée.")
        if _cabinet_admin(request):
            return redirect(f'{reverse("invoicing:invoice_list")}?{urlencode({"company_name": invoice.company.nom})}')
        return redirect("invoicing:invoice_list")


@method_decorator(company_required, name="dispatch")
class InvoiceHistoryView(LoginRequiredMixin, View):
    template_name = "invoicing/billing_history.html"

    def get(self, request: HttpRequest, invoice_id: int):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        if not _can_access_company_document(request, invoice.company_id):
            messages.error(request, "Accès refusé.")
            return redirect("invoicing:invoice_list")

        entries = BillingDocumentHistory.objects.filter(
            company_id=invoice.company_id,
            kind=BillingDocumentHistory.Kind.INVOICE,
            document_id=invoice.pk,
        )
        return render(
            request,
            self.template_name,
            {
                "document_kind_label": "Facture",
                "document_ref": invoice.number,
                "entries": entries,
                "company_name": request.GET.get("company_name") or (invoice.company.nom if _cabinet_admin(request) else ""),
                "companies": _companies_for_request(request),
                "back_url": reverse("invoicing:invoice_list") + _cabinet_company_query(request, invoice.company),
            },
        )
