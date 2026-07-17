-- =====================================================================
-- EasyMoveDakar - Schéma de la base de données 
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Table LIEUX
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
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS moyens_transport (
    id_transport    INTEGER PRIMARY KEY AUTOINCREMENT,
    nom             TEXT NOT NULL,
    image_url       TEXT,             -- URL/Chemin de l'image réelle (ex: /static/img/BRT.jpg)
    description     TEXT,
    cout_min        INTEGER,          -- en FCFA
    cout_max        INTEGER,          -- en FCFA
    niveau_confort  TEXT,             -- 'Faible', 'Moyen', 'Élevé'
    disponibilite   TEXT,             -- ex: '24h/24', 'Heures de bureau'
    avantages       TEXT,
    inconvenients   TEXT
);

-- ---------------------------------------------------------------------
-- Table LIGNES_BUS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lignes_bus (
    id_ligne            INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_ligne        TEXT NOT NULL,
    nom_ligne           TEXT,
    id_transport        INTEGER NOT NULL,
    est_minibus         INTEGER DEFAULT 0, -- 0 = Bus classique (DDD, BRT), 1 = Réseau Minibus (Tata, Car Rapide)
    description         TEXT,
    FOREIGN KEY (id_transport) REFERENCES moyens_transport(id_transport)
);

-- ---------------------------------------------------------------------
-- Table ARRETS
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
-- Table PHRASES_WOLOF
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS phrases_wolof (
    id_phrase     INTEGER PRIMARY KEY AUTOINCREMENT,
    wolof         TEXT NOT NULL,
    francais      TEXT NOT NULL,
    phonetique    TEXT,
    situation     TEXT,          -- ex: 'Saluer', 'Payer et connaître le tarif'
    contexte      TEXT           -- ex: 'À dire au chauffeur' (optionnel)
);

-- ---------------------------------------------------------------------
-- Table CONSEILS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conseils (
    id_conseil    INTEGER PRIMARY KEY AUTOINCREMENT,
    categorie     TEXT NOT NULL,     -- 'Sécurité', 'Argent', 'Comportement'
    titre         TEXT NOT NULL,
    contenu       TEXT NOT NULL,
    periode       TEXT               -- 'Heures de pointe', 'Toute l'année'
);

-- ---------------------------------------------------------------------
-- Table INFOS_UTILES
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS infos_utiles (
    id_info     INTEGER PRIMARY KEY AUTOINCREMENT,
    categorie   TEXT NOT NULL,      -- 'Urgence', 'À emporter'
    libelle     TEXT NOT NULL,
    valeur      TEXT
);

-- ---------------------------------------------------------------------
-- Table HISTORIQUE_RECHERCHES 
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historique_recherches (
    id_historique       INTEGER PRIMARY KEY AUTOINCREMENT,
    adresse_depart      TEXT NOT NULL,
    adresse_arrivee     TEXT NOT NULL,
    lat_depart          REAL,
    lng_depart          REAL,
    lat_arrivee         REAL,
    lng_arrivee         REAL,
    id_lieu_depart      INTEGER,
    id_lieu_arrivee     INTEGER,
    date_recherche      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Table FAVORIS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS favoris (
    id_favori           INTEGER PRIMARY KEY AUTOINCREMENT,
    nom_trajet          TEXT NOT NULL, -- ex: "Maison -> Bureau"
    id_lieu_depart      INTEGER NOT NULL,
    id_lieu_arrivee     INTEGER NOT NULL,
    FOREIGN KEY (id_lieu_depart)  REFERENCES lieux(id_lieu),
    FOREIGN KEY (id_lieu_arrivee) REFERENCES lieux(id_lieu)
);