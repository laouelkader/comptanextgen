from __future__ import annotations

from decimal import Decimal

from django import forms
from django.forms import formset_factory

from .models import ChartOfAccount, EntryLine


class AccountingEntryForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    reference = forms.CharField(required=False, max_length=64)


class EntryLineForm(forms.Form):
    _cls = "mt-1 w-full border rounded px-3 py-2 text-sm"
    account = forms.ModelChoiceField(
        queryset=ChartOfAccount.objects.filter(is_active=True).order_by("account_number"),
        required=False,
        empty_label="—",
        widget=forms.Select(attrs={"class": _cls}),
    )
    debit = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
        widget=forms.TextInput(attrs={"class": _cls, "inputmode": "decimal"}),
    )
    credit = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
        widget=forms.TextInput(attrs={"class": _cls, "inputmode": "decimal"}),
    )

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get("account")
        debit = cleaned.get("debit") or Decimal("0.00")
        credit = cleaned.get("credit") or Decimal("0.00")

        # Ligne vide (compte non choisi et montants nuls) : ignorée au traitement
        if not account and debit <= 0 and credit <= 0:
            cleaned["__is_empty"] = True
            return cleaned

        if not account:
            raise forms.ValidationError("Sélectionnez un compte pour cette ligne.")
        if debit <= 0 and credit <= 0:
            raise forms.ValidationError("Chaque ligne doit avoir un débit ou un crédit non nul.")
        if debit > 0 and credit > 0:
            raise forms.ValidationError("Une ligne ne peut pas avoir à la fois débit et crédit.")
        cleaned["__is_empty"] = False
        return cleaned


# 2 lignes par défaut + ajout dynamique (TOTAL_FORMS) ; min_num=0 car les lignes vides sont autorisées.
EntryLineFormSet = formset_factory(EntryLineForm, extra=0, min_num=0, validate_min=False)

