from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import Company, EncryptedTextField


class BankAccount(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="bank_accounts")
    name = models.CharField(max_length=255)
    iban = EncryptedTextField(blank=True, null=True)
    bic = EncryptedTextField(blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)

    initial_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    current_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    is_main = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.name} ({self.company_id})"


class BankTransaction(models.Model):
    class Types(models.TextChoices):
        DEBIT = "DEBIT", "DEBIT"
        CREDIT = "CREDIT", "CREDIT"

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="transactions")
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True, default="")

    amount = models.DecimalField(max_digits=18, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=Types.choices)

    reconciled = models.BooleanField(default=False)
    reconciled_entry = models.ForeignKey(
        "accounting.EntryLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciliations",
    )
    reconciliation_date = models.DateTimeField(null=True, blank=True)

    import_id = models.CharField(max_length=64, blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.bank_account_id} {self.date} {self.transaction_type} {self.amount}"


class CashForecastItem(models.Model):
    class Types(models.TextChoices):
        INCOME = "INCOME", "Encaissement"
        EXPENSE = "EXPENSE", "Décaissement"

    class Recurrence(models.TextChoices):
        MONTHLY = "MONTHLY", "Mensuel"
        QUARTERLY = "QUARTERLY", "Trimestriel"
        YEARLY = "YEARLY", "Annuel"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="cash_forecasts")

    date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    type = models.CharField(max_length=10, choices=Types.choices)
    is_recurring = models.BooleanField(default=False)
    recurrence_period = models.CharField(max_length=20, choices=Recurrence.choices, null=True, blank=True)
    recurrence_end_date = models.DateField(null=True, blank=True)

    category = models.CharField(max_length=255, blank=True, null=True)
    is_actual = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.company_id} {self.date} {self.type} {self.amount}"

