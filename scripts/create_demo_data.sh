#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Création données démo (MVP)..."
python manage.py shell -c "
import random
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

from core.models import Company, User
from accounting.models import ChartOfAccount, AccountingEntry, EntryLine
from invoicing.models import Quote, Invoice, InvoiceLine
from treasury.models import BankAccount, BankTransaction, CashForecastItem
from invoicing.utils import next_quote_number, next_invoice_number, recalc_totals_for_quote, recalc_totals_for_invoice

now = timezone.now()
accounts = list(ChartOfAccount.objects.filter(is_active=True))
if not accounts:
  print('Aucun compte comptable : lancez la fixture initiale.')
  raise SystemExit(1)

charg = ChartOfAccount.objects.filter(type='CHARGE', is_active=True).first()
prod = ChartOfAccount.objects.filter(type='PRODUIT', is_active=True).first()
actif = ChartOfAccount.objects.filter(type='ACTIF', is_active=True).first()
passif = ChartOfAccount.objects.filter(type='PASSIF', is_active=True).first()

if not (charg and prod and actif and passif):
  print('Comptes ACTIF/PASSIF/CHARGE/PRODUIT insuffisants.')
  raise SystemExit(1)

for company in Company.objects.filter(is_active=True):
  mgr = User.objects.filter(company=company, role__in=['MANAGER','ACCOUNTANT']).first()
  if not mgr:
    continue

  # Banque
  bank = BankAccount.objects.filter(company=company).first()
  if not bank:
    bank = BankAccount.objects.create(company=company, name='Compte démo', bank_name='Demo', initial_balance=Decimal('1000.00'), current_balance=Decimal('1000.00'), is_main=True)

  # Prévisions
  for i in range(10):
    dt = (now + timedelta(days=i*3)).date()
    t = random.choice(['INCOME','EXPENSE'])
    amt = Decimal(random.randint(50, 500)) * Decimal('1.00')
    if t == 'EXPENSE':
      amt = amt
    CashForecastItem.objects.create(company=company, date=dt, description='Prévision démo', amount=amt, type=t, category='DÉMO', is_actual=False)

  # Transactions bancaires
  for i in range(10):
    BankTransaction.objects.create(
      bank_account=bank,
      date=(now - timedelta(days=random.randint(0,25))).date(),
      description='Txn démo',
      amount=Decimal(random.randint(50, 2500))/Decimal('10'),
      transaction_type=random.choice(['DEBIT','CREDIT']),
      reconciled=False,
      import_id='demo'
    )

  # Comptabilité : 10 écritures
  for i in range(10):
    entry = AccountingEntry.objects.create(
      company=company,
      date=(now - timedelta(days=random.randint(0,180))).date(),
      description='Ecriture démo',
      reference=f'DEM-{i}',
      created_by=mgr,
      validated=(i % 2 == 0),
      created_at=now
    )
    amt = Decimal(random.randint(100, 900)) / Decimal('10')
    EntryLine.objects.create(entry=entry, account=charg, debit=amt, credit=Decimal('0.00'))
    EntryLine.objects.create(entry=entry, account=prod, debit=Decimal('0.00'), credit=amt)

  # Devis + factures : 5
  for i in range(5):
    qt = Quote.objects.create(
      company=company,
      number=next_quote_number(company),
      date=(now - timedelta(days=random.randint(0,60))).date(),
      valid_until=(now + timedelta(days=30)).date(),
      client_name='Client démo',
      status='DRAFT',
      notes=''
    )
    InvoiceLine.objects.create(quote=qt, invoice=None, description='Ligne démo', quantity=Decimal('1.00'), unit_price=Decimal('100.00'), tax_rate=Decimal('20.0'))
    recalc_totals_for_quote(qt)

    inv = Invoice.objects.create(
      company=company,
      number=next_invoice_number(company),
      date=qt.date,
      due_date=qt.valid_until,
      client_name=qt.client_name,
      status='SENT',
      notes=''
    )
    InvoiceLine.objects.create(invoice=inv, quote=None, description='Ligne démo', quantity=Decimal('1.00'), unit_price=Decimal('100.00'), tax_rate=Decimal('20.0'))
    recalc_totals_for_invoice(inv)
"

echo "Données démo créées."

