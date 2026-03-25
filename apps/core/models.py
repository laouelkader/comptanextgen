from __future__ import annotations

from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def _get_fernet() -> Fernet:
    """
    ENCRYPTION_KEY doit être une clé Fernet valide (base64) : https://cryptography.io/en/latest/fernet/#using-fernet
    """

    key = settings.ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


class EncryptedTextField(models.TextField):
    """
    Champ texte chiffré/déchiffré via Fernet.
    MVP : pas de recherche SQL sur la valeur chiffrée.
    """

    def get_prep_value(self, value: Any) -> Any:
        if value is None:
            return None
        value_str = str(value).strip()
        if value_str == "":
            return ""
        token = _get_fernet().encrypt(value_str.encode("utf-8"))
        return token.decode("utf-8")

    def from_db_value(self, value: Any, expression=None, connection=None) -> Any:
        if value is None:
            return None
        if value == "":
            return ""
        try:
            return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Si ENCRYPTION_KEY a changé, on évite de casser l'app
            return value

    def to_python(self, value: Any) -> Any:
        return value


class Company(models.Model):
    nom = models.CharField(max_length=255)
    siret = EncryptedTextField(blank=True, null=True)
    iban = EncryptedTextField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.nom


class User(AbstractUser):
    class Roles(models.TextChoices):
        CABINET_ADMIN = "CABINET_ADMIN", "CABINET_ADMIN"
        MANAGER = "MANAGER", "MANAGER"
        ACCOUNTANT = "ACCOUNTANT", "ACCOUNTANT"
        COLLABORATOR = "COLLABORATOR", "COLLABORATOR"

    # On utilise l'email comme identifiant
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, blank=True, default="")

    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=30, choices=Roles.choices, default=Roles.COLLABORATOR)

    two_factor_enabled = models.BooleanField(default=False)
    two_factor_code = models.CharField(max_length=6, blank=True, null=True)
    two_factor_code_created_at = models.DateTimeField(blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        return f"{self.email} ({self.role})"


class AuditLog(models.Model):
    """
    Journal d'audit pour modèles sensibles.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20)  # create/update/delete
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    timestamp = models.DateTimeField(default=timezone.now)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)

    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return f"[{self.action}] {self.model_name} {self.object_id}"

