from __future__ import annotations

import csv
import io
import random
from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd

from django.utils import timezone

from .models import BankTransaction


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


def suggest_entry_lines_for_transaction(
    tx: BankTransaction,
    *,
    days_window: int = 21,
    limit: int = 20,
) -> list[dict]:
    """
    Propose des lignes d'écriture (EntryLine) pour rapprocher une transaction bancaire :
    même société (via le compte), montant net (débit − crédit) proche du flux bancaire,
    date d'écriture dans une fenêtre autour de la date de transaction.
    Exclut les lignes déjà liées à une transaction rapprochée.
    """
    from apps.accounting.models import EntryLine

    company_id = tx.bank_account.company_id
    start = tx.date - timedelta(days=days_window)
    end = tx.date + timedelta(days=days_window)

    used_line_ids = set(
        BankTransaction.objects.filter(reconciled=True, reconciled_entry_id__isnull=False).values_list(
            "reconciled_entry_id", flat=True
        )
    )

    if tx.transaction_type == BankTransaction.Types.CREDIT:
        signed_bank = tx.amount
    else:
        signed_bank = -tx.amount

    qs = (
        EntryLine.objects.select_related("entry", "account")
        .filter(entry__company_id=company_id, entry__date__gte=start, entry__date__lte=end)
        .exclude(pk__in=used_line_ids)
    )

    candidates: list[tuple[Decimal, int, EntryLine]] = []
    for line in qs.iterator(chunk_size=200):
        net = line.debit - line.credit
        if abs(net - signed_bank) > Decimal("0.02") and abs(abs(net) - abs(tx.amount)) > Decimal("0.02"):
            continue
        day_diff = abs((line.entry.date - tx.date).days)
        amount_penalty = abs(net - signed_bank)
        score = day_diff * Decimal("1.0") + amount_penalty * Decimal("10.0")
        candidates.append((score, day_diff, line))

    candidates.sort(key=lambda x: (x[0], x[1]))
    out: list[dict] = []
    for score, day_diff, line in candidates[:limit]:
        net = line.debit - line.credit
        out.append(
            {
                "id": line.pk,
                "score": score,
                "day_diff": day_diff,
                "entry_date": line.entry.date.isoformat(),
                "entry_ref": line.entry.reference or "",
                "entry_description": (line.entry.description or "")[:120],
                "account": f"{line.account.account_number} — {line.account.name}",
                "debit": str(line.debit),
                "credit": str(line.credit),
                "net": str(net),
            }
        )
    return out


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

