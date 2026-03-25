from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.invoicing.utils import process_overdue_invoice_reminders


class Command(BaseCommand):
    help = "Envoie les relances automatiques de factures en retard (7/14/21/30 jours)."

    def handle(self, *args, **options):
        now = timezone.now()
        count = process_overdue_invoice_reminders(now=now)
        self.stdout.write(self.style.SUCCESS(f"Relances envoyées: {count}"))
