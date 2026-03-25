from django.conf import settings

from apps.core.permissions import (
    can_cancel_billing_documents,
    can_manage_sensitive_company_actions,
    is_collaborator,
)


def debug_flag(_request):
    """Expose un booléen pour afficher des aides dev (ex. comptes démo sur la page login)."""
    return {"is_debug": settings.DEBUG}


def role_permissions(request):
    """
    Droits gérant/comptable vs collaborateur (cabinet admin = actions sensibles autorisées).
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {
            "user_can_manage_sensitive": False,
            "user_is_collaborator": False,
            "user_can_cancel_billing": False,
        }
    return {
        "user_can_manage_sensitive": can_manage_sensitive_company_actions(user),
        "user_is_collaborator": is_collaborator(user),
        "user_can_cancel_billing": can_cancel_billing_documents(user),
    }
