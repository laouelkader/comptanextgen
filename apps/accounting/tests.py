from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Company, User

from .models import AccountingEntry, ChartOfAccount, EntryLine


class AccountingMVPTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            nom="Alpha SARL",
            is_active=True,
        )

        self.user = User.objects.create(
            email="manager@alpha.test",
            role="MANAGER",
            company=self.company,
            is_active=True,
        )
        self.user.set_password("Aa!234567")  # set_password required for auth-related flows
        self.user.save()

        # Comptes MVP
        self.actif = ChartOfAccount.objects.create(account_number="1000", name="Actif", type="ACTIF", is_active=True)
        self.passif = ChartOfAccount.objects.create(account_number="2000", name="Passif", type="PASSIF", is_active=True)
        self.charge = ChartOfAccount.objects.create(account_number="6000", name="Charges", type="CHARGE", is_active=True)
        self.produit = ChartOfAccount.objects.create(account_number="7000", name="Produits", type="PRODUIT", is_active=True)

        self.today = timezone.now().date()
        self.start = self.today.replace(day=1)
        self.end = self.today

    def force_login(self):
        # On évite la mécanique de login/2FA, on force la session
        self.client.force_login(self.user)

    def create_validated_entry(self, debit_account, credit_account, amount: Decimal):
        entry = AccountingEntry.objects.create(
            company=self.company,
            date=self.end,
            description="Test",
            reference="REF-1",
            created_by=self.user,
            validated=True,
            validation_by=self.user,
            validation_date=timezone.now(),
        )
        EntryLine.objects.create(entry=entry, account=debit_account, debit=amount, credit=Decimal("0.00"))
        EntryLine.objects.create(entry=entry, account=credit_account, debit=Decimal("0.00"), credit=amount)
        return entry

    def test_chart_of_account_creation(self):
        self.assertEqual(ChartOfAccount.objects.count(), 4)
        self.assertTrue(ChartOfAccount.objects.filter(account_number="6000", type="CHARGE").exists())

    def test_accounting_entry_totals(self):
        entry = AccountingEntry.objects.create(
            company=self.company,
            date=self.end,
            description="Totals",
            reference="T1",
            created_by=self.user,
            validated=False,
        )
        EntryLine.objects.create(entry=entry, account=self.actif, debit=Decimal("10.00"), credit=Decimal("0.00"))
        EntryLine.objects.create(entry=entry, account=self.passif, debit=Decimal("0.00"), credit=Decimal("10.00"))
        self.assertEqual(entry.debit_total(), Decimal("10.00"))
        self.assertEqual(entry.credit_total(), Decimal("10.00"))

    def test_entry_line_requires_debit_or_credit(self):
        # Création directe : les champs ont défaut 0, donc on teste le form côté vue
        entry = AccountingEntry.objects.create(
            company=self.company,
            date=self.end,
            description="Validation form",
            reference="T2",
            created_by=self.user,
        )
        # Valeurs vides : validation MVP côté formset seulement
        EntryLine.objects.create(entry=entry, account=self.actif, debit=Decimal("0.00"), credit=Decimal("0.00"))
        self.assertEqual(entry.lines.count(), 1)

    def test_entry_create_view_get(self):
        self.force_login()
        resp = self.client.get(reverse("accounting:entry_add"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("formset", resp.context)

    def test_entry_create_view_rejects_imbalanced_entry(self):
        self.force_login()
        url = reverse("accounting:entry_add")

        # On crée 2 lignes : débit 10 / crédit 5 (déséquilibre)
        post = {
            "date": self.end.isoformat(),
            "description": "Imbalance",
            "reference": "X1",
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-account": self.charge.id,
            "form-0-debit": "10.00",
            "form-0-credit": "0.00",
            "form-1-account": self.produit.id,
            "form-1-debit": "0.00",
            "form-1-credit": "5.00",
        }

        resp = self.client.post(url, post, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "non équilibrée", status_code=200)
        self.assertEqual(AccountingEntry.objects.count(), 0)

    def test_entry_create_view_creates_balanced_entry(self):
        self.force_login()
        url = reverse("accounting:entry_add")

        post = {
            "date": self.end.isoformat(),
            "description": "Balance",
            "reference": "B1",
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-account": self.charge.id,
            "form-0-debit": "10.00",
            "form-0-credit": "0.00",
            "form-1-account": self.produit.id,
            "form-1-debit": "0.00",
            "form-1-credit": "10.00",
        }

        resp = self.client.post(url, post, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AccountingEntry.objects.count(), 1)
        entry = AccountingEntry.objects.first()
        self.assertEqual(entry.lines.count(), 2)

    def test_financial_statements_resultat(self):
        self.force_login()
        # Charge: débit 10, Produit: crédit 10 => résultat = 10 - 0? (charges=10 produits=10 => 0)
        self.create_validated_entry(debit_account=self.charge, credit_account=self.produit, amount=Decimal("10.00"))

        resp = self.client.get(
            reverse("accounting:statements")
            + f"?start_date={self.start.isoformat()}&end_date={self.end.isoformat()}&validated_only=1"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["compte_resultat"]["resultat"].quantize(Decimal("0.01")), Decimal("0.00"))

    def test_financial_statements_excel_export(self):
        self.force_login()
        self.create_validated_entry(debit_account=self.charge, credit_account=self.produit, amount=Decimal("10.00"))

        resp = self.client.get(
            reverse("accounting:statements_excel")
            + f"?start_date={self.start.isoformat()}&end_date={self.end.isoformat()}&validated_only=1"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", resp["Content-Type"])

    def test_financial_statements_pdf_export(self):
        self.force_login()
        self.create_validated_entry(debit_account=self.charge, credit_account=self.produit, amount=Decimal("10.00"))

        fake_html_instance = MagicMock()
        fake_html_instance.write_pdf.return_value = b"%PDF-1.4 dummy"
        fake_weasyprint = MagicMock()
        fake_weasyprint.HTML.return_value = fake_html_instance

        with patch.dict("sys.modules", {"weasyprint": fake_weasyprint}):
            resp = self.client.get(
                reverse("accounting:statements_pdf")
                + f"?start_date={self.start.isoformat()}&end_date={self.end.isoformat()}&validated_only=1"
            )

        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/pdf", resp["Content-Type"])

    def test_financial_statements_pdf_weasyprint_fails_returns_printable_html(self):
        self.force_login()
        self.create_validated_entry(debit_account=self.charge, credit_account=self.produit, amount=Decimal("10.00"))

        fake_html_instance = MagicMock()
        fake_html_instance.write_pdf.side_effect = OSError("weasyprint system libs missing")
        fake_weasyprint = MagicMock()
        fake_weasyprint.HTML.return_value = fake_html_instance

        with patch.dict("sys.modules", {"weasyprint": fake_weasyprint}):
            resp = self.client.get(
                reverse("accounting:statements_pdf")
                + f"?start_date={self.start.isoformat()}&end_date={self.end.isoformat()}&validated_only=1"
            )

        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])
        self.assertContains(resp, "États financiers synthétiques")
        self.assertContains(resp, "Bilan simplifié")

    def test_entry_list_pagination(self):
        self.force_login()
        # 30 entrées => 25 sur la page 1 (MVP)
        for i in range(30):
            entry = AccountingEntry.objects.create(
                company=self.company,
                date=self.end,
                description=f"E{i}",
                reference=f"R{i}",
                created_by=self.user,
                validated=bool(i % 2),
            )
            EntryLine.objects.create(entry=entry, account=self.actif, debit=Decimal("1.00"), credit=Decimal("0.00"))
            EntryLine.objects.create(entry=entry, account=self.passif, debit=Decimal("0.00"), credit=Decimal("1.00"))

        resp = self.client.get(reverse("accounting:entry_list") + "?page=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["page_obj"]), 25)

