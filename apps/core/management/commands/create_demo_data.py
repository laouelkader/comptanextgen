"""
Génère des données fictives réalistes pour enrichir l’interface (démo / formation).
Marqueur interne : notes='__demo__' (factures/devis), category='DÉMO_AUTO' (prévisions),
import_id='demo_seed' (transactions), reference commençant par DEMO- (écritures).
"""
from __future__ import annotations

import random
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounting.models import AccountingEntry, ChartOfAccount, EntryLine
from apps.core.models import Company, User
from apps.invoicing.models import Invoice, InvoiceLine, Quote
from apps.invoicing.utils import next_invoice_number, next_quote_number, recalc_totals_for_invoice, recalc_totals_for_quote
from apps.reporting.models import AlertConfig
from apps.treasury.models import BankAccount, BankTransaction, CashForecastItem


DEMO_MARKER = "__demo__"
DEMO_REF_PREFIX = "DEMO-"
DEMO_FORECAST_CAT = "DÉMO_AUTO"
DEMO_TX_IMPORT = "demo_seed"

# Plan comptable minimal (aligné sur fixtures/initial_data.json) — créé si absent.
CHART_SEED = [
    ("411000", "Clients", "ACTIF"),
    ("512000", "Banque", "ACTIF"),
    ("401000", "Fournisseurs", "PASSIF"),
    ("421000", "Personnel", "PASSIF"),
    ("606300", "Fournitures", "CHARGE"),
    ("607000", "Achats", "CHARGE"),
    ("701000", "Ventes produits", "PRODUIT"),
    ("706000", "Prestations", "PRODUIT"),
    ("445660", "TVA déductible", "CHARGE"),
    ("445710", "TVA collectée", "PRODUIT"),
]

CLIENTS = [
    ("SARL Les Bons Comptes", "contact@bonscomptes.fr"),
    ("EURL Atelier du Nord", "facturation@atelier-nord.fr"),
    ("SCI Les Tilleuls", "gestion@tilleuls-sci.fr"),
    ("Auto-école Voltaire", "compta@voltaire-auto.fr"),
    ("Boulangerie Martin", "martin.boulangerie@orange.fr"),
    ("Cabinet Santé Plus", "admin@sante-plus.fr"),
    ("Transport Girard", "compta@girard-transport.fr"),
    ("Menuiserie Dubois", "cecile@menuiserie-dubois.fr"),
]

SERVICES = [
    "Prestation de conseil comptable",
    "Mission de révision annuelle",
    "Tenue de la comptabilité (mois)",
    "Établissement des liasses fiscales",
    "Accompagnement création d’entreprise",
    "Audit interne simplifié",
]

FORECAST_LABELS = [
    ("Encaissement client attendu", CashForecastItem.Types.INCOME),
    ("Paiement fournisseur", CashForecastItem.Types.EXPENSE),
    ("Charges sociales", CashForecastItem.Types.EXPENSE),
    ("Subvention à recevoir", CashForecastItem.Types.INCOME),
    ("Loyer à payer", CashForecastItem.Types.EXPENSE),
]

BANK_LABELS = [
    "Virement fournisseur",
    "Encaissement TPE",
    "Prélèvement URSSAF",
    "Virement salaires",
    "Remise chèques",
    "Frais bancaires",
]


def _ensure_chart_of_accounts() -> int:
    """Crée les comptes nécessaires si la base est vide (évite dépendre de loaddata)."""
    n = 0
    for num, name, typ in CHART_SEED:
        _, created = ChartOfAccount.objects.get_or_create(
            account_number=num,
            defaults={"name": name, "type": typ, "is_active": True},
        )
        if created:
            n += 1
    return n


def _clear_demo_data() -> None:
    """Supprime les données marquées démo (ré-exécution propre)."""
    Invoice.objects.filter(notes=DEMO_MARKER).delete()
    Quote.objects.filter(notes=DEMO_MARKER).delete()
    AccountingEntry.objects.filter(reference__startswith=DEMO_REF_PREFIX).delete()
    BankTransaction.objects.filter(import_id=DEMO_TX_IMPORT).delete()
    CashForecastItem.objects.filter(category=DEMO_FORECAST_CAT).delete()


