# 🎉 Samba Fête — Gestion d'Événements Professionnels

## 📋 Table des Matières
1. [Objectif du Projet](#objectif)
2. [Architecture Technique](#architecture)
3. [Structure des Fichiers](#structure)
4. [Base de Données](#base-de-donnees)
5. [Fonctionnalités](#fonctionnalites)
6. [Authentification & Rôles](#authentification)
7. [Installation & Déploiement](#installation)
8. [API & Routes](#api)
9. [Exports](#exports)
10. [Maintenance & Support](#maintenance)

---

## 1. 🎯 Objectif du Projet

**Samba Fête** est une application web de gestion complète pour un hall d'événements basé à Constantine, Algérie. Elle permet de gérer:

- 📅 **Événements** — Mariages, fiançailles, anniversaires, conférences
- 👥 **Clients** — Fiches clients avec historique complet
- 💰 **Finances** — Paiements, dépenses, bénéfices
- 📄 **Documents** — Contrats PDF, reçus, rapports comptables
- 📊 **Statistiques** — Tableau de bord avec graphiques
- 📆 **Calendrier** — Disponibilités des salles en temps réel

**Client:** Samba Fête — 102 ZAM, Nouvelle Ville, Constantine, Algérie
**Téléphone:** 0550 50 37 67
**RC:** 034275305A | **NIF:** 1635

---

## 2. 🏗️ Architecture Technique

### Stack Technologique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| **Backend** | Python Flask | 3.0+ |
| **Base de données** | PostgreSQL | 14+ |
| **Frontend** | HTML5, CSS3, JavaScript | - |
| **CSS Framework** | Bootstrap 5 | 5.3+ |
| **PDF (Contrats)** | WeasyPrint | 60+ |
| **PDF (Reçus)** | ReportLab | 4.0+ |
| **Exports Tableur** | ODFPY | 1.4+ |
| **Hébergement** | Render.com | - |

### Architecture Client-Serveur

```
┌─────────────────┐     HTTPS      ┌─────────────────┐
│   Navigateur    │ ◄────────────► │   Render.com    │
│   (Flask App)   │                │   (Flask+PgSQL) │
└─────────────────┘                └─────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │   PostgreSQL    │
                                   │   (Données)     │
                                   └─────────────────┘
```

---

## 3. 📁 Structure des Fichiers

```
samba-fete/
├── app.py                    # Application principale Flask (routes)
├── models.py                 # Modèles de base de données
├── contract_generator.py     # Génération PDF des contrats
├── receipt_generator.py      # Génération des reçus
├── export_functions.py       # Export ODS (tableurs)
├── requirements.txt          # Dépendances Python
├── static/
│   ├── css/
│   │   └── style.css         # Styles CSS principaux
│   ├── js/
│   │   └── main.js           # JavaScript (sidebar, calendrier)
│   └── img/
│       └── logo.jpg          # Logo Samba Fête
├── templates/
│   ├── base.html             # Layout principal (header, sidebar, footer)
│   ├── index.html            # Tableau de bord
│   ├── event_form.html       # Formulaire événement (créer/modifier)
│   ├── event_detail.html     # Détail d'un événement
│   ├── events_list.html      # Liste des événements
│   ├── clients.html          # Liste des clients
│   ├── client_detail.html    # Détail client
│   ├── finances.html         # Vue financière
│   ├── accounting.html       # Comptabilité (P&L)
│   ├── expenses.html         # Gestion des dépenses
│   ├── calendar.html         # Calendrier des disponibilités
│   ├── login.html            # Page de connexion
│   ├── users.html            # Gestion des utilisateurs
│   └── settings.html         # Paramètres
└── README.md                 # Ce document
```

---

## 4. 🗄️ Base de Données

### Schéma des Tables

#### Table `clients`
| Colonne | Type | Description |
|---------|------|-------------|
| id | SERIAL | Clé primaire |
| name | TEXT | Nom complet |
| phone | TEXT | Téléphone principal |
| phone2 | TEXT | Téléphone secondaire |
| email | TEXT | Email |
| address | TEXT | Adresse |
| created_at | TIMESTAMP | Date de création |

#### Table `events`
| Colonne | Type | Description |
|---------|------|-------------|
| id | SERIAL | Clé primaire |
| title | TEXT | Titre de l'événement |
| client_id | INTEGER | FK → clients |
| venue_id | INTEGER | FK → venues |
| venue_id2 | INTEGER | FK → venues (optionnel) |
| event_type | TEXT | Mariage, Fiançailles, etc. |
| event_date | DATE | Date de l'événement |
| time_slot | TEXT | Déjeuner, Après-midi, Dîner |
| guests_men | INTEGER | Nombre d'hommes |
| guests_women | INTEGER | Nombre de femmes |
| status | TEXT | en attente, confirmé, terminé, annulé |
| notes | TEXT | Notes |
| total_amount | NUMERIC | Montant total |
| deposit_required | NUMERIC | Acompte requis |
| created_at | TIMESTAMP | Date de création |
| updated_at | TIMESTAMP | Date de modification |

#### Table `payments`
| Colonne | Type | Description |
|---------|------|-------------|
| id | SERIAL | Clé primaire |
| event_id | INTEGER | FK → events |
| amount | NUMERIC | Montant |
| payment_type | TEXT | Acompte, Solde, Autre |
| method | TEXT | Espèces, Chèque, Virement, Carte |
| reference | TEXT | Référence du paiement |
| notes | TEXT | Notes |
| payment_date | TIMESTAMP | Date du paiement |
| is_refunded | INTEGER | 0=non, 1=remboursé |

#### Table `event_lines`
| Colonne | Type | Description |
|---------|------|-------------|
| id | SERIAL | Clé primaire |
| event_id | INTEGER | FK → events |
| description | TEXT | Description du service |
| amount | NUMERIC | Montant |
| is_cost | INTEGER | 0=revenu, 1=coût |

#### Table `expenses`
| Colonne | Type | Description |
|---------|------|-------------|
| id | SERIAL | Clé primaire |
| event_id | INTEGER | FK → events |
| category | TEXT | Catégorie (Serveurs, Sécurité, etc.) |
| description | TEXT | Description |
| amount | NUMERIC | Montant |
| expense_date | TEXT | Date de la dépense |
| method | TEXT | Méthode de paiement |
| reference | TEXT | Référence |
| notes | TEXT | Notes |
| created_at | TIMESTAMP | Date de création |

#### Table `venues`
| Colonne | Type | Description |
|---------|------|-------------|
| id | SERIAL | Clé primaire |
| name | TEXT | Nom de la salle |
| capacity_men | INTEGER | Capacité hommes |
| capacity_women | INTEGER | Capacité femmes |
| is_active | INTEGER | 1=active, 0=inactive |

#### Table `settings`
| Colonne | Type | Description |
|---------|------|-------------|
| key | TEXT | Clé (PRIMARY KEY) |
| value | TEXT | Valeur |

#### Table `users`
| Colonne | Type | Description |
|---------|------|-------------|
| id | SERIAL | Clé primaire |
| username | TEXT | Nom d'utilisateur (UNIQUE) |
| password_hash | TEXT | Mot de passe hashé |
| role | TEXT | admin ou manager |
| is_active | INTEGER | 1=actif, 0=inactif |
| created_at | TIMESTAMP | Date de création |

### Relations entre Tables

```
clients (1) ──── (N) events
venues  (1) ──── (N) events
events  (1) ──── (N) payments
events  (1) ──── (N) event_lines
events  (1) ──── (N) expenses
```

---

## 5. ✨ Fonctionnalités

### 📊 Tableau de Bord
- Statistiques mensuelles (revenus, dépenses, profit)
- Graphiques Revenus vs Dépenses (6 mois)
- Graphique Évolution du Profit (6 mois)
- Liste des événements à venir
- Paiements récents
- Alertes événements en attente (>48h)

### 📅 Gestion des Événements
- Création avec formulaire complet
- Informations client auto-populées
- Sélection de salle (primaire + secondaire)
- Services prédéfinis (Location, Café, Photo, Déco, etc.)
- Lignes personnalisées (devis)
- Suivi des statuts: en attente → confirmé → terminé/annulé
- Calendrier visuel des disponibilités

### 💰 Gestion Financière
- Suivi des paiements (acompte, solde)
- Dépenses par catégorie (Serveurs, Nettoyeurs, Sécurité, Autre)
- Calcul automatique des bénéfices
- Historique des paiements par client

### 📄 Documents
- **Contrat PDF** — 1 page, professionnel, avec toutes les clauses
- **Reçu PDF** — Pour chaque paiement
- **Factures** — Récapitulatif financier

### 📊 Rapports Comptables
- Compte de Résultat (P&L)
- Revenus par type d'événement
- Top 10 clients
- Dépenses par catégorie
- Rapports mensuels

### 📤 Exports
- Événements → ODS
- Clients → ODS
- Paiements → ODS
- Dépenses → ODS
- Rapport P&L → ODS

---

## 6. 🔐 Authentification & Rôles

### Rôles et Permissions

| Fonctionnalité | Admin | Manager |
|----------------|-------|---------|
| Tableau de bord | ✅ | ✅ |
| Créer événement | ✅ | ✅ |
| Modifier événement | ✅ | ✅ |
| Supprimer événement | ✅ | ❌ |
| Ajouter paiement | ✅ | ✅ |
| Rembourser | ✅ | ❌ |
| Ajouter dépense | ✅ | ✅ |
| Exporter données | ✅ | ❌ |
| Paramètres | ✅ | ❌ |
| Gérer utilisateurs | ✅ | ❌ |

### Connexion par Défaut
- **Admin:** username: `admin`, password: `admin123`
- ⚠️ Changer le mot de passe après première connexion!

### Sécurité
- Mots de passe hashés avec werkzeug (PBKDF2 + salt)
- Sessions sécurisées avec Flask-Login
- Protection CSRF avec Flask secret key
- Toutes les routes protégées par @login_required

---

## 7. 🚀 Installation & Déploiement

### Prérequis
- Python 3.11+
- PostgreSQL 14+
- Pip

### Installation Locale

```bash
# 1. Cloner le repository
git clone https://github.com/Aramoul23/Samba-fete-.git
cd Samba-fete-

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer la base de données
export DATABASE_URL="postgresql://user:password@localhost:5432/samba_fete"

# 4. Lancer l'application
python app.py

# 5. Ouvrir le navigateur
# http://localhost:5000
```

### Déploiement sur Render.com

1. **Créer un compte** sur [dashboard.render.com](https://dashboard.render.com)

2. **Créer la base PostgreSQL:**
   - New → PostgreSQL
   - Nom: `samba-fete-db`
   - Plan: Free
   - Créer

3. **Déployer l'application:**
   - New → Web Service
   - Connecter le repo GitHub: `Aramoul23/Samba-fete-`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py`

4. **Ajouter la variable d'environnement:**
   - Settings → Environment Variables
   - Clé: `DATABASE_URL`
   - Valeur: URL interne de la base PostgreSQL

5. **Déployer!**

### Mise à jour

```bash
# Pousser les modifications
git add -A
git commit -m "Description des changements"
git push

# Render auto-redéploie
```

---

## 8. 🛤️ Routes API

### Pages Principales
| Route | Méthode | Description |
|-------|---------|-------------|
| `/` | GET | Tableau de bord |
| `/login` | GET/POST | Connexion |
| `/logout` | GET | Déconnexion |

### Événements
| Route | Méthode | Description |
|-------|---------|-------------|
| `/evenements` | GET | Liste des événements |
| `/evenement/nouveau` | GET/POST | Créer un événement |
| `/evenement/<id>` | GET | Détail d'un événement |
| `/evenement/<id>/modifier` | GET/POST | Modifier un événement |
| `/evenement/<id>/supprimer` | POST | Supprimer un événement |
| `/evenement/<id>/statut` | POST | Changer le statut |
| `/evenement/<id>/paiement` | POST | Ajouter un paiement |
| `/evenement/<id>/depense` | POST | Ajouter une dépense |
| `/evenement/<id>/contrat` | GET | Télécharger contrat PDF |
| `/evenement/<id>/recu/<pid>` | GET | Télécharger reçu PDF |

### Clients
| Route | Méthode | Description |
|-------|---------|-------------|
| `/clients` | GET | Liste des clients |
| `/client/<id>` | GET | Détail client |

### Finances
| Route | Méthode | Description |
|-------|---------|-------------|
| `/finances` | GET | Vue financière |
| `/comptabilite` | GET | Comptabilité P&L |
| `/depenses` | GET | Liste des dépenses |

### Utilisateurs (Admin only)
| Route | Méthode | Description |
|-------|---------|-------------|
| `/parametres` | GET | Paramètres |
| `/utilisateurs` | GET | Gestion des utilisateurs |
| `/utilisateur/nouveau` | POST | Créer un utilisateur |
| `/utilisateur/<id>/modifier` | POST | Modifier un utilisateur |
| `/utilisateur/<id>/supprimer` | POST | Supprimer un utilisateur |

### Exports
| Route | Méthode | Description |
|-------|---------|-------------|
| `/export/events.ods` | GET | Export événements |
| `/export/clients.ods` | GET | Export clients |
| `/export/payments.ods` | GET | Export paiements |
| `/export/expenses.ods` | GET | Export dépenses |
| `/export/financials.ods` | GET | Export financiers |
| `/export/pl_report.ods` | GET | Rapport P&L |

### Calendrier & API
| Route | Méthode | Description |
|-------|---------|-------------|
| `/calendrier` | GET | Vue calendrier |
| `/api/calendar/events` | GET | Données calendrier (JSON) |
| `/api/deactivate-venue/<id>` | POST | Désactiver une salle |

---

## 9. 📤 Exports

### Formats Disponibles
- **ODS** (OpenDocument Spreadsheet) — Compatible LibreOffice, Google Sheets, Excel

### Données Exportées
| Export | Colonnes |
|--------|----------|
| Événements | Date, Titre, Client, Type, Salle, Statut, Montant, Payé, Reste |
| Clients | Nom, Téléphone, Email, Événements, Total payé, Reste |
| Paiements | Date, Événement, Client, Montant, Type, Méthode, Référence |
| Dépenses | Date, Catégorie, Description, Montant, Événement |
| P&L | Mois, Revenus, Dépenses, Bénéfice, Marge |

---

## 10. 🔧 Maintenance & Support

### Fichiers de Configuration

**requirements.txt:**
```
flask>=3.0.0
odfpy>=1.4.1
reportlab>=4.0
psycopg2-binary>=2.9.0
weasyprint>=60.0
```

### Variables d'Environnement

| Variable | Description | Exemple |
|----------|-------------|---------|
| `DATABASE_URL` | URL de connexion PostgreSQL | `postgresql://user:pass@host/db` |
| `SECRET_KEY` | Clé de session Flask | `random-secret-key` |
| `FLASK_ENV` | Environnement | `production` |

### Sauvegarde de la Base de Données

```bash
# Export
pg_dump -h host -U user dbname > backup.sql

# Import
psql -h host -U user dbname < backup.sql
```

### Dépannage

| Problème | Solution |
|----------|----------|
| Erreur "ModuleNotFoundError" | Vérifier requirements.txt |
| Erreur "column does not exist" | Vérifier schéma PostgreSQL |
| Page ne charge pas | Vérifier logs Render |
| PDF ne génère pas | Vérifier weasyprint installé |

### Contacts

- **Développeur:** Ali Ramoul (@ramsysschool)
- **Entreprise:** Samba Fête, Constantine, Algérie
- **Support:** Par GitHub Issues

---

## 📝 Notes de Version

### v2.0 (Mars 2026)
- Migration SQLite → PostgreSQL
- Interface mobile optimisée (iPhone/Android)
- Authentification Admin/Manager
- Exports ODS
- Contrat PDF 1 page avec WeasyPrint

### v1.0 (Février 2026)
- Version initiale avec SQLite
- Fonctionnalités de base

---

## 📄 Licence

Propriétaire — Samba Fête, Constantine, Algérie

---

*Document généré le 25 Mars 2026 — Samba Fête © 2026*
