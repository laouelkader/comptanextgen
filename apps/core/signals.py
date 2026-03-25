from django.apps import apps as django_apps
from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .middleware import get_request_ip_address, get_request_user
from .models import AuditLog


SENSITIVE_SENDER_SPECS = [
    ("core", "Company"),
    ("core", "User"),
    ("accounting", "AccountingEntry"),
    ("invoicing", "Invoice"),
    ("treasury", "BankAccount"),
]


def _get_company_for_instance(instance):
    if hasattr(instance, "company"):
        return getattr(instance, "company")
    return None


def _log(action: str, instance, extra_details=None):
    req_user = get_request_user()
    ip = get_request_ip_address()

    user_to_set = None
    if req_user is not None and getattr(req_user, "is_authenticated", False):
        req_pk = getattr(req_user, "pk", None)
        if req_pk:
            try:
                auth_user_model = django_apps.get_model(*settings.AUTH_USER_MODEL.split("."))
                if auth_user_model.objects.filter(pk=req_pk).exists():
                    user_to_set = req_user
            except Exception:
                user_to_set = None

    AuditLog.objects.create(
        user=user_to_set,
        action=action,
        model_name=instance.__class__.__name__,
        object_id=str(getattr(instance, "pk", "")),
        timestamp=timezone.now(),
        ip_address=ip,
        details=extra_details or {},
        company=_get_company_for_instance(instance),
    )


def register_audit_triggers():
    """
    Connecte post_save/post_delete pour les modèles sensibles.
    """

    for app_label, model_name in SENSITIVE_SENDER_SPECS:
        try:
            sender = django_apps.get_model(app_label, model_name)
        except LookupError:
            continue

        @receiver(post_save, sender=sender, weak=False)
        def _post_save(sender, instance, created=False, **kwargs):
            action = "create" if created else "update"
            _log(action=action, instance=instance, extra_details={"created": created})

        @receiver(post_delete, sender=sender, weak=False)
        def _post_delete(sender, instance, **kwargs):
            _log(action="delete", instance=instance, extra_details={})

