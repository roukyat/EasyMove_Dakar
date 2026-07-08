"""
database.py
------------
Module Python chargé de tout ce qui concerne la base de données SQL (SQLite)
du projet EasyMoveDakar : création, connexion, et fonctions de recherche
utilisées par app.py.
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "easymove.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "sql", "schema.sql")
DONNEES_PATH = os.path.join(BASE_DIR, "sql", "donnees.sql")


def get_connection():
    """Ouvre une connexion SQLite et retourne les lignes sous forme de dict."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def verifier_et_mettre_a_jour_schema():
    """
    Vérifie à la volée si les colonnes nécessaires (image_url, avantages, inconvenients, est_minibus)
    et la table historique existent pour éviter les plantages 'OperationalError'.
    """
    if not os.path.exists(DB_PATH):
        return

    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Vérification/Ajout des colonnes sur moyens_transport
    cursor.execute("PRAGMA table_info(moyens_transport)")
    colonnes_transport = [row["name"] for row in cursor.fetchall()]
    
    if "image_url" not in colonnes_transport:
        cursor.execute("ALTER TABLE moyens_transport ADD COLUMN image_url TEXT DEFAULT ''")
    if "avantages" not in colonnes_transport:
        cursor.execute("ALTER TABLE moyens_transport ADD COLUMN avantages TEXT DEFAULT ''")
    if "inconvenients" not in colonnes_transport:
        cursor.execute("ALTER TABLE moyens_transport ADD COLUMN inconvenients TEXT DEFAULT ''")
        
    
    cursor.execute("PRAGMA table_info(lignes_bus)")
    colonnes_lignes = [row["name"] for row in cursor.fetchall()]
    
    if "est_minibus" not in colonnes_lignes:
        cursor.execute("ALTER TABLE lignes_bus ADD COLUMN est_minibus INTEGER DEFAULT 0")
        # On met à 1 par défaut les lignes existantes si ce sont des Tata pour éviter qu'elles disparaissent
        cursor.execute("UPDATE lignes_bus SET est_minibus = 1 WHERE numero_ligne LIKE '%Tata%' OR nom_ligne LIKE '%Tata%'")
        
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historique_recherches'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE historique_recherches (
                id_historique INTEGER PRIMARY KEY AUTOINCREMENT,
                adresse_depart TEXT,
                adresse_arrivee TEXT,
                lat_depart REAL,
                lng_depart REAL,
                lat_arrivee REAL,
                lng_arrivee REAL,
                date_recherche TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
    conn.commit()
    conn.close()


