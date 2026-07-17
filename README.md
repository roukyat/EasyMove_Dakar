# EasyMove Sénégal — Version full-stack (SQL + Python + Carte interactive)

Ce dossier contient la version complète du projet, avec une vraie architecture
3-tiers :

```
Navigateur (HTML/CSS/JS + carte Leaflet)
        ↕
Serveur Python (Flask)  →  app.py
        ↕
Base de données SQL (SQLite)  →  easymove.db (générée depuis sql/schema.sql + sql/donnees.sql)
```

## 1. Structure du projet

```
easymovedakar/
├── app.py                 → Application Flask : toutes les routes du site
├── database.py             → Fonctions Python qui parlent à la base SQL
├── easymove.db             → Base de données SQLite (générée automatiquement)
├── sql/
│   ├── schema.sql           → Création des tables (DDL)
│   └── donnees.sql          → Données de départ (DML)
├── templates/               → Pages HTML (Jinja2), le design est conservé
│   ├── base.html             → Navbar + footer communs à toutes les pages
│   ├── index.html
│   ├── transports.html
│   ├── trajets.html
│   ├── resultat_trajet.html  → Page avec la carte interactive
│   ├── prix.html
│   ├── conseils.html
│   ├── wolof.html
│   └── contact.html
└── static/
    └── css/style.css        → Le design (réutilisé depuis ta version originale)
```

## 2. Comment lancer le site en local

Il te faut Python 3 installé. Ensuite, dans un terminal :

```bash
cd easymovedakar
pip install flask
python app.py
```

Puis ouvre ton navigateur à l'adresse : **http://127.0.0.1:5000**

Au premier lancement, `app.py` crée automatiquement le fichier `easymove.db`
à partir de `sql/schema.sql` et `sql/donnees.sql`. Si tu modifies les
données et veux repartir de zéro, supprime simplement `easymove.db` et
relance `python app.py`.

## 3. La base de données SQL

9 tables, reliées par des clés étrangères :

| Table              | Rôle |
|--------------------|------|
| `lieux`            | Tous les points sur la carte (quartiers, villes, aéroport...) |
| `moyens_transport` | Taxi, DDD, Car rapide, Minibus Tata, Jakarta, TER, BRT |
| `lignes_bus`       | Les lignes précises (ex: Ligne 14 Plateau–UCAD) |
| `arrets`           | Les arrêts physiques, reliés à un lieu |
| `ligne_arrets`     | Association ligne ↔ arrêts (avec ordre de passage) |
| `trajets`          | Un trajet = un lieu de départ + un lieu d'arrivée |
| `trajet_options`   | Pour un trajet donné, les différentes façons de le faire (prix, durée, étapes) |
| `phrases_wolof`    | Guide de conversation |
| `conseils`         | Conseils pratiques par catégorie et période |
| `infos_utiles`     | Numéros d'urgence, objets à emporter |

Tu peux ouvrir `easymove.db` avec [DB Browser for SQLite](https://sqlitebrowser.org/)
pour visualiser et modifier les données sans toucher au code.

## 4. Le rôle de Python (Flask)

`app.py` définit une route par page (ex: `/transports`), qui va chercher les
données correspondantes dans `database.py`, puis les transmet au template
HTML pour affichage — c'est le principe MVC (Modèle / Vue / Contrôleur).

La partie la plus intéressante est `/trajets/resultat` : quand un
utilisateur choisit un départ et une arrivée, Flask interroge la base pour
trouver un trajet correspondant (`database.rechercher_trajet`), puis
transmet les coordonnées GPS au template pour dessiner la carte.

Il y a aussi deux routes API (`/api/lieux` et `/api/rechercher-trajet`) qui
renvoient du JSON — utile si tu veux plus tard connecter une application
mobile ou un JavaScript plus poussé.

## 5. La carte interactive

Elle utilise **Leaflet.js** (librairie JS gratuite et open-source, basée sur
les fonds de carte OpenStreetMap) directement dans `resultat_trajet.html` :
- un marqueur 📍 pour le départ,
- un marqueur 🎯 pour l'arrivée,
- une ligne entre les deux représentant le trajet.

Ceci nécessite une connexion internet quand le site est ouvert dans un
navigateur (pour charger les tuiles de la carte et la librairie Leaflet).

## 6. Idées pour aller plus loin

- Ajouter un vrai calcul d'itinéraire (API OpenRouteService / OSRM) au lieu
  d'une ligne droite entre les deux points.
- Ajouter une table `utilisateurs` + formulaire de contact avec enregistrement
  en base.
- Ajouter une page d'administration pour éditer les trajets sans toucher au SQL.
