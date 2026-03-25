# ComptaNextGen (Solution PME) - Django

## Prérequis
- Python 3.10+
- PostgreSQL (ou SQLite en dev)
- Node.js (pour builder Tailwind via npm)

## Installation
1. Créer un environnement virtuel :
   - Optionnel : exécuter `scripts/setup_dev.sh`
2. Installer les dépendances :
   - `pip install -r requirements.txt`
3. Configurer les variables d'environnement :
   - Copier `./.env.example` vers `./.env`
4. Base de données :
   - Par défaut : SQLite si `DATABASE_URL` est vide
   - En prod : PostgreSQL via `DATABASE_URL`
5. Générer la CSS Tailwind :
   - `npm install`
   - `npm run build:css`
6. Migrations et données :
   - `python manage.py makemigrations`
   - `python manage.py migrate`
   - `python manage.py loaddata fixtures/initial_data.json`

## Variables d'environnement
Fichier : `.env`
- `SECRET_KEY` (obligatoire)
- `DEBUG` (booléen)
- `ALLOWED_HOSTS` (liste séparée par virgules)
- `DATABASE_URL`
  - format PostgreSQL : `postgresql://USER:PASSWORD@HOST:5432/NAME`
- `ENCRYPTION_KEY` (clé Fernet valide)
- `EMAIL_BACKEND` (dev: console backend recommandé)
- `DEFAULT_FROM_EMAIL`

## Identifiants (dev) via la fixture minimale
**Mot de passe commun à tous les comptes ci-dessous :** `Aa!234567`

| Email | Rôle | Entreprise / remarque |
|--------|------|------------------------|
| `admin@comptanextgen.fr` | CABINET_ADMIN (superuser) | Aucune entreprise fixe ; « Admin Dashboard » + accès à toutes les données ; [Django admin](http://127.0.0.1:8000/admin/) |
| `gerant.alpha@alpha.fr` | MANAGER | Alpha SARL |
| `comptable.alpha@alpha.fr` | ACCOUNTANT | Alpha SARL |
| `collab.alpha@alpha.fr` | COLLABORATOR | Alpha SARL |
| `gerant.beta@beta.fr` | MANAGER | Beta SAS |
| `comptable.beta@beta.fr` | ACCOUNTANT | Beta SAS |
| `gerant.gamma@gamma.fr` | MANAGER | Gamma EURL |
| `comptable.gamma@gamma.fr` | ACCOUNTANT | Gamma EURL |

### Accéder aux différentes interfaces
1. Ouvrez **http://127.0.0.1:8000/login/** (ou la page d’accueil qui redirige vers le tableau de bord si déjà connecté).
2. Connectez-vous avec l’email voulu et le mot de passe ci-dessus.
3. Utilisez le **menu latéral** (Dashboard, Comptabilité, Facturation, Trésorerie, Reporting). Le rôle **cabinet** voit aussi **Admin Dashboard** (gestion des entreprises) et peut accéder à **Django Admin** (`/admin/`) avec le compte `admin@comptanextgen.fr`.
4. Pour **changer d’utilisateur** : lien **Déconnexion** en haut à droite, puis reconnectez-vous avec un autre compte (ou utilisez une fenêtre de navigation privée pour deux sessions en parallèle).

En mode **DEBUG**, la page de connexion affiche un rappel des comptes démo.

## Générer des données démo
- `./scripts/create_demo_data.sh`

## Lancer le serveur
- En local : `python manage.py runserver` puis ouvrir **http://127.0.0.1:8000/** ou **http://localhost:8000/**
- **Depuis un autre appareil (téléphone, autre PC)** sur le même réseau :
  1. Lancer : `python manage.py runserver 0.0.0.0:8000`
  2. Utiliser l’URL `http://<IP_DE_VOTRE_PC>:8000/` (ex. `http://192.168.1.42:8000/`)
  3. Avec un fichier `.env`, laissez `ALLOWED_HOSTS` vide en dev (voir `.env.example`) pour éviter l’erreur **DisallowedHost** ; ou listez votre IP explicitement.

### Le site est « inaccessible »
- Vérifier que le terminal affiche bien `Starting development server` (pas d’erreur au démarrage).
- Vérifier l’URL : le serveur par défaut n’écoute que sur cette machine (`127.0.0.1`), pas depuis Internet sans déploiement réel.
- Si le navigateur affiche une erreur liée au **Host** / **DisallowedHost** : mettre à jour `ALLOWED_HOSTS` ou laisser ce champ vide en dev (voir ci-dessus).

## Tests
- `python manage.py test`

## API banque simulée
- `GET /api/bank-simulator/<company_id>/` (identifiant numérique en base)

## Sélection d’entreprise (rôle cabinet)
- Dans l’interface, le paramètre d’URL utilisé est `company_name` (nom exact de l’entreprise, insensible à la casse), par ex. `?company_name=Alpha%20SARL`.
- L’ancien paramètre `company_id` reste accepté en secours pour les liens ou scripts existants.

## Structure (résumé)
- `comptanextgen/` : configuration Django
- `apps/core/` : authentification + audit trail + dashboard
- `apps/accounting/` : comptabilité (lot suivant)
- `apps/invoicing/` : facturation (lot suivant)
- `apps/treasury/` : trésorerie (lot suivant)
- `apps/reporting/` : reporting (lot suivant)

## Notes
Ce projet est livré en plusieurs lots (scaffolding, comptabilité, facturation, trésorerie, reporting) pour rester itératif et validable.

### Export PDF (factures)
WeasyPrint dépend de bibliothèques système (souvent absentes sous Windows). Si la génération PDF échoue, l’application affiche une **page imprimable** de la facture : utilisez **Ctrl+P** puis **Enregistrer au format PDF** (ou « Microsoft Print to PDF »).

# comptanextgen
