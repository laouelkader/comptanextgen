from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from io import BytesIO

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from apps.core.models import Company, User

from .models import BankAccount, BankTransaction, CashForecastItem


class TreasuryMVPTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(nom="Alpha SARL", is_active=True)
        self.other_company = Company.objects.create(nom="Beta SAS", is_active=True)

        self.user = User.objects.create(email="manager@alpha.test", role="MANAGER", company=self.company, is_active=True)
        self.user.set_password("Aa!234567")
        self.user.save()

        self.now = timezone.now()

        self.account = BankAccount.objects.create(
            company=self.company,
            name="Compte principal",
            bank_name="Bank",
            initial_balance=Decimal("1000.00"),
            current_balance=Decimal("1200.00"),
            is_main=True,
        )

        self.other_account = BankAccount.objects.create(
            company=self.other_company,
            name="Autre compte",
            bank_name="Bank2",
            initial_balance=Decimal("500.00"),
            current_balance=Decimal("600.00"),
            is_main=False,
        )

    def force_login(self):
        self.client.force_login(self.user)

    def test_simulated_bank_transactions_api_200(self):
        self.force_login()
        resp = self.client.get(reverse("bank_simulator_api", args=[self.company.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["company_id"], self.company.id)
        self.assertIn("transactions", data)
        self.assertGreater(len(data["transactions"]), 0)

    def test_simulated_bank_transactions_api_forbidden_for_other_company(self):
        self.force_login()
        resp = self.client.get(reverse("bank_simulator_api", args=[self.other_company.id]))
        self.assertEqual(resp.status_code, 403)

    def test_treasury_dashboard_solde_sum(self):
        BankAccount.objects.create(company=self.company, name="C2", bank_name="B", initial_balance=0, current_balance=Decimal("10.00"))
        CashForecastItem.objects.create(
            company=self.company,
            date=(self.now + timedelta(days=5)).date(),
            description="Encaissement",
            amount=Decimal("100.00"),
            type=CashForecastItem.Types.INCOME,
            is_actual=False,
        )

        self.force_login()
        resp = self.client.get(reverse("treasury:treasury_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertAlmostEqual(float(resp.context["solde"]), float(Decimal("1200.00") + Decimal("10.00")), places=2)

    def test_reconciliation_post_marks_reconciled(self):
        tx = BankTransaction.objects.create(
            bank_account=self.account,
            date=self.now.date(),
            description="Paiement",
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Types.DEBIT,
            reconciled=False,
        )
        self.force_login()
        resp = self.client.post(
            reverse("treasury:reconciliation"),
            {"bank_transaction_id": tx.id, "reconciled_entry_id": ""},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        tx.refresh_from_db()
        self.assertTrue(tx.reconciled)
        self.assertIsNotNone(tx.reconciliation_date)

    def test_reconciliation_access_denied_other_company(self):
        tx = BankTransaction.objects.create(
            bank_account=self.other_account,
            date=self.now.date(),
            description="Paiement",
            amount=Decimal("25.00"),
            transaction_type=BankTransaction.Types.DEBIT,
            reconciled=False,
        )
        self.force_login()
        resp = self.client.post(
            reverse("treasury:reconciliation"),
            {"bank_transaction_id": tx.id, "reconciled_entry_id": ""},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        tx.refresh_from_db()
        self.assertFalse(tx.reconciled)

    def test_forecast_series_cumulative_net(self):
        d1 = (self.now + timedelta(days=1)).date()
        d2 = (self.now + timedelta(days=2)).date()

        CashForecastItem.objects.create(company=self.company, date=d1, description="Inc1", amount=Decimal("100.00"), type=CashForecastItem.Types.INCOME)
        CashForecastItem.objects.create(company=self.company, date=d1, description="Dep1", amount=Decimal("30.00"), type=CashForecastItem.Types.EXPENSE)
        CashForecastItem.objects.create(company=self.company, date=d2, description="Inc2", amount=Decimal("50.00"), type=CashForecastItem.Types.INCOME)

        self.force_login()
        resp = self.client.get(reverse("treasury:forecast") + "?horizon_days=90")
        self.assertEqual(resp.status_code, 200)

        # Net day1 = 70, cumulative day1 = 70; day2 net=+50 => cumulative day2 = 120
        series = resp.context["series"]
        self.assertTrue(len(series) >= 2)
        self.assertAlmostEqual(series[0], 70.0, places=2)
        self.assertAlmostEqual(series[1], 120.0, places=2)

    def test_forecast_create_item_post(self):
        self.force_login()
        resp = self.client.post(
            reverse("treasury:forecast"),
            {
                "date": (self.now + timedelta(days=10)).date().isoformat(),
                "description": "Test prévision",
                "amount": "200.00",
                "type": "INCOME",
                "category": "VENTES",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(CashForecastItem.objects.filter(company=self.company, description="Test prévision").exists())

    def test_reconciliation_pagination(self):
        for i in range(30):
            BankTransaction.objects.create(
                bank_account=self.account,
                date=(self.now - timedelta(days=i)).date(),
                description=f"T{i}",
                amount=Decimal("1.00"),
                transaction_type=BankTransaction.Types.DEBIT,
                reconciled=False,
            )
        self.force_login()
        resp = self.client.get(reverse("treasury:reconciliation") + "?page=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["page_obj"]), 25)

    def test_bank_transaction_fields(self):
        tx = BankTransaction.objects.create(
            bank_account=self.account,
            date=self.now.date(),
            description="Achat",
            amount=Decimal("10.50"),
            transaction_type=BankTransaction.Types.DEBIT,
        )
        self.assertEqual(tx.amount, Decimal("10.50"))
        self.assertEqual(tx.transaction_type, BankTransaction.Types.DEBIT)

    def test_cash_forecast_item_defaults(self):
        it = CashForecastItem.objects.create(
            company=self.company,
            date=self.now.date(),
            description="X",
            amount=Decimal("10.00"),
            type=CashForecastItem.Types.INCOME,
        )
        self.assertFalse(it.is_recurring)
        self.assertFalse(it.is_actual)

    def test_import_csv_transactions(self):
        self.force_login()
        csv_content = "date,description,amount,transaction_type\n2026-03-20,Paiement,123.45,DEBIT\n"
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded = SimpleUploadedFile("releve.csv", csv_content.encode("utf-8"), content_type="text/csv")
        resp = self.client.post(
            reverse("treasury:reconciliation"),
            {
                "bank_account_id": str(self.account.id),
                "file": uploaded,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(BankTransaction.objects.filter(bank_account=self.account, description="Paiement").exists())

    def test_import_xlsx_transactions(self):
        self.force_login()
        wb = Workbook()
        ws = wb.active
        ws.append(["date", "description", "amount", "transaction_type"])
        ws.append([self.now.date().isoformat(), "Virement", 99.99, "CREDIT"])
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)

        # On simule un UploadedFile minimal
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile(
            "releve.xlsx",
            bio.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post(
            reverse("treasury:reconciliation"),
            {
                "bank_account_id": str(self.account.id),
                "file": uploaded,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(BankTransaction.objects.filter(bank_account=self.account, description="Virement").exists())

