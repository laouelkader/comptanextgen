from __future__ import annotations

import csv
import io
import random
from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
from django.utils import timezone

def simulate_bank_transactions(company_id: int, count: int = 10):
    """
    API simulée : renvoie des transactions aléatoires (MVP).
    """
    today = timezone.now().date()
    txs = []
    for i in range(count):
        date = today - timedelta(days=random.randint(0, 25))
        transaction_type = random.choice(["DEBIT", "CREDIT"])
        amount = Decimal(str(random.randint(50, 2500) / 10)).quantize(Decimal("0.01"))
        desc = random.choice(["Virement", "Paiement", "Facture", "Achat", "Service"])
        txs.append(
            {
                "date": date.isoformat(),
                "description": desc,
                "amount": str(amount),
                "transaction_type": transaction_type,
            }
        )
    return txs


def simple_transaction_suggestion(amount: Decimal, date, existing_transactions):
    """
    MVP : suggère 1 transaction si montant et date sont compatibles.
    """
    candidates = []
    for t in existing_transactions:
        if not t.reconciled and abs(t.amount - amount) <= Decimal("0.01") and t.date == date:
            candidates.append(t)
    return candidates[0] if candidates else None


def import_transactions_from_csv(file_bytes: bytes):
    """
    MVP : parse CSV avec colonnes: date, description, amount, transaction_type
    """
    decoded = file_bytes.decode("utf-8", errors="ignore")
    f = io.StringIO(decoded)
    reader = csv.DictReader(f)
    rows = list(reader)
    parsed = []
    for r in rows:
        raw_date = (r.get("date") or "").strip()
        parsed_date = datetime.fromisoformat(raw_date).date() if raw_date else timezone.now().date()
        parsed.append(
            {
                "date": parsed_date,
                "description": r.get("description", ""),
                "amount": Decimal(str(r.get("amount", "0"))),
                "transaction_type": (r.get("transaction_type", "DEBIT") or "DEBIT").upper(),
            }
        )
    return parsed


def import_transactions_from_excel(file_bytes: bytes):
    """
    Parse XLSX avec colonnes attendues:
    - date
    - description
    - amount
    - transaction_type
    """
    bio = io.BytesIO(file_bytes)
    df = pd.read_excel(bio)
    # normalise colonnes
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = {"date", "description", "amount", "transaction_type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes: {', '.join(sorted(missing))}")

    parsed = []
    for _, row in df.iterrows():
        raw_date = row.get("date")
        if pd.isna(raw_date):
            parsed_date = timezone.now().date()
        elif hasattr(raw_date, "date"):
            parsed_date = raw_date.date()
        else:
            parsed_date = datetime.fromisoformat(str(raw_date)).date()

        parsed.append(
            {
                "date": parsed_date,
                "description": "" if pd.isna(row.get("description")) else str(row.get("description")),
                "amount": Decimal(str(row.get("amount") if not pd.isna(row.get("amount")) else "0")),
                "transaction_type": str(row.get("transaction_type") if not pd.isna(row.get("transaction_type")) else "DEBIT").upper(),
            }
        )
    return parsed

