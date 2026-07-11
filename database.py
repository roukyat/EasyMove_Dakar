"""
database.py
------------
Module Python chargé de tout ce qui concerne la base de données SQL (SQLite)
du projet EasyMoveDakar : création, connexion, et fonctions de recherche
utilisées par app.py.
"""

import sqlite3
import os

import itineraire

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

    # Certaines bases existantes ont été créées avant l'ajout des tables
    # `conseils` / `infos_utiles` à donnees.sql : comme init_db() ne rejoue
    # les INSERT que sur une base neuve, ces tables restaient vides (page
    # /conseils sans numéros d'urgence). On les réamorce ici si nécessaire.
    _reseeder_donnees_manquantes(cursor)

    # Enrichissement du réseau (quartiers, lignes minibus, lexique wolof) :
    # idempotent, vérifie l'existence par nom avant chaque insertion pour
    # ne jamais dupliquer sur les bases qui ont déjà ces données.
    _enrichir_reseau_et_lexique(cursor)

    # Photos de transport ajoutées après le lancement initial (DDD, TER) :
    # les bases déjà créées ont encore image_url = '' pour ces lignes, donc
    # on complète uniquement si le champ est vide, sans jamais écraser une
    # valeur déjà personnalisée.
    _completer_images_transport_manquantes(cursor)

    conn.commit()
    conn.close()


def _completer_images_transport_manquantes(cursor):
    """Complète l'image de certains moyens de transport ajoutée après le
    lancement initial (photos DDD et TER uploadées dans static/img/).
    Ne touche que les lignes où image_url est encore vide, pour ne jamais
    écraser une valeur déjà personnalisée."""
    images_par_defaut = {
        "Dakar Dem Dikk": "/static/img/DDD.jpg",
        "TER": "/static/img/TER.jpg",
    }
    for nom, chemin_image in images_par_defaut.items():
        cursor.execute(
            "UPDATE moyens_transport SET image_url = ? WHERE nom = ? AND (image_url IS NULL OR image_url = '')",
            (chemin_image, nom)
        )


def _reseeder_donnees_manquantes(cursor):
    """Réinsère les conseils / infos utiles si les tables correspondantes
    sont vides (base créée avant l'ajout de ces données)."""
    if cursor.execute("SELECT COUNT(*) AS n FROM conseils").fetchone()["n"] == 0:
        cursor.executemany(
            "INSERT INTO conseils (categorie, titre, contenu, periode) VALUES (?, ?, ?, ?)",
            [
                ('Avant de partir', 'Prévoir de la monnaie', "Ayez toujours des petites coupures : les chauffeurs n'ont pas toujours la monnaie sur un gros billet.", "Toute l'année"),
                ('Avant de partir', 'Vêtements adaptés', 'Porter des vêtements légers mais couvrants, par respect culturel.', "Toute l'année"),
                ('Dans le transport', 'Négocier avant de monter', 'Pour les taxis clando, toujours fixer le prix avant de monter, jamais après.', "Toute l'année"),
                ('Dans le transport', 'Vérifier la destination', 'Confirmer la destination avec le chauffeur avant de partir pour éviter tout malentendu.', "Toute l'année"),
                ('Confort et bien-être', 'Climatisation non garantie', "La climatisation n'est pas garantie dans tous les taxis ni dans les cars rapides.", "Toute l'année"),
                ('Confort et bien-être', 'Se protéger du soleil', "Utiliser un chapeau ou un parasol en cas de fort ensoleillement.", "Toute l'année"),
                ('Argent et paiement', 'Montant fixe pour le DDD et le BRT', 'Le bus Dakar Dem Dikk et le BRT appliquent un tarif fixe, pas de négociation nécessaire.', "Toute l'année"),
                ('Argent et paiement', "Éviter de montrer trop d'argent", 'Sortez uniquement la somme nécessaire au moment de payer.', "Toute l'année"),
                ('Saisons et météo', 'Prévoir du temps en saison des pluies', 'Les jours de pluie (juillet à octobre), prévoyez le double du temps de trajet habituel.', 'Météo'),
                ('Saisons et météo', 'Circulation dense le vendredi', 'La circulation peut être très dense le vendredi après-midi, lors du retour du travail et de la prière.', 'Heures de pointe'),
                ('Saisons et météo', 'Éviter les heures de pointe', 'Les heures de pointe sont 7h-9h le matin et 17h-20h le soir : prévoir une marge.', 'Heures de pointe'),
                ('Pour les femmes', 'Privilégier les transports connus', 'Privilégier le TER, le BRT ou le DDD en soirée plutôt que un taxi inconnu.', "Toute l'année"),
                ('Périodes', 'Affluence pendant les vacances', 'Pendant les vacances scolaires et les grands événements religieux (Magal, Tabaski), les gares routières sont bondées : réserver ou partir tôt.', 'Vacances'),
            ]
        )

    if cursor.execute("SELECT COUNT(*) AS n FROM infos_utiles").fetchone()["n"] == 0:
        cursor.executemany(
            "INSERT INTO infos_utiles (categorie, libelle, valeur) VALUES (?, ?, ?)",
            [
                ('Urgence', 'Police nationale', '17'),
                ('Urgence', 'SAMU (urgences médicales)', '15'),
                ('Urgence', 'Sapeurs-pompiers', '18'),
                ('Urgence', 'Gendarmerie nationale', '800 00 20 20'),
                ('À emporter', 'Objet recommandé', 'Petite monnaie en FCFA'),
                ('À emporter', 'Objet recommandé', 'Chapeau ou casquette'),
                ('À emporter', 'Objet recommandé', "Bouteille d'eau"),
                ('À emporter', 'Objet recommandé', "Copie de vos papiers d'identité"),
                ('À emporter', 'Objet recommandé', 'Téléphone chargé + batterie externe'),
                ('À emporter', 'Objet recommandé', 'Crème solaire'),
                ('À emporter', 'Objet recommandé', 'Lingettes ou mouchoirs'),
                ('À emporter', 'Objet recommandé', 'Petit sac fermé, porté devant vous'),
                ('À emporter', 'Objet recommandé', 'Plan hors-ligne ou application de cartographie téléchargée'),
            ]
        )


