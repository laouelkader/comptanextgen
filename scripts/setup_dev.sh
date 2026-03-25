#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Installation dépendances Python..."
python -m venv venv || true
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null || true
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Build CSS Tailwind (npm)..."
if command -v npm >/dev/null 2>&1; then
  npm install
  npm run build:css
else
  echo "npm introuvable : saute build CSS."
fi

echo "Migrations Django..."
python manage.py makemigrations
python manage.py migrate

echo "Chargement fixture initiale..."
python manage.py loaddata fixtures/initial_data.json || true

echo "Création superuser (si absent)..."
python manage.py shell -c "
from django.contrib.auth.hashers import make_password
from core.models import User
email='admin@comptanextgen.fr'
pwd='Aa!234567'
defaults=dict(
  is_active=True,
  role='CABINET_ADMIN',
)
u,created=User.objects.get_or_create(email=email, defaults=defaults)
if created:
  u.set_password(pwd)
  u.save()
"

echo "Terminé. Lancer: python manage.py runserver"

