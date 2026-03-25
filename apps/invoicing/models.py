from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import Company, EncryptedTextField


class Quote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SENT = "SENT", "Envoyé"
        ACCEPTED = "ACCEPTED", "Accepté"
        REFUSED = "REFUSED", "Refusé"
        EXPIRED = "EXPIRED", "Expiré"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="quotes")

    number = models.CharField(max_length=30)
    date = models.DateField()
    valid_until = models.DateField()

    client_name = models.CharField(max_length=255)
    client_email = models.EmailField(blank=True, null=True)
    client_address = models.TextField(blank=True, null=True)
    client_siret = EncryptedTextField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    total_ht = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_ttc = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("company", "number")]
        indexes = [models.Index(fields=["company", "date"]), models.Index(fields=["company", "status"])]

    def __str__(self) -> str:
        return f"{self.number} - {self.client_name}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SENT = "SENT", "Envoyée"
        PAID = "PAID", "Payée"
        OVERDUE = "OVERDUE", "En retard"
        CANCELLED = "CANCELLED", "Annulée"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="invoices")

    number = models.CharField(max_length=30)
    date = models.DateField()
    due_date = models.DateField()

    client_name = models.CharField(max_length=255)
    client_email = models.EmailField(blank=True, null=True)
    client_address = models.TextField(blank=True, null=True)
    client_siret = EncryptedTextField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    total_ht = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_ttc = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    paid_at = models.DateTimeField(blank=True, null=True)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)

    reminder_count = models.PositiveIntegerField(default=0)
    last_reminder_at = models.DateTimeField(blank=True, null=True)

    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("company", "number")]
        indexes = [models.Index(fields=["company", "date"]), models.Index(fields=["company", "status"])]

    def __str__(self) -> str:
        return f"{self.number} - {self.client_name}"


class InvoiceLine(models.Model):
    TAX_RATES = [
        (Decimal("20.0"), "20%"),
        (Decimal("10.0"), "10%"),
        (Decimal("5.5"), "5.5%"),
        (Decimal("0.0"), "0%"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, null=True, blank=True, related_name="lines")
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, null=True, blank=True, related_name="lines")

    description = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        default=Decimal("1.00"),
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))], default=Decimal("0.00"))

    tax_rate = models.DecimalField(max_digits=6, decimal_places=2, choices=TAX_RATES, default=Decimal("20.0"))

    amount_ht = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    amount_ttc = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        indexes = [models.Index(fields=["invoice"]), models.Index(fields=["quote"])]

    def clean(self) -> None:
        # MVP : exactement une des 2 liaisons (quote ou invoice)
        if self.invoice and self.quote:
            raise models.ValidationError("Une ligne doit être rattachée soit à un devis, soit à une facture (pas les deux).")
        if not self.invoice and not self.quote:
            raise models.ValidationError("Une ligne doit être rattachée à un devis ou à une facture.")

    def compute_amounts(self) -> None:
        ht = (self.quantity * self.unit_price).quantize(Decimal("0.01"))
        tax_multiplier = (Decimal("1.00") + (self.tax_rate / Decimal("100.00")))
        ttc = (ht * tax_multiplier).quantize(Decimal("0.01"))
        self.amount_ht = ht
        self.amount_ttc = ttc

    def save(self, *args, **kwargs):
        self.compute_amounts()
        self.full_clean(exclude=None)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        parent = "FACT" if self.invoice_id else "DEV"
        return f"{parent} - {self.description}"