class Command(BaseCommand):
    help = "Crée des données fictives (clients, factures, devis, écritures, trésorerie, alertes)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Supprime les données démo existantes avant d’en créer de nouvelles.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Graine aléatoire pour reproduire le même jeu de données.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["seed"] is not None:
            random.seed(options["seed"])

        if options["replace"]:
            _clear_demo_data()
            self.stdout.write(self.style.WARNING("Anciennes données démo supprimées."))

        now = timezone.now()
        today = now.date()

        seeded = _ensure_chart_of_accounts()
        if seeded:
            self.stdout.write(self.style.NOTICE(f"Plan comptable : {seeded} compte(s) créé(s)."))

        if ChartOfAccount.objects.filter(is_active=True).count() < 4:
            self.stderr.write("Impossible d’obtenir au moins 4 comptes actifs.")
            return

        charg = ChartOfAccount.objects.filter(type="CHARGE", is_active=True).first()
        prod = ChartOfAccount.objects.filter(type="PRODUIT", is_active=True).first()
        actif = ChartOfAccount.objects.filter(type="ACTIF", is_active=True).first()
        passif = ChartOfAccount.objects.filter(type="PASSIF", is_active=True).first()

        if not all([charg, prod, actif, passif]):
            self.stderr.write("Il manque un type de compte (CHARGE/PRODUIT/ACTIF/PASSIF).")
            return

        companies = list(Company.objects.filter(is_active=True))
        if not companies:
            self.stderr.write("Aucune entreprise active.")
            return

        total_created = {"quotes": 0, "invoices": 0, "entries": 0, "tx": 0, "fc": 0}

        for company in companies:
            mgr = User.objects.filter(company=company, role__in=["MANAGER", "ACCOUNTANT"]).first()
            if not mgr:
                self.stdout.write(self.style.WARNING(f"Pas d’utilisateur manager pour {company.nom}, ignoré."))
                continue

            AlertConfig.objects.get_or_create(
                company=company,
                is_active=True,
                defaults={"treasury_threshold": Decimal("5000.00"), "email_enabled": True},
            )

            bank = BankAccount.objects.filter(company=company, is_main=True).first()
            if not bank:
                bank = BankAccount.objects.create(
                    company=company,
                    name="Compte courant principal",
                    bank_name="Banque démo",
                    initial_balance=Decimal("12500.00"),
                    current_balance=Decimal("12500.00"),
                    is_main=True,
                )

            # — Prévisions (20) —
            for i in range(20):
                dt = today + timedelta(days=random.randint(1, 120))
                label, t = random.choice(FORECAST_LABELS)
                amt = (Decimal(random.randint(200, 8000)) / Decimal("1")).quantize(Decimal("0.01"))
                CashForecastItem.objects.create(
                    company=company,
                    date=dt,
                    description=f"{label} — {company.nom[:20]}",
                    amount=amt,
                    type=t,
                    category=DEMO_FORECAST_CAT,
                    is_actual=False,
                )
                total_created["fc"] += 1

            # — Transactions bancaires (25) —
            bal = bank.current_balance
            for i in range(25):
                d = today - timedelta(days=random.randint(0, 90))
                is_credit = random.random() > 0.45
                amt = (Decimal(random.randint(50, 4500)) / Decimal("10")).quantize(Decimal("0.01"))
                if is_credit:
                    bal += amt
                    tt = "CREDIT"
                else:
                    bal -= amt
                    tt = "DEBIT"
                BankTransaction.objects.create(
                    bank_account=bank,
                    date=d,
                    description=random.choice(BANK_LABELS),
                    amount=amt,
                    transaction_type=tt,
                    reconciled=random.random() > 0.7,
                    import_id=DEMO_TX_IMPORT,
                )
                total_created["tx"] += 1
            bank.current_balance = bal.quantize(Decimal("0.01"))
            bank.save(update_fields=["current_balance"])

            # — Écritures comptables (18) : ventes à crédit (actif/produit) ou charges (charge/passif) —
            for i in range(18):
                d = today - timedelta(days=random.randint(0, 200))
                ref = f"{DEMO_REF_PREFIX}{company.id}-{i}-{random.randint(1000, 9999)}"
                entry = AccountingEntry.objects.create(
                    company=company,
                    date=d,
                    description=random.choice(SERVICES),
                    reference=ref,
                    created_by=mgr,
                    validated=random.random() > 0.35,
                )
                amt = (Decimal(random.randint(500, 12000)) / Decimal("100")).quantize(Decimal("0.01"))
                if i % 2 == 0:
                    EntryLine.objects.create(entry=entry, account=actif, debit=amt, credit=Decimal("0.00"))
                    EntryLine.objects.create(entry=entry, account=prod, debit=Decimal("0.00"), credit=amt)
                else:
                    EntryLine.objects.create(entry=entry, account=charg, debit=amt, credit=Decimal("0.00"))
                    EntryLine.objects.create(entry=entry, account=passif, debit=Decimal("0.00"), credit=amt)
                total_created["entries"] += 1

            # — Devis (8) avec statuts variés —
            quote_statuses = [
                Quote.Status.DRAFT,
                Quote.Status.SENT,
                Quote.Status.ACCEPTED,
                Quote.Status.REFUSED,
                Quote.Status.EXPIRED,
            ]
            for i in range(8):
                client, _email = random.choice(CLIENTS)
                d = today - timedelta(days=random.randint(0, 45))
                q = Quote.objects.create(
                    company=company,
                    number=next_quote_number(company),
                    date=d,
                    valid_until=d + timedelta(days=30),
                    client_name=client,
                    status=random.choice(quote_statuses),
                    notes=DEMO_MARKER,
                )
                qty = Decimal("1.00")
                pu = (Decimal(random.randint(80, 2500)) / Decimal("1")).quantize(Decimal("0.01"))
                tax = Decimal("20.0")
                InvoiceLine.objects.create(
                    quote=q,
                    invoice=None,
                    description=random.choice(SERVICES),
                    quantity=qty,
                    unit_price=pu,
                    tax_rate=tax,
                )
                if random.random() > 0.3:
                    InvoiceLine.objects.create(
                        quote=q,
                        invoice=None,
                        description="Frais de déplacement",
                        quantity=Decimal("1"),
                        unit_price=Decimal("120.00"),
                        tax_rate=tax,
                    )
                recalc_totals_for_quote(q)
                total_created["quotes"] += 1

            # — Factures (12) avec statuts variés —
            inv_statuses = [
                Invoice.Status.DRAFT,
                Invoice.Status.SENT,
                Invoice.Status.PAID,
                Invoice.Status.OVERDUE,
            ]
            for i in range(12):
                client, _email = random.choice(CLIENTS)
                d = today - timedelta(days=random.randint(0, 120))
                due = d + timedelta(days=30)
                st = random.choice(inv_statuses)
                inv = Invoice.objects.create(
                    company=company,
                    number=next_invoice_number(company),
                    date=d,
                    due_date=due,
                    client_name=client,
                    status=st,
                    notes=DEMO_MARKER,
                    paid_at=now if st == Invoice.Status.PAID else None,
                    paid_amount=Decimal("0.00") if st != Invoice.Status.PAID else None,
                )
                pu = (Decimal(random.randint(500, 8000)) / Decimal("1")).quantize(Decimal("0.01"))
                InvoiceLine.objects.create(
                    invoice=inv,
                    quote=None,
                    description=random.choice(SERVICES),
                    quantity=Decimal("1"),
                    unit_price=pu,
                    tax_rate=Decimal("20.0"),
                )
                recalc_totals_for_invoice(inv)
                if st == Invoice.Status.PAID:
                    inv.paid_amount = inv.total_ttc
                    inv.save(update_fields=["paid_amount", "paid_at"])
                total_created["invoices"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Données démo créées : "
                f"{total_created['quotes']} devis, {total_created['invoices']} factures, "
                f"{total_created['entries']} écritures, {total_created['tx']} transactions, "
                f"{total_created['fc']} prévisions."
            )
        )
        self.stdout.write('Astuce : relancez avec --replace pour tout remplacer (même marqueur "__demo__").')
