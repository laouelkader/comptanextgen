from __future__ import annotations

from unittest.mock import patch
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptanextgen.settings import CustomComplexPasswordValidator

from .forms import LoginForm, TwoFactorForm
from .models import AuditLog, Company, User


class CoreMVPTests(TestCase):
    def test_password_validator_rejects_short(self):
        v = CustomComplexPasswordValidator()
        with self.assertRaises(ValueError):
            v.validate("Aa!1", None)

    def test_password_validator_accepts_complex(self):
        v = CustomComplexPasswordValidator()
        v.validate("Aa!234567", None)

    def test_login_form_validation_missing_fields(self):
        form = LoginForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        self.assertIn("password", form.errors)

    def test_two_factor_form_validation_rejects_non_digits(self):
        form = TwoFactorForm(data={"code": "12AB34"})
        self.assertFalse(form.is_valid())

    def test_cabinet_admin_only_blocks_non_cabinet_admin(self):
        company = Company.objects.create(nom="Alpha SARL", is_active=True)
        user = User.objects.create(email="manager@alpha.test", role="MANAGER", company=company, is_active=True)
        user.set_password("Aa!234567")
        user.save()

        self.client.force_login(user)
        resp = self.client.get(reverse("core:admin_dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_cabinet_admin_only_allows_cabinet_admin(self):
        user = User.objects.create(email="cabinet@alpha.test", role="CABINET_ADMIN", company=None, is_active=True)
        user.set_password("Aa!234567")
        user.save()

        self.client.force_login(user)
        resp = self.client.get(reverse("core:admin_dashboard"))
        self.assertEqual(resp.status_code, 200)

    @patch("apps.core.views.send_mail")
    def test_login_2fa_creates_pending_session(self, mock_send_mail):
        company = Company.objects.create(nom="Alpha SARL", is_active=True)
        user = User.objects.create(email="2fa@alpha.test", role="MANAGER", company=company, is_active=True, two_factor_enabled=True)
        user.set_password("Aa!234567")
        user.save()

        resp = self.client.post(reverse("core:login"), {"email": user.email, "password": "Aa!234567"}, follow=False)
        self.assertEqual(resp.status_code, 302)

        self.assertIn("two_factor_pending_user_id", self.client.session)
        self.assertIn("two_factor_code", self.client.session)
        mock_send_mail.assert_called()

    @patch("apps.core.views.send_mail")
    def test_login_2fa_wrong_code_returns_error(self, mock_send_mail):
        company = Company.objects.create(nom="Alpha SARL", is_active=True)
        user = User.objects.create(email="2fa2@alpha.test", role="MANAGER", company=company, is_active=True, two_factor_enabled=True)
        user.set_password("Aa!234567")
        user.save()

        # Prépare session comme si l'utilisateur venait de passer le login password
        session = self.client.session
        session["two_factor_pending_user_id"] = user.id
        session["two_factor_code"] = "123456"
        session["two_factor_code_created_at"] = timezone.now().isoformat()
        session.save()

        resp = self.client.post(reverse("core:login"), {"code": "000000"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Code 2FA incorrect", resp.content.decode("utf-8"))

    def test_two_factor_expires(self):
        company = Company.objects.create(nom="Alpha SARL", is_active=True)
        user = User.objects.create(email="2faexp@alpha.test", role="MANAGER", company=company, is_active=True, two_factor_enabled=True)
        user.set_password("Aa!234567")
        user.save()

        session = self.client.session
        session["two_factor_pending_user_id"] = user.id
        session["two_factor_code"] = "123456"
        session["two_factor_code_created_at"] = (timezone.now() - timedelta(seconds=10 * 60)).isoformat()
        session.save()

        resp = self.client.post(reverse("core:login"), {"code": "123456"}, follow=False)
        self.assertEqual(resp.status_code, 302)
        # Redirection vers login
        self.assertTrue(resp.url.endswith("/login/"))

    def test_auditlog_company_created_on_save(self):
        before = AuditLog.objects.count()
        company = Company.objects.create(nom="Gamma EURL", is_active=True)
        after = AuditLog.objects.count()
        self.assertGreater(after, before)
        entry = AuditLog.objects.filter(model_name="Company", object_id=str(company.pk), action="create").first()
        self.assertIsNotNone(entry)

    def test_admin_dashboard_create_company_via_post(self):
        admin = User.objects.create(email="admin2@compta.test", role="CABINET_ADMIN", company=None, is_active=True)
        admin.set_password("Aa!234567")
        admin.save()
        self.client.force_login(admin)

        resp = self.client.post(
            reverse("core:admin_dashboard"),
            {
                "action": "create_company",
                "nom": "Delta SARL",
                "siret": "45678901234567",
                "iban": "FR7612345678901234567890123",
                "phone": "0101010101",
                "email": "contact@delta.fr",
                "address": "1 rue Test",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Company.objects.filter(nom="Delta SARL", is_active=True).exists())

    def test_admin_dashboard_delete_company_soft(self):
        admin = User.objects.create(email="admin3@compta.test", role="CABINET_ADMIN", company=None, is_active=True)
        admin.set_password("Aa!234567")
        admin.save()
        company = Company.objects.create(nom="Epsilon SAS", is_active=True)

        self.client.force_login(admin)
        resp = self.client.post(
            reverse("core:admin_dashboard"),
            {"action": "delete_company", "company_id": company.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        company.refresh_from_db()
        self.assertFalse(company.is_active)

