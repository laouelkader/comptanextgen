from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Company, User

from .models import Invoice, InvoiceLine, Quote
from .utils import process_overdue_invoice_reminders, recalc_totals_for_invoice, recalc_totals_for_quote, next_invoice_number, next_quote_number


class InvoicingMVPTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(nom="Alpha SARL", is_active=True)
        self.user = User.objects.create(email="manager@alpha.test", role="MANAGER", company=self.company, is_active=True)
        self.user.set_password("Aa!234567")
        self.user.save()

        self.now = timezone.now()

    def force_login(self):
        self.client.force_login(self.user)

    def test_next_quote_number_format(self):
        year = timezone.now().year
        number = next_quote_number(self.company)
        self.assertTrue(number.startswith(f"DEV-{year}-"))
        self.assertEqual(len(number.split("-")[-1]), 4)

    def test_next_invoice_number_format(self):
        year = timezone.now().year
        number = next_invoice_number(self.company)
        self.assertTrue(number.startswith(f"FAC-{year}-"))
        self.assertEqual(len(number.split("-")[-1]), 4)

    def test_invoice_line_amounts_computed(self):
        quote = Quote.objects.create(
            company=self.company,
            number=next_quote_number(self.company),
            date=self.now.date(),
            valid_until=(self.now + timedelta(days=30)).date(),
            client_name="Client",
            status=Quote.Status.DRAFT,
        )
        line = InvoiceLine.objects.create(
            quote=quote,
            invoice=None,
            description="Service",
            quantity=Decimal("2.00"),
            unit_price=Decimal("50.00"),
            tax_rate=Decimal("20.0"),
        )
        self.assertEqual(line.amount_ht, Decimal("100.00"))
        self.assertEqual(line.amount_ttc, Decimal("120.00"))

    def test_recalc_totals_for_quote(self):
        quote = Quote.objects.create(
            company=self.company,
            number=next_quote_number(self.company),
            date=self.now.date(),
            valid_until=(self.now + timedelta(days=30)).date(),
            client_name="Client",
            status=Quote.Status.DRAFT,
        )
        InvoiceLine.objects.create(quote=quote, invoice=None, description="A", quantity=Decimal("1.00"), unit_price=Decimal("10.00"), tax_rate=Decimal("0.0"))
        InvoiceLine.objects.create(quote=quote, invoice=None, description="B", quantity=Decimal("2.00"), unit_price=Decimal("10.00"), tax_rate=Decimal("20.0"))
        recalc_totals_for_quote(quote)
        quote.refresh_from_db()
        self.assertEqual(quote.total_ht, Decimal("30.00"))
        self.assertEqual(quote.total_ttc, Decimal("34.00"))

    def test_recalc_totals_for_invoice(self):
        invoice = Invoice.objects.create(
            company=self.company,
            number=next_invoice_number(self.company),
            date=self.now.date(),
            due_date=(self.now - timedelta(days=1)).date(),
            client_name="Client",
            status=Invoice.Status.SENT,
        )
        InvoiceLine.objects.create(invoice=invoice, quote=None, description="A", quantity=Decimal("1.00"), unit_price=Decimal("100.00"), tax_rate=Decimal("10.0"))
        recalc_totals_for_invoice(invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.total_ht, Decimal("100.00"))
        self.assertEqual(invoice.total_ttc, Decimal("110.00"))

    def test_quote_convert_view_creates_invoice_and_lines(self):
        quote = Quote.objects.create(
            company=self.company,
            number=next_quote_number(self.company),
            date=self.now.date(),
            valid_until=(self.now + timedelta(days=30)).date(),
            client_name="Client",
            status=Quote.Status.ACCEPTED,
        )
        InvoiceLine.objects.create(quote=quote, invoice=None, description="L1", quantity=Decimal("1.00"), unit_price=Decimal("10.00"), tax_rate=Decimal("0.0"))
        InvoiceLine.objects.create(quote=quote, invoice=None, description="L2", quantity=Decimal("2.00"), unit_price=Decimal("10.00"), tax_rate=Decimal("20.0"))

        self.force_login()
        resp = self.client.post(reverse("invoicing:quote_convert", args=[quote.id]), follow=True)
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(Invoice.objects.filter(company=self.company).count(), 1)
        inv = Invoice.objects.filter(company=self.company).first()
        self.assertEqual(inv.lines.count(), 2)
        self.assertEqual(inv.status, Invoice.Status.DRAFT)

    def test_quote_list_pagination_25(self):
        base_date = self.now.date()
        for i in range(30):
            q = Quote.objects.create(
                company=self.company,
                number=next_quote_number(self.company),
                date=base_date,
                valid_until=base_date,
                client_name=f"C{i}",
                status=Quote.Status.DRAFT,
            )
            # au moins 1 ligne pour éviter total vide si on veut ; ici pas requis
            InvoiceLine.objects.create(
                quote=q,
                invoice=None,
                description="X",
                quantity=Decimal("1.00"),
                unit_price=Decimal("1.00"),
                tax_rate=Decimal("0.0"),
            )

        self.force_login()
        resp = self.client.get(reverse("invoicing:quote_list") + "?page=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["page_obj"]), 25)

    def test_invoice_excel_export(self):
        invoice = Invoice.objects.create(
            company=self.company,
            number=next_invoice_number(self.company),
            date=self.now.date(),
            due_date=(self.now + timedelta(days=10)).date(),
            client_name="Client",
            status=Invoice.Status.SENT,
        )
        InvoiceLine.objects.create(invoice=invoice, quote=None, description="A", quantity=Decimal("1.00"), unit_price=Decimal("10.00"), tax_rate=Decimal("0.0"))
        recalc_totals_for_invoice(invoice)

        self.force_login()
        resp = self.client.get(reverse("invoicing:invoice_export_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", resp["Content-Type"])

    def test_invoice_pdf_export_mock_weasyprint(self):
        invoice = Invoice.objects.create(
            company=self.company,
            number=next_invoice_number(self.company),
            date=self.now.date(),
            due_date=(self.now + timedelta(days=10)).date(),
            client_name="Client",
            status=Invoice.Status.SENT,
        )
        InvoiceLine.objects.create(invoice=invoice, quote=None, description="A", quantity=Decimal("1.00"), unit_price=Decimal("10.00"), tax_rate=Decimal("0.0"))
        recalc_totals_for_invoice(invoice)

        # Mock weasyprint pour éviter libs système
        fake_html_instance = MagicMock()
        fake_html_instance.write_pdf.return_value = b"%PDF-1.4 dummy"
        fake_weasyprint = MagicMock()
        fake_weasyprint.HTML.return_value = fake_html_instance

        self.force_login()
        with patch.dict("sys.modules", {"weasyprint": fake_weasyprint}):
            resp = self.client.get(reverse("invoicing:invoice_pdf", args=[invoice.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/pdf", resp["Content-Type"])

    def test_invoice_pdf_weasyprint_fails_returns_printable_html(self):
        invoice = Invoice.objects.create(
            company=self.company,
            number=next_invoice_number(self.company),
            date=self.now.date(),
            due_date=(self.now + timedelta(days=10)).date(),
            client_name="Client",
            status=Invoice.Status.SENT,
        )
        InvoiceLine.objects.create(invoice=invoice, quote=None, description="A", quantity=Decimal("1.00"), unit_price=Decimal("10.00"), tax_rate=Decimal("0.0"))
        recalc_totals_for_invoice(invoice)

        fake_html_instance = MagicMock()
        fake_html_instance.write_pdf.side_effect = OSError("weasyprint system libs missing")
        fake_weasyprint = MagicMock()
        fake_weasyprint.HTML.return_value = fake_html_instance

        self.force_login()
        with patch.dict("sys.modules", {"weasyprint": fake_weasyprint}):
            resp = self.client.get(reverse("invoicing:invoice_pdf", args=[invoice.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Détail des prestations")
        self.assertContains(resp, invoice.number)

    def test_process_overdue_invoice_reminders_updates_invoice(self):
        invoice = Invoice.objects.create(
            company=self.company,
            number=next_invoice_number(self.company),
            date=(self.now - timedelta(days=30)).date(),
            due_date=(self.now - timedelta(days=10)).date(),
            client_name="Client",
            client_email="client@example.com",
            status=Invoice.Status.SENT,
        )
        recalc_totals_for_invoice(invoice)

        count = process_overdue_invoice_reminders(now=self.now)
        invoice.refresh_from_db()
        self.assertGreaterEqual(count, 1)
        self.assertEqual(invoice.reminder_count, 1)
        self.assertEqual(invoice.status, Invoice.Status.OVERDUE)

    def test_invoice_list_pagination_25(self):
        base_date = self.now.date()
        for i in range(30):
            inv = Invoice.objects.create(
                company=self.company,
                number=next_invoice_number(self.company),
                date=base_date,
                due_date=base_date,
                client_name=f"C{i}",
                status=Invoice.Status.DRAFT,
            )
            InvoiceLine.objects.create(invoice=inv, quote=None, description="X", quantity=Decimal("1.00"), unit_price=Decimal("1.00"), tax_rate=Decimal("0.0"))
            recalc_totals_for_invoice(inv)

        self.force_login()
        resp = self.client.get(reverse("invoicing:invoice_list") + "?page=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["page_obj"]), 25)

    @patch("apps.invoicing.utils.send_invoice_reminder")
    def test_management_command_send_invoice_reminders(self, mock_send):
        invoice = Invoice.objects.create(
            company=self.company,
            number=next_invoice_number(self.company),
            date=(self.now - timedelta(days=40)).date(),
            due_date=(self.now - timedelta(days=10)).date(),
            client_name="Client",
            client_email="client@example.com",
            status=Invoice.Status.SENT,
        )

        call_command("send_invoice_reminders")
        invoice.refresh_from_db()
        self.assertGreaterEqual(invoice.reminder_count, 1)
        self.assertEqual(invoice.status, Invoice.Status.OVERDUE)
        mock_send.assert_called()

