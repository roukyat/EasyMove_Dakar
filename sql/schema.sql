-- =====================================================================
-- EasyMoveDakar - Schéma de la base de données
-- =====================================================================
-- Ce fichier contient uniquement la structure (DDL).
-- Les données sont insérées séparément dans donnees.sql
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Table LIEUX
-- Tous les endroits que l'on peut choisir comme départ ou arrivée :
-- quartiers, villes, aéroport, gares, sites touristiques, universités...
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lieux (
    id_lieu       INTEGER PRIMARY KEY AUTOINCREMENT,
    nom           TEXT NOT NULL,
    type_lieu     TEXT NOT NULL,      -- ex: 'quartier', 'ville', 'aeroport', 'universite', 'site_touristique'
    latitude      REAL NOT NULL,
    longitude     REAL NOT NULL,
    description   TEXT
);

-- ---------------------------------------------------------------------
-- Table MOYENS_TRANSPORT
-- Les différents moyens de transport disponibles à Dakar / au Sénégal
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS moyens_transport (
    id_transport    INTEGER PRIMARY KEY AUTOINCREMENT,
    nom             TEXT NOT NULL,
    icone           TEXT,             -- emoji utilisé pour l'affichage
    description     TEXT,
    cout_min        INTEGER,          -- en FCFA
    cout_max        INTEGER,          -- en FCFA
    niveau_confort  TEXT,             -- 'Faible', 'Moyen', 'Élevé'
    disponibilite   TEXT,             -- ex: '24h/24', 'Heures de bureau', 'Selon affluence'
    avantages       TEXT,
    inconvenients   TEXT
);

-- ---------------------------------------------------------------------
-- Table LIGNES_BUS
-- Les lignes de bus (Dakar Dem Dikk, BRT, etc.) rattachées à un moyen
-- de transport
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lignes_bus (
    id_ligne            INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_ligne        TEXT NOT NULL,
    nom_ligne           TEXT,
    id_transport        INTEGER NOT NULL,
    description         TEXT,
    FOREIGN KEY (id_transport) REFERENCES moyens_transport(id_transport)
);

-- ---------------------------------------------------------------------
-- Table ARRETS
-- Les arrêts de bus / points d'embarquement, reliés à un lieu
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS arrets (
    id_arret        INTEGER PRIMARY KEY AUTOINCREMENT,
    nom             TEXT NOT NULL,
    id_lieu         INTEGER,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    FOREIGN KEY (id_lieu) REFERENCES lieux(id_lieu)
);

-- ---------------------------------------------------------------------
-- Table LIGNE_ARRETS (table d'association N-N)
-- Ordonne les arrêts desservis par chaque ligne de bus
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ligne_arrets (
    id_ligne    INTEGER NOT NULL,
    id_arret    INTEGER NOT NULL,
    ordre       INTEGER NOT NULL,
    PRIMARY KEY (id_ligne, id_arret),
    FOREIGN KEY (id_ligne) REFERENCES lignes_bus(id_ligne),
    FOREIGN KEY (id_arret) REFERENCES arrets(id_arret)
);

-- ---------------------------------------------------------------------
-- Table TRAJETS
-- Un trajet relie un lieu de départ à un lieu d'arrivée
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trajets (
    id_trajet           INTEGER PRIMARY KEY AUTOINCREMENT,
    id_lieu_depart      INTEGER NOT NULL,
    id_lieu_arrivee     INTEGER NOT NULL,
    distance_km         REAL,
    niveau_difficulte   TEXT,          -- 'Facile', 'Moyen', 'Complexe'
    description         TEXT,
    FOREIGN KEY (id_lieu_depart)  REFERENCES lieux(id_lieu),
    FOREIGN KEY (id_lieu_arrivee) REFERENCES lieux(id_lieu)
);

-- ---------------------------------------------------------------------
-- Table TRAJET_OPTIONS
-- Pour un trajet donné, les différentes options de transport possibles
-- (prix, durée, correspondances, étapes...)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trajet_options (
    id_option         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_trajet         INTEGER NOT NULL,
    id_transport      INTEGER NOT NULL,
    id_ligne          INTEGER,                 -- NULL si pas de ligne de bus précise
    prix_min          INTEGER,
    prix_max          INTEGER,
    duree_min_minutes INTEGER,
    duree_max_minutes INTEGER,
    correspondances   TEXT,
    etapes            TEXT,                    -- étapes séparées par ' | '
    recommande        INTEGER DEFAULT 0,       -- 1 = option recommandée
    FOREIGN KEY (id_trajet)    REFERENCES trajets(id_trajet),
    FOREIGN KEY (id_transport) REFERENCES moyens_transport(id_transport),
    FOREIGN KEY (id_ligne)     REFERENCES lignes_bus(id_ligne)
);

-- ---------------------------------------------------------------------
-- Table PHRASES_WOLOF
-- Guide de phrases utiles en wolof
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS phrases_wolof (
    id_phrase     INTEGER PRIMARY KEY AUTOINCREMENT,
    wolof         TEXT NOT NULL,
    francais      TEXT NOT NULL,
    phonetique    TEXT,
    situation     TEXT           -- ex: 'Salutations', 'Négocier un prix', 'Demander son chemin'
);

-- ---------------------------------------------------------------------
-- Table CONSEILS
-- Conseils pratiques, éventuellement liés à une période de l'année
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conseils (
    id_conseil    INTEGER PRIMARY KEY AUTOINCREMENT,
    categorie     TEXT NOT NULL,     -- 'Sécurité', 'Argent', 'Comportement', 'Périodes'...
    titre         TEXT NOT NULL,
    contenu       TEXT NOT NULL,
    periode       TEXT              -- 'Vacances', 'Heures de pointe', 'Météo', 'Toute l'année'
);

-- ---------------------------------------------------------------------
-- Table INFOS_UTILES
-- Numéros d'urgence, recommandations diverses
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS infos_utiles (
    id_info     INTEGER PRIMARY KEY AUTOINCREMENT,
    categorie   TEXT NOT NULL,      -- 'Urgence', 'Sécurité', 'À emporter'
    libelle     TEXT NOT NULL,
    valeur      TEXT
);
