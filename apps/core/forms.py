import re

from django import forms


class LoginForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput, label="Mot de passe")


class TwoFactorForm(forms.Form):
    code = forms.CharField(label="Code 2FA", max_length=6)

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not re.fullmatch(r"\d{6}", code):
            raise forms.ValidationError("Le code 2FA doit contenir 6 chiffres.")
        return code


class CompanyForm(forms.Form):
    nom = forms.CharField(max_length=255, label="Nom")
    siret = forms.CharField(max_length=30, required=False, label="SIRET")
    iban = forms.CharField(max_length=64, required=False, label="IBAN")
    phone = forms.CharField(max_length=50, required=False, label="Téléphone")
    email = forms.EmailField(required=False, label="Email")
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Adresse")

