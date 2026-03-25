from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.core.models import Company


class AlertConfig(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="alert_configs")
    treasury_threshold = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    email_enabled = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("company", "is_active")]

    def __str__(self) -> str:
        return f"AlertConfig({self.company_id})"

