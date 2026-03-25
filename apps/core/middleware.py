import threading
from typing import Optional

_thread = threading.local()


def set_request_context(user=None, ip_address: Optional[str] = None) -> None:
    _thread.user = user
    _thread.ip_address = ip_address


def get_request_user():
    return getattr(_thread, "user", None)


def get_request_ip_address() -> Optional[str]:
    return getattr(_thread, "ip_address", None)


class RequestContextMiddleware:
    """
    Permet aux signaux d'audit de récupérer user & IP courants.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if ip:
            ip = ip.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")

        set_request_context(user=getattr(request, "user", None), ip_address=ip)
        return self.get_response(request)

