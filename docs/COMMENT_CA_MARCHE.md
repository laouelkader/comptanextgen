# ComptaNextGen — Comment ça marche (pour les non-comptables)

Ce document explique **l’idée générale** du projet et **comment les écrans s’enchaînent**, sans supposer que vous maîtrisez la comptabilité. Pour l’installation technique, voir le `README.md` à la racine du projet.

---

## 1. À quoi sert cette application ?

**ComptaNextGen** est une application web de **gestion pour petites structures** (PME, TPE, cabinets qui accompagnent plusieurs entreprises). Elle regroupe dans un même site :

- de la **facturation** (devis, factures clients) ;
- un peu de **comptabilité** (écritures, bilan / résultat simplifiés) ;
- la **trésorerie** (comptes bancaires, mouvements, prévisions) ;
- du **reporting** (graphiques, alertes).

En pratique : vous **enregistrez ce qui se passe** (ventes, paiements, opérations bancaires) et l’outil **calcule des totaux** et **affiche des tableaux de bord** pour voir si tout tient debout.

---

## 2. Les rôles : qui fait quoi ?

| Rôle | Idée simple |
|------|-------------|
| **MANAGER / ACCOUNTANT / COLLABORATOR** | Utilisateurs rattachés à **une entreprise**. Ils voient les données de **leur** société. **Gérant** et **comptable** ont les mêmes droits « sensibles » (validation d’écritures, conversion devis→facture, imports bancaires, rapprochement, prévisions, paramètres d’alertes, exports Excel/PDF états & factures, export reporting global). Le **collaborateur** peut saisir et consulter, mais pas ces actions réservées. |
| **CABINET_ADMIN** | Compte « direction du cabinet » : peut **passer d’une entreprise cliente à l’autre** (souvent via le nom d’entreprise dans l’URL ou les listes). Accès aussi à un **Admin Dashboard** (gestion des entreprises côté cabinet). |
| **Compte admin Django** (`admin@…`) | Accès technique à l’**interface d’administration Django** (`/admin/`), en plus du reste si besoin. |

Le mot de passe de démonstration des comptes de test est indiqué dans le `README.md`.

---

## 3. Le fil conducteur : de la vente à l’argent (vue métier)

Imaginez une **chaîne** :

1. **Devis** — proposition de prix pour un client (pas encore une facture).
2. **Facture** — document qui dit « vous nous devez X € » (souvent avec TVA).
3. **Paiement / banque** — l’argent entre ou sort du **compte bancaire** (virement, prélèvement, etc.).
4. **Comptabilité** — pour les entreprises qui tiennent des comptes : des **écritures** enregistrent les mouvements selon un **plan comptable** (numéros de comptes : charges, produits, etc.).

L’application ne remplace pas un expert-comptable pour les obligations légales, mais elle **structure** ces étapes dans l’interface.

---

## 4. Les modules du menu (sans jargon inutile)

### Dashboard

- **Page d’accueil** après connexion : quelques **chiffres clés** (chiffre d’affaires du mois, solde de trésorerie, nombre de factures non payées, etc.).
- **Actions rapides** : raccourcis vers « nouvelle facture », « nouveau devis », trésorerie, listes, etc.
- **Alertes** : messages du type « attention à… » (seuils, retards, etc. — selon ce qui est configuré).

### Comptabilité

- **Écritures** : liste des opérations comptables saisies (date, libellé, validée ou non).
- **États financiers (MVP)** : vue **simplifiée** de **bilan** et **compte de résultat** sur une période — en résumé : ce que l’entreprise « a » / « doit » et ce qu’elle a gagné ou perdu sur la période, avec des exports Excel/PDF possibles.

*Pour un non-comptable : pensez aux écritures comme à des **lignes dans un grand livre** : chaque ligne dit « tant sur le compte A, tant sur le compte B », et à la fin tout doit être **équilibré** (débit = crédit).*

### Facturation

- **Factures** : création, liste, filtres par statut (brouillon, envoyée, payée, en retard…), export Excel, **PDF** (ou page imprimable si le PDF système n’est pas disponible).
- **Devis** : même logique côté « proposition » ; un devis peut être **converti** en facture dans le flux prévu par l’app.

### Trésorerie

- **Tableau de bord trésorerie** : vue des **soldes** des comptes bancaires et des **prévisions** à venir.
- **Rapprochement** : faire correspondre les **mouvements bancaires** importés (fichier) avec la compta / le suivi interne (fonctionnalité de type « pointage »).
- **Prévisionnel** : courbe ou tableau des **entrées/sorties attendues** sur un horizon (ex. 90 jours).

### Reporting

- **Analytics** : graphiques (CA, clients, etc.) — utile pour **voir des tendances**.
- **Alertes** : paramétrage de **seuils** (par ex. solde minimum) et liste d’**alertes** actives.

### Cabinet (si vous êtes CABINET_ADMIN)

- **Admin Dashboard** : création / désactivation d’**entreprises** côté cabinet, vue d’ensemble.

---

## 5. Entreprise unique vs cabinet multi-entreprises

- Un utilisateur **classique** est lié à **une** entreprise : tout est filtré automatiquement.
- Un **cabinet** travaille avec **plusieurs** entreprises : il faut souvent **choisir l’entreprise** (liste déroulante ou paramètre `company_name` dans l’URL, comme expliqué dans le `README`). Les **actions rapides** du dashboard peuvent reprendre ce paramètre si vous l’avez mis dans l’URL du dashboard.

---

## 6. Données de démonstration

Pour **remplir** l’interface avec des exemples (clients fictifs, factures, banque, etc.) sans tout saisir à la main :

```bash
python manage.py create_demo_data
```

Avec remplacement d’une ancienne démo :

```bash
python manage.py create_demo_data --replace
```

(Cf. `README.md` — il faut en général avoir chargé la fixture initiale avant.)

---

## 7. Limites à avoir en tête (MVP)

- C’est un **produit en construction** : certaines parties sont marquées **MVP** (version minimale).
- La **comptabilité** et les **états** sont **simplifiés** : pour obligations légales, fiscalité ou audit, un **professionnel** reste la référence.
- **PDF factures** : sous Windows, si la génération PDF avancée échoue, l’app peut proposer une **page à imprimer** « en PDF » via le navigateur.

---

## 8. En résumé

1. Vous vous **connectez** avec un rôle (entreprise ou cabinet).
2. Vous utilisez le **menu** pour passer de la **facturation** à la **trésorerie** et au **reporting**.
3. Le **dashboard** centralise des **indicateurs** et des **raccourcis**.
4. Les **données démo** permettent de **tester** sans être comptable.

Pour les commandes (`migrate`, `runserver`, variables `.env`), tout est détaillé dans le **`README.md`**.
