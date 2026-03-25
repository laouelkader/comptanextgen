from pathlib import Path
from urllib.parse import urlparse

from decouple import config
from cryptography.fernet import Fernet

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="insecure-dev-secret-key")
# Sans fichier .env, on reste en mode développement (évite page blanche / erreurs silencieuses).
DEBUG = config("DEBUG", cast=bool, default=True)

# Si ALLOWED_HOSTS est vide en .env : en DEBUG, accepter tout hôte (127.0.0.1, IP LAN, nom machine).
# Sinon erreur fréquente : « site inaccessible » / DisallowedHost en ouvrant http://192.168.x.x:8000/
_allowed_raw = config("ALLOWED_HOSTS", default="").strip()
if _allowed_raw:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_raw.split(",") if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

ENCRYPTION_KEY = config("ENCRYPTION_KEY", default=Fernet.generate_key().decode("utf-8"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "whitenoise.runserver_nostatic",

    "apps.core.apps.CoreConfig",
    "apps.accounting.apps.AccountingConfig",
    "apps.invoicing.apps.InvoicingConfig",
    "apps.treasury.apps.TreasuryConfig",
    "apps.reporting.apps.ReportingConfig",
]

AUTH_USER_MODEL = "core.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",

    "apps.core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "comptanextgen.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.debug_flag",
                "apps.core.context_processors.role_permissions",
            ],
        },
    }
]

WSGI_APPLICATION = "comptanextgen.wsgi.application"
ASGI_APPLICATION = "comptanextgen.asgi.application"

DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL doit être du type postgresql://...")

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username,
            "PASSWORD": parsed.password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


class CustomComplexPasswordValidator:
    """
    Validation de complexité minimale :
    - au moins 8 caractères
    - au moins 1 chiffre
    - au moins 1 majuscule
    - au moins 1 caractère spécial
    """

    def validate(self, password, user=None):
        if password is None or len(password) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
        if not any(c.isdigit() for c in password):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre.")
        if not any(c.isupper() for c in password):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule.")
        specials = "!@#$%^&*()-_=+[]{};:,.?/\\|"
        if not any(c in specials for c in password):
            raise ValueError("Le mot de passe doit contenir au moins un caractère spécial.")

    def get_help_text(self) -> str:
        return "Min 8, chiffre, majuscule et caractère spécial."


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "comptanextgen.settings.CustomComplexPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# En dev/test, éviter l'exigence du manifest (.json) en ne passant pas par le stockage manifest.
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_AGE = 1800
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="no-reply@comptanextgen.fr")

DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-comptanextgen",
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

