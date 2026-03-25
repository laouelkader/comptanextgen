from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def _get_request_from_args(args, kwargs):
    """
    Supporte les décorateurs appliqués sur :
    - une fonction Django : (request, ...)
    - une méthode de classe (dispatch) : (self, request, ...)
    """
    if args:
        # cas fonction : args[0] == request
        if hasattr(args[0], "user"):
            return args[0]
        # cas méthode : args[1] == request
        if len(args) > 1 and hasattr(args[1], "user"):
            return args[1]
    return kwargs.get("request")


def role_required(*roles):
    """
    Autorise uniquement les rôles spécifiés.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(*args, **kwargs):
            request = _get_request_from_args(args, kwargs)
            user = request.user
            if not user.is_authenticated:
                return redirect("core:login")
            if getattr(user, "role", None) not in roles:
                return HttpResponseForbidden("Accès refusé.")
            return view_func(*args, **kwargs)

        return _wrapped

    return decorator


def cabinet_admin_only(view_func):
    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        request = _get_request_from_args(args, kwargs)
        user = request.user
        if not user.is_authenticated:
            return redirect("core:login")
        if getattr(user, "role", None) != "CABINET_ADMIN":
            return HttpResponseForbidden("Accès cabinet admin refusé.")
        return view_func(*args, **kwargs)

    return _wrapped


def company_required(view_func):
    """
    Vérifie l'appartenance à une entreprise pour les utilisateurs non-cabinet.
    """

    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        request = _get_request_from_args(args, kwargs)
        user = request.user
        if not user.is_authenticated:
            return redirect("core:login")

        if getattr(user, "role", None) == "CABINET_ADMIN":
            return view_func(*args, **kwargs)

        if getattr(user, "company", None) is None:
            return HttpResponseForbidden("Aucune entreprise associée.")

        request.company = user.company
        return view_func(*args, **kwargs)

    return _wrapped

