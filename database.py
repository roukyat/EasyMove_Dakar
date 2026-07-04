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


def init_db(force=False):
    """
    Crée le fichier de base de données à partir de schema.sql et le remplit
    avec donnees.sql. Si force=True, la base existante est supprimée et
    recréée depuis zéro (pratique pendant le développement).
    """
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    nouvelle_base = not os.path.exists(DB_PATH)

    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    if nouvelle_base:
        with open(DONNEES_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()

    conn.close()


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
            SELECT o.*, m.nom AS nom_transport, m.icone,
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
    Cherche un trajet prédéfini entre deux lieux (dans les deux sens).
    Retourne un dict avec les infos du trajet + ses options + coordonnées
    GPS (utilisées ensuite pour dessiner la carte).
    """
    conn = get_connection()

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
        # Aucun trajet prédéfini : on renvoie quand même les coordonnées
        # des deux lieux pour pouvoir afficher la carte, sans les options.
        lieu_depart = conn.execute("SELECT * FROM lieux WHERE id_lieu = ?", (id_depart,)).fetchone()
        lieu_arrivee = conn.execute("SELECT * FROM lieux WHERE id_lieu = ?", (id_arrivee,)).fetchone()
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
        SELECT o.*, m.nom AS nom_transport, m.icone, m.avantages, m.inconvenients,
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
