from __future__ import annotations

from decimal import Decimal

from django import forms
from django.forms import formset_factory

from .models import InvoiceLine, Quote, Invoice


class QuoteForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    valid_until = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    client_name = forms.CharField(max_length=255)
    client_email = forms.EmailField(required=False)
    client_address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    client_siret = forms.CharField(required=False)

    status = forms.ChoiceField(choices=[(v, v) for v, _ in Quote.Status.choices], required=False)

    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class InvoiceForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    due_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    client_name = forms.CharField(max_length=255)
    client_email = forms.EmailField(required=False)
    client_address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    client_siret = forms.CharField(required=False)

    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class InvoiceLineForm(forms.Form):
    # Non obligatoire au niveau HTML : une ligne vide est ignorée (sinon le formset est invalide
    # dès qu’on remplit seulement la 2e ligne, et la facture « disparaît » au submit).
    _cls = "mt-1 w-full border rounded px-3 py-2 text-sm"
    description = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": _cls}))
    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        widget=forms.TextInput(attrs={"class": _cls, "inputmode": "decimal"}),
    )
    unit_price = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        widget=forms.TextInput(attrs={"class": _cls, "inputmode": "decimal"}),
    )
    tax_rate = forms.ChoiceField(
        choices=[("20.0", "20%"), ("10.0", "10%"), ("5.5", "5.5%"), ("0.0", "0%")],
        required=False,
        widget=forms.Select(attrs={"class": _cls}),
    )

    def clean(self):
        cleaned = super().clean()

        desc = (cleaned.get("description") or "").strip()
        qty = cleaned.get("quantity") or Decimal("0.00")
        unit = cleaned.get("unit_price") or Decimal("0.00")
        tax_raw = cleaned.get("tax_rate") or "20.0"
        tax = Decimal(str(tax_raw))

        # MVP : ligne vide => ignorée
        if not desc and qty == 0 and unit == 0:
            cleaned["__is_empty"] = True
            return cleaned

        if not desc:
            raise forms.ValidationError("La description est obligatoire si la ligne n'est pas vide.")

        cleaned["__is_empty"] = False
        cleaned["quantity"] = qty
        cleaned["unit_price"] = unit
        cleaned["tax_rate"] = tax
        cleaned["amount_ht"] = (qty * unit).quantize(Decimal("0.01"))
        cleaned["amount_ttc"] = (cleaned["amount_ht"] * (Decimal("1.00") + tax / Decimal("100.00"))).quantize(Decimal("0.01"))
        return cleaned


# extra=0 : le nombre de lignes = celui affiché (2 par défaut) + lignes ajoutées en JS (TOTAL_FORMS).
InvoiceLineFormSet = formset_factory(InvoiceLineForm, extra=0, min_num=0, validate_min=False)

