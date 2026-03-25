from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import Company
from .models import BillingDocumentHistory, DocumentSequence, Invoice, InvoiceLine, Quote


def _bootstrap_next_seq(company: Company, kind: str, year: int) -> int:
    """Prochain indice libre à partir des documents existants (sans verrou de séquence)."""
    prefix = "DEV" if kind == DocumentSequence.Kind.QUOTE else "FAC"
    base = f"{prefix}-{year}-"
    Model = Quote if kind == DocumentSequence.Kind.QUOTE else Invoice
    max_seq = 0
    for num in Model.objects.filter(company=company, number__startswith=base).values_list("number", flat=True):
        try:
            idx = int(str(num).split("-")[-1])
            max_seq = max(max_seq, idx)
        except (ValueError, IndexError):
            continue
    return max_seq + 1


def allocate_next_document_number(company: Company, kind: str) -> str:
    """
    Alloue atomiquement le prochain numéro {DEV|FAC}-{YYYY}-NNNN pour l'entreprise.
    Utilise DocumentSequence + select_for_update pour éviter les doublons.
    """
    year = timezone.now().year
    prefix = "DEV" if kind == DocumentSequence.Kind.QUOTE else "FAC"

    with transaction.atomic():
        seq = (
            DocumentSequence.objects.select_for_update()
            .filter(company=company, kind=kind, year=year)
            .first()
        )
        if seq is None:
            next_idx = _bootstrap_next_seq(company, kind, year)
            seq = DocumentSequence.objects.create(
                company=company,
                kind=kind,
                year=year,
                next_seq=next_idx,
            )
        elif seq.next_seq == 0:
            seq.next_seq = _bootstrap_next_seq(company, kind, year)
            seq.save(update_fields=["next_seq"])

        current = seq.next_seq
        seq.next_seq = current + 1
        seq.save(update_fields=["next_seq"])

    return f"{prefix}-{year}-{current:04d}"


def next_quote_number(company: Company) -> str:
    return allocate_next_document_number(company, DocumentSequence.Kind.QUOTE)


def next_invoice_number(company: Company) -> str:
    return allocate_next_document_number(company, DocumentSequence.Kind.INVOICE)


def snapshot_quote(quote: Quote) -> dict:
    lines = []
    for line in quote.lines.all().order_by("id"):
        lines.append(
            {
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "tax_rate": str(line.tax_rate),
                "amount_ht": str(line.amount_ht),
                "amount_ttc": str(line.amount_ttc),
            }
        )
    return {
        "number": quote.number,
        "date": quote.date.isoformat(),
        "valid_until": quote.valid_until.isoformat(),
        "client_name": quote.client_name,
        "client_email": quote.client_email or "",
        "status": quote.status,
        "total_ht": str(quote.total_ht),
        "total_ttc": str(quote.total_ttc),
        "notes": quote.notes or "",
        "lines": lines,
    }


def snapshot_invoice(invoice: Invoice) -> dict:
    lines = []
    for line in invoice.lines.all().order_by("id"):
        lines.append(
            {
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "tax_rate": str(line.tax_rate),
                "amount_ht": str(line.amount_ht),
                "amount_ttc": str(line.amount_ttc),
            }
        )
    return {
        "number": invoice.number,
        "date": invoice.date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "client_name": invoice.client_name,
        "client_email": invoice.client_email or "",
        "status": invoice.status,
        "total_ht": str(invoice.total_ht),
        "total_ttc": str(invoice.total_ttc),
        "notes": invoice.notes or "",
        "lines": lines,
    }


def log_billing_history(
    *,
    company: Company,
    kind: str,
    document_id: int,
    action: str,
    user,
    snapshot: dict | None = None,
    note: str = "",
) -> BillingDocumentHistory:
    return BillingDocumentHistory.objects.create(
        company=company,
        kind=kind,
        document_id=document_id,
        action=action,
        user=user if user and getattr(user, "is_authenticated", False) else None,
        snapshot=snapshot or {},
        note=note[:500] if note else "",
    )


def recalc_totals_for_quote(quote: Quote) -> None:
    totals = quote.lines.aggregate(total_ht=Sum("amount_ht"), total_ttc=Sum("amount_ttc"))
    quote.total_ht = totals.get("total_ht") or Decimal("0.00")
    quote.total_ttc = totals.get("total_ttc") or Decimal("0.00")
    quote.save(update_fields=["total_ht", "total_ttc"])


def recalc_totals_for_invoice(invoice: Invoice) -> None:
    totals = invoice.lines.aggregate(total_ht=Sum("amount_ht"), total_ttc=Sum("amount_ttc"))
    invoice.total_ht = totals.get("total_ht") or Decimal("0.00")
    invoice.total_ttc = totals.get("total_ttc") or Decimal("0.00")
    invoice.save(update_fields=["total_ht", "total_ttc"])


def send_invoice_reminder(invoice: Invoice) -> None:
    """
    MVP : en dev, on envoie via console backend (EMAIL_BACKEND).
    """
    if not invoice.client_email:
        return

    subject = f"Relance facture {invoice.number}"
    message = f"Bonjour, veuillez régler la facture {invoice.number} (montant TTC: {invoice.total_ttc})."
    send_mail(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=[invoice.client_email],
    )


def process_overdue_invoice_reminders(now=None) -> int:
    """
    Relances automatiques : après 7/14/21/30 jours de retard.
    Retourne le nombre de relances envoyées (MVP).
    """
    if now is None:
        now = timezone.now()

    thresholds = [
        (7, 1),
        (14, 2),
        (21, 3),
        (30, 4),
    ]

    sent = 0
    overdue = Invoice.objects.filter(status__in=[Invoice.Status.SENT, Invoice.Status.OVERDUE]).exclude(due_date__gte=now.date())

    for inv in overdue:
        days_overdue = (now.date() - inv.due_date).days

        # On détermine si on doit envoyer la prochaine relance en fonction du nb déjà envoyé
        for min_days, expected_count in thresholds:
            if days_overdue >= min_days and inv.reminder_count < expected_count:
                send_invoice_reminder(inv)
                inv.reminder_count = expected_count
                inv.last_reminder_at = now
                # MVP : statut OVERDUE dès qu'on est en relance
                inv.status = Invoice.Status.OVERDUE
                inv.save(update_fields=["reminder_count", "last_reminder_at", "status"])
                sent += 1
                break

    return sent

