#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

BACKUP_DIR="${BACKUP_DIR:-backups}"
mkdir -p "$BACKUP_DIR"

TS="$(date +'%Y%m%d_%H%M%S')"
OUT_JSON="$BACKUP_DIR/dump_${TS}.json"
OUT_GZ="$OUT_JSON.gz"

echo "Dumpdata -> $OUT_JSON"
python manage.py dumpdata --indent 2 > "$OUT_JSON"

echo "Compression gzip -> $OUT_GZ"
gzip -f "$OUT_JSON"

echo "Backup terminé."

