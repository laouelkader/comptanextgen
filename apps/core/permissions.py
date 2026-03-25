"""
Droits au sein d'une entreprise : gérant (MANAGER) et comptable (ACCOUNTANT)
peuvent valider, importer, configurer les alertes, exporter des données sensibles, etc.
Les collaborateurs (COLLABORATOR) ont un accès opérationnel limité (saisie, consultation).

Le rôle CABINET_ADMIN conserve tous les pouvoirs sur le périmètre cabinet / entreprises clientes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.models import User
    from apps.invoicing.models import Invoice, Quote


def user_role(user) -> str:
    return getattr(user, "role", None) or ""


def is_cabinet_admin(user) -> bool:
    return user_role(user) == "CABINET_ADMIN"


def is_company_privileged(user) -> bool:
    """Gérant ou comptable : même niveau d'action sensible au sein de l'entreprise."""
    return user_role(user) in ("MANAGER", "ACCOUNTANT")


def is_company_manager(user) -> bool:
    """Gérant d'entreprise (pas le comptable)."""
    return user_role(user) == "MANAGER"


def is_collaborator(user) -> bool:
    return user_role(user) == "COLLABORATOR"


def can_cancel_billing_documents(user) -> bool:
    """
    Annulation définitive de devis/factures : réservé au gérant et à l'admin cabinet.
    Le comptable peut éditer dans les limites autorisées mais ne peut pas annuler.
    """
    return is_cabinet_admin(user) or is_company_manager(user)


def can_edit_quote(user, quote: "Quote") -> bool:
    from apps.invoicing.models import Quote

    if quote.status in (Quote.Status.ACCEPTED, Quote.Status.CANCELLED):
        return False
    if is_collaborator(user):
        return quote.status == Quote.Status.DRAFT
    return is_cabinet_admin(user) or is_company_privileged(user)


def can_edit_invoice(user, invoice: "Invoice") -> bool:
    from apps.invoicing.models import Invoice

    if invoice.status in (Invoice.Status.PAID, Invoice.Status.CANCELLED):
        return False
    if is_collaborator(user):
        return invoice.status == Invoice.Status.DRAFT
    return is_cabinet_admin(user) or is_company_privileged(user)


def can_cancel_quote(user, quote: "Quote") -> bool:
    from apps.invoicing.models import Quote

    if not can_cancel_billing_documents(user):
        return False
    if quote.status in (Quote.Status.CANCELLED, Quote.Status.ACCEPTED):
        return False
    return True


def can_cancel_invoice(user, invoice: "Invoice") -> bool:
    from apps.invoicing.models import Invoice

    if not can_cancel_billing_documents(user):
        return False
    if invoice.status in (Invoice.Status.CANCELLED, Invoice.Status.PAID):
        return False
    return True


def can_manage_sensitive_company_actions(user) -> bool:
    """
    Validation d'écritures, conversion devis→facture, imports / rapprochement bancaire,
    saisie de prévisions de trésorerie, paramètres d'alertes (seuils),
    exports Excel/PDF des états financiers, export Excel factures, export reporting global.
    """
    return is_cabinet_admin(user) or is_company_privileged(user)


def can_validate_accounting_entries(user) -> bool:
    return can_manage_sensitive_company_actions(user)


def can_convert_quote_to_invoice(user) -> bool:
    return can_manage_sensitive_company_actions(user)


def can_access_treasury_sensitive_operations(user) -> bool:
    """Import relevé, marquer rapprochée, créer une ligne de prévision."""
    return can_manage_sensitive_company_actions(user)


def can_edit_alert_settings(user) -> bool:
    return can_manage_sensitive_company_actions(user)


def can_export_financial_reports(user) -> bool:
    return can_manage_sensitive_company_actions(user)


def can_export_invoice_excel(user) -> bool:
    return can_manage_sensitive_company_actions(user)


def can_export_reporting_global_excel(user) -> bool:
    return can_manage_sensitive_company_actions(user)
