from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import Company
from .models import Invoice, InvoiceLine, Quote


def _next_number(company: Company, prefix: str, year: int) -> str:
    """
    Génère un numéro du type {PREFIX}-{YYYY}-XXXX (par entreprise).
    """

    base = f"{prefix}-{year}-"
    last = (
        Quote.objects.filter(company=company, number__startswith=base)
        .values_list("number", flat=True)
        .order_by("-number")
        .first()
    )
    if last is None:
        last_index = 0
    else:
        try:
            last_index = int(last.split("-")[-1])
        except (ValueError, IndexError):
            last_index = 0

    next_index = last_index + 1
    return f"{prefix}-{year}-{next_index:04d}"


def next_quote_number(company: Company) -> str:
    year = timezone.now().year
    prefix = "DEV"
    base = f"{prefix}-{year}-"
    # On s'appuie sur Quote uniquement
    last_number = Quote.objects.filter(company=company, number__startswith=base).order_by("-number").values_list("number", flat=True).first()
    last_index = int(last_number.split("-")[-1]) if last_number else 0
    return f"{prefix}-{year}-{last_index + 1:04d}"


def next_invoice_number(company: Company) -> str:
    year = timezone.now().year
    prefix = "FAC"
    base = f"{prefix}-{year}-"
    last_number = Invoice.objects.filter(company=company, number__startswith=base).order_by("-number").values_list("number", flat=True).first()
    last_index = int(last_number.split("-")[-1]) if last_number else 0
    return f"{prefix}-{year}-{last_index + 1:04d}"


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

