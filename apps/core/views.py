import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.views import LogoutView
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from .decorators import cabinet_admin_only, company_required
from .forms import CompanyForm, LoginForm, TwoFactorForm
from .models import Company, User


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


class LoginView(TemplateView):
    template_name = "core/login.html"

    RATE_LIMIT_MAX = 5
    RATE_LIMIT_TTL_SECONDS = 15 * 60
    TWO_FACTOR_EXPIRY_SECONDS = 5 * 60

    def get(self, request, *args, **kwargs):
        pending_user_id = request.session.get("two_factor_pending_user_id")
        code_created_at = request.session.get("two_factor_code_created_at")

        two_factor_required = False
        if pending_user_id and code_created_at:
            created_at = timezone.datetime.fromisoformat(code_created_at)
            two_factor_required = timezone.now() <= created_at + timedelta(seconds=self.TWO_FACTOR_EXPIRY_SECONDS)

        return self.render_to_response(
            {
                "login_form": LoginForm(),
                "two_factor_form": TwoFactorForm(),
                "two_factor_required": two_factor_required,
            }
        )

    def post(self, request, *args, **kwargs):
        pending_user_id = request.session.get("two_factor_pending_user_id")
        code_created_at = request.session.get("two_factor_code_created_at")

        if pending_user_id and code_created_at:
            return self._handle_two_factor(request, pending_user_id)

        return self._handle_password_login(request)

    def _handle_password_login(self, request):
        ip = _get_client_ip(request)
        cache_key = f"login_attempts::{ip}"
        attempts = cache.get(cache_key, 0)

        if attempts >= self.RATE_LIMIT_MAX:
            messages.error(request, "Trop de tentatives de connexion. Réessayez plus tard.")
            return redirect("core:login")

        form = LoginForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Formulaire invalide.")
            return self.render_to_response(
                {"login_form": form, "two_factor_form": TwoFactorForm(), "two_factor_required": False}
            )

        user = authenticate(request, email=form.cleaned_data["email"], password=form.cleaned_data["password"])
        if not user:
            cache.set(cache_key, attempts + 1, timeout=self.RATE_LIMIT_TTL_SECONDS)
            messages.error(request, "Email ou mot de passe incorrect.")
            return self.render_to_response(
                {"login_form": form, "two_factor_form": TwoFactorForm(), "two_factor_required": False}
            )

        cache.delete(cache_key)

        if not user.is_active:
            messages.error(request, "Votre compte est désactivé.")
            return self.render_to_response(
                {"login_form": form, "two_factor_form": TwoFactorForm(), "two_factor_required": False}
            )

        if user.two_factor_enabled:
            code = str(secrets.randbelow(1_000_000)).zfill(6)
            now = timezone.now()

            request.session["two_factor_pending_user_id"] = user.id
            request.session["two_factor_code"] = code
            request.session["two_factor_code_created_at"] = now.isoformat()
            request.session.modified = True

            send_mail(
                subject="Votre code de vérification 2FA",
                message=f"Votre code 2FA est : {code}",
                from_email=None,
                recipient_list=[user.email],
            )

            messages.info(request, "Code 2FA envoyé. Veuillez le saisir.")
            return redirect("core:login")

        login(request, user)
        return redirect("core:dashboard")

    def _handle_two_factor(self, request, pending_user_id: int):
        form = TwoFactorForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Code 2FA invalide.")
            return self.render_to_response(
                {"login_form": LoginForm(), "two_factor_form": form, "two_factor_required": True}
            )

        created_at_raw = request.session.get("two_factor_code_created_at")
        if not created_at_raw:
            return redirect("core:login")

        created_at = timezone.datetime.fromisoformat(created_at_raw)
        if timezone.now() > created_at + timedelta(seconds=self.TWO_FACTOR_EXPIRY_SECONDS):
            for k in ["two_factor_pending_user_id", "two_factor_code", "two_factor_code_created_at"]:
                request.session.pop(k, None)
            messages.error(request, "Code 2FA expiré. Veuillez vous reconnecter.")
            return redirect("core:login")

        expected = request.session.get("two_factor_code")
        if form.cleaned_data["code"] != expected:
            messages.error(request, "Code 2FA incorrect.")
            return self.render_to_response(
                {"login_form": LoginForm(), "two_factor_form": form, "two_factor_required": True}
            )

        user = User.objects.filter(pk=pending_user_id).first()
        if not user or not user.is_active:
            messages.error(request, "Compte introuvable ou désactivé.")
            return redirect("core:login")

        for k in ["two_factor_pending_user_id", "two_factor_code", "two_factor_code_created_at"]:
            request.session.pop(k, None)
        request.session.modified = True

        login(request, user)
        return redirect("core:dashboard")


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    @company_required
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = getattr(self.request, "company", None)

        from django.apps import apps as django_apps
        from django.db.models import Sum

        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        ca_mensuel = 0
        solde_tresorerie = 0
        factures_impayees = 0
        nb_ecritures_mois = 0

        try:
            Invoice = django_apps.get_model("invoicing", "Invoice")
            invoices_month = Invoice.objects.filter(company=company, date__gte=month_start, date__lte=now)
            ca_mensuel = invoices_month.aggregate(total=Sum("total_ht")).get("total") or 0
            factures_impayees = Invoice.objects.filter(company=company).exclude(status="PAID").count()
        except LookupError:
            pass

        try:
            AccountingEntry = django_apps.get_model("accounting", "AccountingEntry")
            nb_ecritures_mois = AccountingEntry.objects.filter(company=company, created_at__gte=month_start).count()
        except LookupError:
            pass

        try:
            BankAccount = django_apps.get_model("treasury", "BankAccount")
            solde_tresorerie = BankAccount.objects.filter(company=company).aggregate(total=Sum("current_balance")).get("total") or 0
        except LookupError:
            pass

        ctx.update(
            {
                "ca_mensuel": ca_mensuel,
                "solde_tresorerie": solde_tresorerie,
                "factures_impayees": factures_impayees,
                "nb_ecritures_mois": nb_ecritures_mois,
                "alertes": [],
            }
        )
        return ctx