# ---------------------------------------------------------------------
# Enrichissement du réseau : nouveaux quartiers, lignes minibus et
# phrases wolof. Ajoutés de façon idempotente (vérification par nom)
# pour pouvoir être appliqués en toute sécurité sur une base existante.
# ---------------------------------------------------------------------

NOUVEAUX_LIEUX = [
    ('Yoff Layène', 'quartier', 14.7550, -17.4830, "Quartier historique de la confrérie layène, en bord de mer à Yoff"),
    ('Cité Djily Mbaye', 'quartier', 14.7130, -17.4550, "Cité résidentielle proche de Liberté 6 et Grand Yoff"),
    ('Liberté 6 Extension', 'quartier', 14.7225, -17.4680, "Extension résidentielle de Liberté 6, vers la VDN"),
    ('Sacré-Cœur 3', 'quartier', 14.7145, -17.4700, "Extension du quartier Sacré-Cœur"),
    ('Zac Mbao', 'quartier', 14.7430, -17.3510, "Zone d'aménagement concerté proche de Mbao"),
    ('Cité Fadia', 'quartier', 14.7295, -17.4880, "Quartier résidentiel proche d'Ouakam et Mermoz"),
    ('Yeumbeul Sud', 'quartier', 14.7620, -17.3800, "Secteur sud de Yeumbeul"),
    ('Île de Ngor', 'site_touristique', 14.7508, -17.5177, "Petite île accessible en pirogue depuis le village de Ngor, plages préservées"),
    ('Monument de la Renaissance Africaine', 'site_touristique', 14.7203, -17.4890, "Statue monumentale surplombant Ouakam, l'une des plus hautes d'Afrique"),
    ('Village des Arts', 'site_touristique', 14.7245, -17.4820, "Centre d'art contemporain et ateliers d'artistes à Ouakam"),
    ('Île de la Madeleine', 'site_touristique', 14.6656, -17.4791, "Îlot classé parc national, réserve d'oiseaux marins"),
    ('Gare de Dakar', 'gare', 14.6743, -17.4372, "Ancienne gare ferroviaire de Dakar, à proximité du Plateau"),
]

NOUVELLES_PHRASES_WOLOF = [
    ('Jamm ak jamm', 'Tout va bien (réponse classique à « Nanga def ? »)', 'diam ak diam', 'Salutations'),
    ('Naka nga tudd ?', "Comment tu t'appelles ?", 'na-ka nga toud', 'Salutations'),
    ('Su la neexee', "S'il te plaît", 'sou la né-é', 'Politesse'),
    ('Baal ma, dama bëgg laa laaj', 'Excusez-moi, je voudrais vous demander', 'baal ma dama beug la ladj', 'Politesse'),
    ('Wesaare', 'Faire la monnaie / rendre la monnaie', 'wé-sa-ré', 'Négociation'),
    ('Dafa yomb', "C'est raisonnable, pas cher", 'da-fa yomb', 'Négociation'),
    ('Dama bëgg dem [lieu]', 'Je voudrais aller à [lieu]', 'da-ma beug dem', 'Transport'),
    ('Ban gaal moo dem [lieu] ?', 'Quel véhicule va à [lieu] ?', 'ban gaal mo dem', 'Transport'),
    ('Fan la gare bi nekk ?', 'Où se trouve la gare routière ?', 'fan la gar bi nèk', 'Transport'),
    ('Wàcc fi !', 'Descendez ici !', 'watch fi', 'Direction'),
    ('Ci kanam rekk', 'Continuez tout droit', 'ci ka-nam rèk', 'Direction'),
    ('Fukk ak juróom', 'Quinze', 'fouk ak dioróm', 'Nombres'),
    ('Téeméer', 'Cent', 'té-mér', 'Nombres'),
    ('Wallal ma !', 'Aidez-moi !', 'wa-lal ma', 'Urgence'),
    ('Fabu police bi', 'Appelez la police', 'fabou po-lis bi', 'Urgence'),
]

