from django.conf import settings


def debug_flag(_request):
    """Expose un booléen pour afficher des aides dev (ex. comptes démo sur la page login)."""
    return {"is_debug": settings.DEBUG}
