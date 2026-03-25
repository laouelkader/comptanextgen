from __future__ import annotations

from django import forms

from .models import BankTransaction, CashForecastItem


class BankReconciliationForm(forms.Form):
    """
    MVP : on permet de marquer une transaction comme rapprochée.
    """

    bank_transaction_id = forms.IntegerField()
    reconciled_entry_id = forms.IntegerField(required=False)


class ForecastFilterForm(forms.Form):
    horizon_days = forms.IntegerField(min_value=30, max_value=365, required=False, initial=90)


class ImportReconciliationUploadForm(forms.Form):
    file = forms.FileField()


class CashForecastItemForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(max_length=255)
    amount = forms.DecimalField(max_digits=18, decimal_places=2)
    type = forms.ChoiceField(choices=CashForecastItem.Types.choices)
    category = forms.CharField(required=False)