NOUVELLES_LIGNES_MINIBUS = [
    {
        "numero_ligne": "Ligne 23", "nom_ligne": "Petersen - Yoff Layène",
        "description": "Minibus Tata (AFTU) reliant Petersen à Yoff Layène via Sacré-Cœur, Ouest Foire, Yoff",
        "arrets": ["Petersen", "Sacré-Cœur", "Ouest Foire", "Yoff", "Yoff Layène"],
    },
    {
        "numero_ligne": "Ligne 31", "nom_ligne": "Grand Yoff - Cité Djily Mbaye",
        "description": "Minibus Tata (AFTU) reliant Grand Yoff à Cité Djily Mbaye via Liberté 6, Liberté 6 Extension",
        "arrets": ["Grand Yoff", "Liberté 6", "Liberté 6 Extension", "Cité Djily Mbaye"],
    },
    {
        "numero_ligne": "Ligne 33", "nom_ligne": "Ouakam - Village des Arts",
        "description": "Minibus Tata (AFTU) reliant Ouakam au Village des Arts via Virage Ouakam et le Monument de la Renaissance Africaine",
        "arrets": ["Ouakam", "Virage Ouakam", "Monument de la Renaissance Africaine", "Village des Arts", "Cité Fadia"],
    },
    {
        "numero_ligne": "Ligne 51", "nom_ligne": "Colobane - Zac Mbao",
        "description": "Minibus Tata (AFTU) reliant Colobane à Zac Mbao via Hann, Mbao, Petit Mbao",
        "arrets": ["Colobane", "Hann", "Mbao", "Petit Mbao", "Zac Mbao"],
    },
    {
        "numero_ligne": "Ligne 61", "nom_ligne": "Pikine - Yeumbeul Sud",
        "description": "Minibus Tata (AFTU) reliant Pikine à Yeumbeul Sud via Thiaroye, Yeumbeul",
        "arrets": ["Pikine", "Thiaroye", "Yeumbeul", "Yeumbeul Sud"],
    },
    {
        "numero_ligne": "Ligne 68", "nom_ligne": "Médina - Gare de Dakar",
        "description": "Minibus Tata (AFTU) reliant Médina à la Gare de Dakar via Tilène, Plateau",
        "arrets": ["Médina", "Tilène", "Plateau", "Gare de Dakar"],
    },
]


