from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class ChartOfAccount(models.Model):
    class Types(models.TextChoices):
        ACTIF = "ACTIF", "ACTIF"
        PASSIF = "PASSIF", "PASSIF"
        CHARGE = "CHARGE", "CHARGE"
        PRODUIT = "PRODUIT", "PRODUIT"

    account_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=Types.choices)
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.account_number} - {self.name}"


class AccountingEntry(models.Model):
    company = models.ForeignKey("core.Company", on_delete=models.CASCADE)
    date = models.DateField()
    description = models.TextField(blank=True, default="")
    reference = models.CharField(max_length=64, blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    validated = models.BooleanField(default=False)
    validation_date = models.DateTimeField(null=True, blank=True)
    validation_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="validated_entries"
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "date"]),
            models.Index(fields=["company", "validated"]),
        ]

    def __str__(self) -> str:
        ref = f" ({self.reference})" if self.reference else ""
        return f"Ecriture {self.date}{ref}"

    def debit_total(self):
        return self.lines.aggregate(total=models.Sum("debit")).get("total") or Decimal("0")

    def credit_total(self):
        return self.lines.aggregate(total=models.Sum("credit")).get("total") or Decimal("0")


class EntryLine(models.Model):
    entry = models.ForeignKey(AccountingEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        indexes = [
            models.Index(fields=["entry"]),
        ]

    def __str__(self) -> str:
        return f"{self.account.account_number} D:{self.debit} C:{self.credit}"