def init_db(force=False):
    """
    Crée le fichier de base de données à partir de schema.sql et le remplit
    avec donnees.sql. Si force=True, la base existante est supprimée et
    recréée depuis zéro .
    """
    if force and os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except PermissionError:
            pass

    nouvelle_base = not os.path.exists(DB_PATH)

    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    if nouvelle_base:
        with open(DONNEES_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()

    conn.close()
    
    # Lancement de la mise à jour de sécurité des colonnes
    verifier_et_mettre_a_jour_schema()


# Appliquer les corrections directement dès l'importation de ce module
if os.path.exists(DB_PATH):
    verifier_et_mettre_a_jour_schema()


# ---------------------------------------------------------------------
# Fonctions de lecture utilisées par les pages du site
# ---------------------------------------------------------------------

def get_tous_les_lieux():
    conn = get_connection()
    lieux = conn.execute(
        "SELECT * FROM lieux ORDER BY type_lieu, nom"
    ).fetchall()
    conn.close()
    return lieux


def get_tous_les_transports():
    conn = get_connection()
    transports = conn.execute(
        "SELECT * FROM moyens_transport ORDER BY cout_min"
    ).fetchall()
    conn.close()
    return transports


def get_toutes_les_phrases():
    conn = get_connection()
    phrases = conn.execute(
        "SELECT * FROM phrases_wolof ORDER BY situation, id_phrase"
    ).fetchall()
    conn.close()
    return phrases


def get_tous_les_conseils():
    conn = get_connection()
    conseils = conn.execute(
        "SELECT * FROM conseils ORDER BY categorie, id_conseil"
    ).fetchall()
    conn.close()
    return conseils


def get_infos_utiles():
    conn = get_connection()
    infos = conn.execute(
        "SELECT * FROM infos_utiles ORDER BY categorie, id_info"
    ).fetchall()
    conn.close()
    return infos


# ---------------------------------------------------------------------
# Gestion Spécifique des Lignes et Arrêts (Minibus )
# ---------------------------------------------------------------------

def get_toutes_les_lignes_bus(seulement_minibus=False):
    """Retourne les lignes de bus avec un filtre optionnel pour le réseau Minibus."""
    conn = get_connection()
    query = "SELECT * FROM lignes_bus"
    if seulement_minibus:
        query += " WHERE est_minibus = 1"
    query += " ORDER BY numero_ligne"
    
    lignes = conn.execute(query).fetchall()
    conn.close()
    return lignes


def get_arrets_par_ligne(id_ligne):
    """Retourne les arrêts ordonnés d'une ligne spécifique avec coordonnées GPS."""
    conn = get_connection()
    arrets = conn.execute("""
        SELECT a.* FROM arrets a
        JOIN ligne_arrets la ON a.id_arret = la.id_arret
        WHERE la.id_ligne = ?
        ORDER BY la.ordre
    """, (id_ligne,)).fetchall()
    conn.close()
    return arrets


# ---------------------------------------------------------------------
# Gestion de l'Historique des Recherches et Favoris
# ---------------------------------------------------------------------

def ajouter_recherche_historique(dep_nom, arr_nom, dep_lat=None, dep_lng=None, arr_lat=None, arr_lng=None):
    """Enregistre une recherche effectuée par l'utilisateur."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO historique_recherches (adresse_depart, adresse_arrivee, lat_depart, lng_depart, lat_arrivee, lng_arrivee)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (dep_nom, arr_nom, dep_lat, dep_lng, arr_lat, arr_lng))
    conn.commit()
    conn.close()


def get_historique_recent(limite=10):
    """Récupère les dernières recherches de l'utilisateur."""
    conn = get_connection()
    try:
        historique = conn.execute("""
            SELECT * FROM historique_recherches 
            ORDER BY date_recherche DESC 
            LIMIT ?
        """, (limite,)).fetchall()
    except sqlite3.OperationalError:
        historique = []
    conn.close()
    return historique


def ajouter_favori(nom_trajet, id_depart, id_arrivee):
    conn = get_connection()
    conn.execute("""
        INSERT INTO favoris (nom_trajet, id_lieu_depart, id_lieu_arrivee)
        VALUES (?, ?, ?)
    """, (nom_trajet, id_depart, id_arrivee))
    conn.commit()
    conn.close()


def get_tous_les_favoris():
    conn = get_connection()
    favoris = conn.execute("""
        SELECT f.*, ld.nom AS nom_depart, la.nom AS nom_arrivee
        FROM favoris f
        JOIN lieux ld ON f.id_lieu_depart = ld.id_lieu
        JOIN lieux la ON f.id_lieu_arrivee = la.id_lieu
        ORDER BY f.id_favori DESC
    """).fetchall()
    conn.close()
    return favoris


# ---------------------------------------------------------------------
# Trajets et Moteur de Recherche d'itinéraires
# ---------------------------------------------------------------------

def get_tous_les_trajets():
    """Retourne tous les trajets prédéfinis, avec le nom des lieux."""
    conn = get_connection()
    trajets = conn.execute("""
        SELECT t.*, ld.nom AS nom_depart, ld.latitude AS lat_depart, ld.longitude AS lng_depart,
               la.nom AS nom_arrivee, la.latitude AS lat_arrivee, la.longitude AS lng_arrivee
        FROM trajets t
        JOIN lieux ld ON t.id_lieu_depart = ld.id_lieu
        JOIN lieux la ON t.id_lieu_arrivee = la.id_lieu
        ORDER BY t.id_trajet
    """).fetchall()

    resultat = []
    for t in trajets:
        options = conn.execute("""
            SELECT o.*, m.nom AS nom_transport, m.image_url,
                   l.numero_ligne, l.nom_ligne
            FROM trajet_options o
            JOIN moyens_transport m ON o.id_transport = m.id_transport
            LEFT JOIN lignes_bus l ON o.id_ligne = l.id_ligne
            WHERE o.id_trajet = ?
            ORDER BY o.recommande DESC, o.prix_min
        """, (t["id_trajet"],)).fetchall()
        resultat.append({"trajet": t, "options": options})

    conn.close()
    return resultat


def rechercher_trajet(id_depart, id_arrivee):
    """
    Cherche un trajet prédéfini entre deux lieux. Enregistre également la recherche 
    automatiquement dans la table d'historique.
    """
    conn = get_connection()

    # Récupération des infos textuelles et GPS de base pour l'historique
    lieu_depart = conn.execute("SELECT * FROM lieux WHERE id_lieu = ?", (id_depart,)).fetchone()
    lieu_arrivee = conn.execute("SELECT * FROM lieux WHERE id_lieu = ?", (id_arrivee,)).fetchone()

    if lieu_depart and lieu_arrivee:
        ajouter_recherche_historique(
            lieu_depart["nom"], lieu_arrivee["nom"],
            lieu_depart["latitude"], lieu_depart["longitude"],
            lieu_arrivee["latitude"], lieu_arrivee["longitude"]
        )

    trajet = conn.execute("""
        SELECT t.*, ld.nom AS nom_depart, ld.latitude AS lat_depart, ld.longitude AS lng_depart,
               la.nom AS nom_arrivee, la.latitude AS lat_arrivee, la.longitude AS lng_arrivee
        FROM trajets t
        JOIN lieux ld ON t.id_lieu_depart = ld.id_lieu
        JOIN lieux la ON t.id_lieu_arrivee = la.id_lieu
        WHERE (t.id_lieu_depart = ? AND t.id_lieu_arrivee = ?)
           OR (t.id_lieu_depart = ? AND t.id_lieu_arrivee = ?)
        LIMIT 1
    """, (id_depart, id_arrivee, id_arrivee, id_depart)).fetchone()

    if trajet is None:
        conn.close()
        if not lieu_depart or not lieu_arrivee:
            return None
        return {
            "trouve": False,
            "depart": dict(lieu_depart),
            "arrivee": dict(lieu_arrivee),
            "options": []
        }

    options = conn.execute("""
        SELECT o.*, m.nom AS nom_transport, m.image_url, m.avantages, m.inconvenients,
               l.numero_ligne, l.nom_ligne
        FROM trajet_options o
        JOIN moyens_transport m ON o.id_transport = m.id_transport
        LEFT JOIN lignes_bus l ON o.id_ligne = l.id_ligne
        WHERE o.id_trajet = ?
        ORDER BY o.recommande DESC, o.prix_min
    """, (trajet["id_trajet"],)).fetchall()

    conn.close()

    return {
        "trouve": True,
        "trajet": dict(trajet),
        "options": [dict(o) for o in options]
    }