def _enrichir_reseau_et_lexique(cursor):
    """Ajoute de nouveaux quartiers/sites, phrases wolof et lignes minibus
    s'ils n'existent pas déjà (vérification par nom / numéro de ligne),
    afin d'enrichir la couverture du réseau sans jamais dupliquer les
    données sur une base qui les aurait déjà."""

    for nom, type_lieu, lat, lng, desc in NOUVEAUX_LIEUX:
        existe = cursor.execute("SELECT 1 FROM lieux WHERE nom = ?", (nom,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES (?, ?, ?, ?, ?)",
                (nom, type_lieu, lat, lng, desc)
            )

    for wolof, francais, phonetique, situation in NOUVELLES_PHRASES_WOLOF:
        existe = cursor.execute("SELECT 1 FROM phrases_wolof WHERE wolof = ?", (wolof,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO phrases_wolof (wolof, francais, phonetique, situation) VALUES (?, ?, ?, ?)",
                (wolof, francais, phonetique, situation)
            )

    ligne_transport = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom LIKE 'Minibus Tata%'"
    ).fetchone()
    if not ligne_transport:
        return
    id_transport_tata = ligne_transport[0]

    for ligne in NOUVELLES_LIGNES_MINIBUS:
        existe = cursor.execute(
            "SELECT 1 FROM lignes_bus WHERE numero_ligne = ?", (ligne["numero_ligne"],)
        ).fetchone()
        if existe:
            continue

        cursor.execute(
            "INSERT INTO lignes_bus (numero_ligne, nom_ligne, id_transport, est_minibus, description) "
            "VALUES (?, ?, ?, 1, ?)",
            (ligne["numero_ligne"], ligne["nom_ligne"], id_transport_tata, ligne["description"])
        )
        id_ligne = cursor.lastrowid

        for ordre, nom_lieu in enumerate(ligne["arrets"], start=1):
            lieu_row = cursor.execute(
                "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom_lieu,)
            ).fetchone()
            if not lieu_row:
                continue
            id_lieu, lat, lng = lieu_row
            cursor.execute(
                "INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES (?, ?, ?, ?)",
                (f"Arrêt {nom_lieu}", id_lieu, lat, lng)
            )
            id_arret = cursor.lastrowid
            cursor.execute(
                "INSERT INTO ligne_arrets (id_ligne, id_arret, ordre) VALUES (?, ?, ?)",
                (id_ligne, id_arret, ordre)
            )


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


def get_nombre_arrets():
    """Nombre total d'arrets cartographies, toutes lignes confondues."""
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS n FROM arrets").fetchone()["n"]
    conn.close()
    return n


def get_nombre_lieux():
    """Nombre total de lieux references (quartiers, villes, gares...)."""
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS n FROM lieux").fetchone()["n"]
    conn.close()
    return n


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


def favori_existe(id_depart, id_arrivee):
    """Vérifie si ce couple départ/arrivée est déjà enregistré en favori."""
    conn = get_connection()
    ligne = conn.execute("""
        SELECT id_favori FROM favoris
        WHERE id_lieu_depart = ? AND id_lieu_arrivee = ?
    """, (id_depart, id_arrivee)).fetchone()
    conn.close()
    return ligne is not None


def ajouter_favori(nom_trajet, id_depart, id_arrivee):
    conn = get_connection()
    conn.execute("""
        INSERT INTO favoris (nom_trajet, id_lieu_depart, id_lieu_arrivee)
        VALUES (?, ?, ?)
    """, (nom_trajet, id_depart, id_arrivee))
    conn.commit()
    conn.close()


def supprimer_favori(id_favori):
    conn = get_connection()
    conn.execute("DELETE FROM favoris WHERE id_favori = ?", (id_favori,))
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
#
# Depuis cette version, les itinéraires ne sont plus stockés un par un en
# base : ils sont calculés à la volée par le module itineraire.py à partir
# du graphe lieux / arrêts / lignes / correspondances. La table `trajets`
# n'est donc plus utilisée pour la recherche (elle reste dans le schéma
# pour compatibilité mais n'est plus alimentée).
# ---------------------------------------------------------------------

# Paires "populaires" affichées sur la page /trajets et /prix à titre
# d'exemples/raccourcis. La recherche elle-même fonctionne pour n'importe
# quelle paire de lieux de la table `lieux` (voir rechercher_trajet).
TRAJETS_POPULAIRES = [
    ("Yoff", "Plateau"), ("Ouakam", "UCAD"), ("Ngor", "Sandaga"),
    ("Parcelles Assainies", "Liberté 6"), ("Petersen", "Almadies"),
    ("Guédiawaye", "Plateau"), ("Rufisque", "Plateau"), ("Keur Massar", "Plateau"),
    ("Pikine", "UCAD"), ("Grand Yoff", "Sandaga"), ("Médina", "Ouakam"),
    ("Almadies", "Aéroport AIBD"), ("Plateau", "Aéroport AIBD"),
    ("Plateau", "Diamniadio"), ("Plateau", "Lac Rose (Retba)"),
    ("Ouakam", "Yoff"), ("Sacré-Cœur", "Guédiawaye"), ("Thiaroye", "Keur Massar"),
    ("Rufisque", "Bargny"), ("Ngor", "Almadies"), ("Colobane", "Grand Yoff"),
    ("Médina", "Gorée"), ("Petersen", "Rufisque"), ("Yoff", "Guédiawaye"),
    ("Parcelles Assainies", "Cambérène"), ("Grand Mbao", "Plateau"),
    ("Sandaga", "Fann"), ("Liberté 6", "Almadies"), ("Pikine", "Rufisque"),
    ("Keur Massar", "Malika"), ("Diamniadio", "Sébikotane"), ("Ouakam", "Rufisque"),
    ("Plateau", "Sicap Baobab"), ("Grand Yoff", "Cambérène"), ("HLM", "Point E"),
    ("Petersen", "Yoff Layène"), ("Grand Yoff", "Cité Djily Mbaye"), ("Ouakam", "Village des Arts"),
    ("Colobane", "Zac Mbao"), ("Pikine", "Yeumbeul Sud"), ("Médina", "Gare de Dakar"),
    ("Almadies", "Île de Ngor"), ("Ouakam", "Monument de la Renaissance Africaine"),
]


def _niveau_difficulte(options):
    """Estime un niveau de difficulté à partir du meilleur itinéraire en
    transport en commun trouvé (indépendamment de l'option recommandée,
    qui peut être un taxi/Jakarta simplement plus rapide)."""
    meilleur_transit = None
    for o in options:
        if o["nom_transport"] not in ("Taxi clando", "Jakarta (moto-taxi)", "À pied"):
            meilleur_transit = o
            break
    if meilleur_transit is None:
        return "Complexe"
    if meilleur_transit["correspondances"] == "Aucune":
        return "Facile"
    if meilleur_transit["correspondances"].startswith(("1 ", "2 ")):
        return "Moyen"
    return "Complexe"


def _construire_reponse(conn, lieu_depart, lieu_arrivee, graphe=None):
    if lieu_depart["id_lieu"] == lieu_arrivee["id_lieu"]:
        trajet_info = {
            "id_trajet": None,
            "id_lieu_depart": lieu_depart["id_lieu"], "id_lieu_arrivee": lieu_arrivee["id_lieu"],
            "nom_depart": lieu_depart["nom"], "lat_depart": lieu_depart["latitude"], "lng_depart": lieu_depart["longitude"],
            "nom_arrivee": lieu_arrivee["nom"], "lat_arrivee": lieu_arrivee["latitude"], "lng_arrivee": lieu_arrivee["longitude"],
            "distance_km": 0, "niveau_difficulte": "Facile",
            "description": "Le départ et l'arrivée correspondent au même lieu.",
        }
        return {"trajet": trajet_info, "options": []}

    options, distance_km = itineraire.calculer_itineraire(conn, lieu_depart, lieu_arrivee, graphe=graphe)
    trajet_info = {
        "id_trajet": None,
        "id_lieu_depart": lieu_depart["id_lieu"], "id_lieu_arrivee": lieu_arrivee["id_lieu"],
        "nom_depart": lieu_depart["nom"], "lat_depart": lieu_depart["latitude"], "lng_depart": lieu_depart["longitude"],
        "nom_arrivee": lieu_arrivee["nom"], "lat_arrivee": lieu_arrivee["latitude"], "lng_arrivee": lieu_arrivee["longitude"],
        "distance_km": round(distance_km, 1),
        "niveau_difficulte": _niveau_difficulte(options),
        "description": f"Itinéraire calculé automatiquement entre {lieu_depart['nom']} et {lieu_arrivee['nom']}.",
    }
    return {"trajet": trajet_info, "options": options}


def get_tous_les_trajets():
    """Retourne une sélection de trajets populaires, calculés dynamiquement
    par le moteur d'itinéraire (utilisé pour les pages /trajets et /prix)."""
    conn = get_connection()
    lieux_par_nom = {l["nom"]: l for l in conn.execute("SELECT * FROM lieux").fetchall()}
    graphe = itineraire.Graphe(conn)

    resultat = []
    for nom_depart, nom_arrivee in TRAJETS_POPULAIRES:
        ld, la = lieux_par_nom.get(nom_depart), lieux_par_nom.get(nom_arrivee)
        if not ld or not la:
            continue
        resultat.append(_construire_reponse(conn, ld, la, graphe=graphe))

    conn.close()
    return resultat


def rechercher_trajet(id_depart, id_arrivee):
    """
    Calcule dynamiquement le meilleur itinéraire entre deux lieux (bus/Tata/
    BRT/TER avec correspondances, + options Taxi/Jakarta toujours
    disponibles). Enregistre également la recherche dans l'historique.
    """
    conn = get_connection()

    lieu_depart = conn.execute("SELECT * FROM lieux WHERE id_lieu = ?", (id_depart,)).fetchone()
    lieu_arrivee = conn.execute("SELECT * FROM lieux WHERE id_lieu = ?", (id_arrivee,)).fetchone()

    if not lieu_depart or not lieu_arrivee:
        conn.close()
        return None

    ajouter_recherche_historique(
        lieu_depart["nom"], lieu_arrivee["nom"],
        lieu_depart["latitude"], lieu_depart["longitude"],
        lieu_arrivee["latitude"], lieu_arrivee["longitude"]
    )

    reponse = _construire_reponse(conn, lieu_depart, lieu_arrivee)
    conn.close()

    return {"trouve": True, "trajet": reponse["trajet"], "options": reponse["options"]}