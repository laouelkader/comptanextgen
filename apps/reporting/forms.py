from __future__ import annotations

from decimal import Decimal

from django import forms

from .models import AlertConfig


class AlertConfigForm(forms.Form):
    treasury_threshold = forms.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.00"), required=False)
    email_enabled = forms.BooleanField(required=False)

    def clean(self):
        cleaned = super().clean()
        threshold = cleaned.get("treasury_threshold")
        if threshold is None:
            cleaned["treasury_threshold"] = Decimal("0.00")
        cleaned["email_enabled"] = bool(cleaned.get("email_enabled"))
        return cleaned

