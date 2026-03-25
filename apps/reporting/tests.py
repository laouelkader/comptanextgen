from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.core.models import Company, User


class ReportingMVPTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(nom="Alpha SARL", is_active=True)
        self.other_company = Company.objects.create(nom="Beta SAS", is_active=True)

        self.user_manager = User.objects.create(email="manager@alpha.test", role="MANAGER", company=self.company, is_active=True)
        self.user_manager.set_password("Aa!234567")
        self.user_manager.save()

        self.user_no_company = User.objects.create(email="nocorp@alpha.test", role="ACCOUNTANT", company=None, is_active=True)
        self.user_no_company.set_password("Aa!234567")
        self.user_no_company.save()

        self.user_cabinet = User.objects.create(email="cabinet@alpha.test", role="CABINET_ADMIN", company=None, is_active=True)
        self.user_cabinet.set_password("Aa!234567")
        self.user_cabinet.save()

    def test_analytics_requires_login(self):
        resp = self.client.get(reverse("reporting:analytics"))
        self.assertEqual(resp.status_code, 302)

    def test_alerts_requires_login(self):
        resp = self.client.get(reverse("reporting:alerts"))
        self.assertEqual(resp.status_code, 302)

    def test_analytics_allowed_for_user_with_company(self):
        self.client.force_login(self.user_manager)
        resp = self.client.get(reverse("reporting:analytics"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Analytics", resp.content.decode("utf-8"))

    def test_alerts_allowed_for_user_with_company(self):
        self.client.force_login(self.user_manager)
        resp = self.client.get(reverse("reporting:alerts"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Alertes", resp.content.decode("utf-8"))

    def test_analytics_forbidden_if_no_company_and_not_cabinet_admin(self):
        self.client.force_login(self.user_no_company)
        resp = self.client.get(reverse("reporting:analytics"))
        self.assertEqual(resp.status_code, 403)

    def test_alerts_forbidden_if_no_company_and_not_cabinet_admin(self):
        self.client.force_login(self.user_no_company)
        resp = self.client.get(reverse("reporting:alerts"))
        self.assertEqual(resp.status_code, 403)

    def test_analytics_allowed_for_cabinet_admin_without_company(self):
        self.client.force_login(self.user_cabinet)
        resp = self.client.get(reverse("reporting:analytics"))
        self.assertEqual(resp.status_code, 200)

    def test_alerts_allowed_for_cabinet_admin_without_company(self):
        self.client.force_login(self.user_cabinet)
        resp = self.client.get(reverse("reporting:alerts"))
        self.assertEqual(resp.status_code, 200)

    def test_urls_resolve(self):
        self.assertEqual(reverse("reporting:analytics"), "/reporting/analytics/")
        self.assertEqual(reverse("reporting:alerts"), "/reporting/alerts/")

    def test_pages_render_template_titles(self):
        self.client.force_login(self.user_manager)
        resp_a = self.client.get(reverse("reporting:analytics"))
        resp_b = self.client.get(reverse("reporting:alerts"))
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_b.status_code, 200)

    def test_export_excel_requires_login(self):
        resp = self.client.get(reverse("reporting:export_excel"))
        self.assertEqual(resp.status_code, 302)

    def test_export_excel_returns_xlsx(self):
        self.client.force_login(self.user_manager)
        resp = self.client.get(reverse("reporting:export_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", resp["Content-Type"])