class AdminDashboardView(TemplateView):
    template_name = "core/admin_dashboard.html"

    @cabinet_admin_only
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx["companies"] = Company.objects.filter(is_active=True).order_by("nom")
        ctx["total_users_actifs"] = User.objects.filter(is_active=True).count()
        ctx["total_companies"] = Company.objects.filter(is_active=True).count()
        ctx["company_form"] = kwargs.get("company_form") or CompanyForm()
        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")

        if action == "create_company":
            form = CompanyForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Formulaire entreprise invalide.")
                ctx = self.get_context_data(company_form=form)
                return self.render_to_response(ctx)

            Company.objects.create(
                nom=form.cleaned_data["nom"],
                siret=form.cleaned_data.get("siret") or None,
                iban=form.cleaned_data.get("iban") or None,
                phone=form.cleaned_data.get("phone") or None,
                email=form.cleaned_data.get("email") or None,
                address=form.cleaned_data.get("address") or None,
                is_active=True,
            )
            messages.success(request, "Entreprise créée.")
            return redirect("core:admin_dashboard")

        if action == "delete_company":
            company_id = request.POST.get("company_id")
            company = Company.objects.filter(pk=company_id, is_active=True).first()
            if not company:
                messages.error(request, "Entreprise introuvable.")
                return redirect("core:admin_dashboard")

            # Suppression logique pour éviter la casse FK
            company.is_active = False
            company.save(update_fields=["is_active"])
            messages.success(request, "Entreprise désactivée (suppression logique).")
            return redirect("core:admin_dashboard")

        messages.error(request, "Action non reconnue.")
        return redirect("core:admin_dashboard")


class CustomLogoutView(LogoutView):
    next_page = "/login/"

