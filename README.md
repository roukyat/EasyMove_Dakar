# EasyMove Dakar — assistant de mobilité pour Dakar (Flask + SQLite + carte interactive)

EasyMove aide à trouver le meilleur moyen de transport entre deux points de
Dakar (Taxi, Clando, Tata, Car rapide, Ndiaga Ndiaye, Dakar Dem Dikk, BRT,
TER, Jakarta) sans avoir à connaître les lignes par cœur : un départ, une
arrivée, et le site calcule l'itinéraire, le prix estimé, la durée et les
correspondances éventuelles.

Architecture 3-tiers :

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
├── app.py                    → Application Flask : toutes les routes du site
├── database.py                → Fonctions Python qui parlent à la base SQL
├── itineraire.py               → Moteur de calcul d'itinéraire (graphe + Dijkstra)
├── easymove.db                 → Base de données SQLite (générée/mise à jour automatiquement)
├── requirements.txt             → Dépendances Python (Flask)
├── sql/
│   ├── schema.sql                → Création des tables (DDL)
│   └── donnees.sql               → Données de départ (DML)
├── templates/                   → Pages HTML (Jinja2)
│   ├── base.html                   → Navbar + footer communs à toutes les pages
│   ├── index.html                  → Accueil
│   ├── trajets.html                → Recherche de trajet + favoris
│   ├── resultat_trajet.html        → Résultat de recherche, avec la carte interactive
│   ├── minibus.html                → Carte complète du réseau Tata
│   ├── transports.html             → Comparatif des moyens de transport
│   ├── prix.html                   → Estimation des prix
│   ├── historique.html             → Historique des recherches
│   ├── conseils.html               → Conseils pratiques
│   ├── wolof.html                  → Lexique wolof pour les transports
│   ├── apropos.html                → Présentation du projet
│   ├── 404.html                    → Page d'erreur "page introuvable"
│   └── _icons.html                 → Macros Jinja réutilisables (icônes par transport/catégorie)
└── static/
    ├── css/style.css             → Le design du site
    └── img/                      → Photos des moyens de transport
```

## 2. Comment lancer le site en local

Il faut Python 3 installé. Ensuite, dans un terminal :

```bash
cd easymovedakar
pip install -r requirements.txt
python app.py
```

Puis ouvre ton navigateur à l'adresse : **http://127.0.0.1:5000**

Au premier lancement, `app.py` crée automatiquement le fichier `easymove.db`
à partir de `sql/schema.sql` et `sql/donnees.sql`. À chaque démarrage
suivant, `database.py` vérifie et met aussi à jour cette base si nécessaire
(nouvelles colonnes, nouvelles données) sans jamais effacer ce qui existe
déjà. Pour repartir d'une base neuve, supprime `easymove.db` et relance
`python app.py`.

## 3. La base de données SQL

10 tables, reliées par des clés étrangères :

| Table                   | Rôle |
|--------------------------|------|
| `lieux`                  | Tous les points sur la carte (quartiers, villes, aéroport, université...) |
| `moyens_transport`       | Taxi, Clando, Dakar Dem Dikk, Car rapide, Minibus Tata, Ndiaga Ndiaye, Jakarta, TER, BRT |
| `lignes_bus`             | Les lignes précises de chaque réseau (ex : Ligne 15 Petersen–Almadies) |
| `arrets`                 | Les arrêts physiques de chaque ligne, avec coordonnées GPS |
| `ligne_arrets`           | Association ligne ↔ arrêts, dans l'ordre de passage |
| `phrases_wolof`          | Lexique wolof utile dans les transports (salutations, paiement, orientation, urgence...) |
| `conseils`                | Conseils pratiques par catégorie |
| `infos_utiles`            | Numéros d'urgence, objets à emporter |
| `historique_recherches`   | Recherches de trajets effectuées, pour la page /historique |
| `favoris`                 | Trajets enregistrés en favori par l'utilisateur |

Tu peux ouvrir `easymove.db` avec [DB Browser for SQLite](https://sqlitebrowser.org/)
pour visualiser les données sans toucher au code.

## 4. Le rôle de Python (Flask)

`app.py` définit une route par page (ex: `/transports`), va chercher les
données correspondantes dans `database.py`, puis les transmet au template
HTML pour affichage.

La partie centrale est `/trajets/resultat` : `itineraire.py` construit un
graphe de transport (arrêts + lignes + correspondances à pied) à partir de
la base, puis calcule le meilleur chemin avec l'algorithme de Dijkstra —
en tenant compte des correspondances entre lignes et entre réseaux (Tata,
Car rapide, Dakar Dem Dikk, BRT, TER). Taxi, Clando, Jakarta et Ndiaga
Ndiaye, qui n'ont pas de ligne fixe, restent toujours proposés en option
à partir d'une estimation de distance. Le résultat est ensuite affiché sur
une vraie carte routière (Leaflet + OSRM), pas une ligne droite entre les
deux points.

Il y a aussi des routes API (`/api/lieux`, `/api/rechercher-trajet`,
`/api/favoris`...) qui renvoient du JSON, utilisées par les scripts du
site (autocomplétion, favoris, arrêt le plus proche).

## 5. La carte interactive

Elle utilise **Leaflet.js** (librairie JS gratuite et open-source, basée sur
les fonds de carte OpenStreetMap/CartoDB), avec un tracé d'itinéraire
routier réel via OSRM (`resultat_trajet.html`, `minibus.html`, l'aperçu de
la page d'accueil).

Ceci nécessite une connexion internet quand le site est ouvert dans un
navigateur (pour charger les tuiles de carte et calculer les itinéraires
routiers).

## 6. Idées pour une future version

- Étendre le moteur d'itinéraire pour tenir compte des horaires réels
  (BRT, TER, DDD ont des horaires publiés) plutôt que d'une vitesse
  moyenne.
- Ajouter des fiches détaillées par ligne et par arrêt (numéro, terminus,
  quartiers traversés, fréquence estimée).
- Préparer une structure multilingue (français / anglais / wolof) pour
  l'interface elle-même, au-delà du lexique.
- Ajouter le partage d'un trajet calculé (lien direct ou QR code).
