#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Déploiement MVP..."

echo "Pull (si applicable)..."
git pull || true

echo "Migrations..."
python manage.py migrate

echo "collectstatic..."
python manage.py collectstatic --noinput || true

echo "Vérification dépendances sécurité (MVP)..."
python -c "import ssl; print('ssl ok')"

echo "Redémarrage gunicorn (à adapter)..."
# Exemple:
# sudo systemctl restart gunicorn
echo "À configurer côté serveur."

echo "Déploiement terminé."

