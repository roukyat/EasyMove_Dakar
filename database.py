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
    if "capacite_max" in colonnes_transport:
        _supprimer_colonne_capacite_max(cursor)


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
                id_lieu_depart INTEGER,
                id_lieu_arrivee INTEGER,
                date_recherche TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # id_lieu_depart/id_lieu_arrivee ajoutés après le lancement initial, pour
    # que "Revoir l'itinéraire" (page /historique) puisse rouvrir directement
    # le bon résultat au lieu de ramener sur une recherche vide : les entrées
    # d'historique plus anciennes gardent ces colonnes à NULL.
    cursor.execute("PRAGMA table_info(historique_recherches)")
    colonnes_historique = [row["name"] for row in cursor.fetchall()]
    if "id_lieu_depart" not in colonnes_historique:
        cursor.execute("ALTER TABLE historique_recherches ADD COLUMN id_lieu_depart INTEGER")
    if "id_lieu_arrivee" not in colonnes_historique:
        cursor.execute("ALTER TABLE historique_recherches ADD COLUMN id_lieu_arrivee INTEGER")

    # `contexte` ajoutée pour la refonte du lexique Wolof (page /wolof) :
    # une courte indication d'usage par phrase ("À dire au chauffeur"...),
    # affichée en petit sous la traduction sans changer la mise en page du
    # tableau. NULL pour les phrases qui n'en ont pas besoin.
    cursor.execute("PRAGMA table_info(phrases_wolof)")
    colonnes_phrases = [row["name"] for row in cursor.fetchall()]
    if "contexte" not in colonnes_phrases:
        cursor.execute("ALTER TABLE phrases_wolof ADD COLUMN contexte TEXT")

    # Le Taxi et le Clando étaient historiquement fusionnés dans une seule
    # ligne 'Taxi clando' : on les sépare ici en deux moyens de transport
    # distincts (taxi officiel réglementé vs taxi clandestin/collectif
    # informel), de façon idempotente pour ne jamais dupliquer sur une base
    # déjà migrée.
    _migrer_taxi_et_clando(cursor)

    # Bug hérité de cette même scission Taxi/Clando : l'insertion de la
    # nouvelle ligne 'Clando' juste après 'Taxi' a décalé d'un cran les
    # id_transport de tous les moyens de transport suivants (Dakar Dem
    # Dikk, Car rapide, Minibus Tata, Jakarta, TER, BRT), mais les lignes
    # de bus de la donnée d'origine (donnees.sql) référençaient encore les
    # anciens id_transport codés en dur — donc mal rattachées (les lignes
    # Tata comptées comme Car rapide, etc.). Corrige les bases déjà créées
    # avant ce correctif ; donnees.sql a aussi été corrigé pour les
    # nouvelles bases. Idempotent (ne touche que ce qui est encore mal
    # rattaché).
    _corriger_id_transport_errones(cursor)

    # Certaines bases existantes ont été créées avant l'ajout des tables
    # `conseils` / `infos_utiles` à donnees.sql : comme init_db() ne rejoue
    # les INSERT que sur une base neuve, ces tables restaient vides (page
    # /conseils sans numéros d'urgence). On les réamorce ici si nécessaire.
    _reseeder_donnees_manquantes(cursor)

    # Conseils "Cars rapides" et "Tata (bus)" ajoutés après le lancement
    # initial : idempotent (vérification par titre), donc sûr à rejouer sur
    # une base qui a déjà ces conseils.
    _ajouter_conseils_cars_rapides_et_tata(cursor)

    # Nouveau moyen de transport "Ndiaga Ndiaye" (page /transports) + ses
    # conseils pratiques dédiés (page /conseils). Idempotent (vérification
    # par nom / par titre).
    _ajouter_transport_ndiaga_ndiaye(cursor)
    _ajouter_conseils_ndiaga_ndiaye(cursor)

    # Relecture éditoriale de quelques conseils trop longs pour une carte
    # compacte : idempotent (UPDATE conditionné au contenu actuel), sûr à
    # rejouer sur une base qui a déjà le texte raccourci.
    _raccourcir_conseils_verbeux(cursor)

    # Enrichissement du réseau (quartiers, lignes minibus, lexique wolof) :
    # idempotent, vérifie l'existence par nom avant chaque insertion pour
    # ne jamais dupliquer sur les bases qui ont déjà ces données.
    _enrichir_reseau_et_lexique(cursor)

    # Réseau minibus curé autour du pôle SONATEL (VDN) : lieu + lignes vers
    # les quartiers où les étudiants sont les plus concentrés (UCAD,
    # Ouakam, Liberté 5/6, Sacré-Cœur, Cité Keur Gorgui) plus deux
    # destinations complémentaires (Ouest Foire, Ngor). Idempotent.
    _ajouter_reseau_sonatel(cursor)

    # Photos de transport ajoutées après le lancement initial (DDD, TER) :
    # les bases déjà créées ont encore image_url = '' pour ces lignes, donc
    # on complète uniquement si le champ est vide, sans jamais écraser une
    # valeur déjà personnalisée.
    _completer_images_transport_manquantes(cursor)

    # Nettoyage éditorial de la page /conseils (retrait de conseils jugés
    # redondants/anecdotiques) + correction du numéro national du SAMU
    # (1515, et non 15 qui est le numéro français) : idempotent, sûr à
    # rejouer sur une base déjà à jour.
    _purger_conseils_obsoletes(cursor)

    # Réactualisation des tarifs (2026) vers des fourchettes plus réalistes :
    # idempotent (UPDATE conditionné au contenu actuel), sûr à rejouer sur
    # une base déjà à jour.
    _mettre_a_jour_tarifs_2026(cursor)

    # Descriptions plus naturelles pour Taxi/Clando/Tata (accueil + page
    # /transports) : idempotent, même logique que les tarifs ci-dessus.
    _naturaliser_descriptions_transport(cursor)

    # Retrait des lignes fictives 'DIT-1..5' créées lors d'une itération
    # précédente (voir _retirer_lignes_dit_fictives). Idempotent.
    _retirer_lignes_dit_fictives(cursor)

    # Troisième vague d'enrichissement du réseau : nouveaux lieux et
    # nouvelles lignes Tata/Car rapide couvrant l'ensemble de Dakar (voir
    # _enrichir_reseau_vague_3). Idempotent.
    _enrichir_reseau_vague_3(cursor)

    # Quatrième vague d'enrichissement, centrée spécifiquement sur le
    # réseau Tata (28 lignes supplémentaires + nouveaux lieux). Idempotent.
    _enrichir_reseau_vague_4(cursor)

    # Refonte du lexique Wolof (page /wolof) : les phrases existantes sont
    # reclassées dans des catégories pensées pour un déplacement réel
    # (saluer, monter dans un Tata, demander un arrêt...) plutôt que des
    # intitulés grammaticaux, et le lexique est enrichi de nouvelles
    # expressions utiles + d'un contexte d'usage. Idempotent (UPDATE par
    # texte wolof exact + INSERT conditionné à l'absence de la phrase).
    _reorganiser_lexique_wolof_transport(cursor)

    conn.commit()
    conn.close()


def _supprimer_colonne_capacite_max(cursor):
    """Retire la colonne `capacite_max` de `moyens_transport` (le nombre
    max de passagers n'est plus affiché ni utilisé nulle part dans le
    site). Utilise DROP COLUMN (SQLite >= 3.35) ; si la version de SQLite
    est trop ancienne pour le supporter, on reconstruit la table sans la
    colonne plutôt que de planter. Idempotent : n'est appelée que si la
    colonne existe encore (voir verifier_et_mettre_a_jour_schema)."""
    try:
        cursor.execute("ALTER TABLE moyens_transport DROP COLUMN capacite_max")
        return
    except sqlite3.OperationalError:
        pass

    # Repli pour SQLite < 3.35 : reconstruction manuelle de la table.
    cursor.execute("PRAGMA table_info(moyens_transport)")
    colonnes = [row["name"] for row in cursor.fetchall() if row["name"] != "capacite_max"]
    colonnes_sql = ", ".join(colonnes)
    cursor.execute(f"""
        CREATE TABLE moyens_transport_tmp (
            id_transport    INTEGER PRIMARY KEY AUTOINCREMENT,
            nom             TEXT NOT NULL,
            image_url       TEXT,
            description     TEXT,
            cout_min        INTEGER,
            cout_max        INTEGER,
            niveau_confort  TEXT,
            disponibilite   TEXT,
            avantages       TEXT,
            inconvenients   TEXT
        )
    """)
    cursor.execute(f"INSERT INTO moyens_transport_tmp ({colonnes_sql}) SELECT {colonnes_sql} FROM moyens_transport")
    cursor.execute("DROP TABLE moyens_transport")
    cursor.execute("ALTER TABLE moyens_transport_tmp RENAME TO moyens_transport")


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


# ---------------------------------------------------------------------
# Tarifs 2026 : fourchettes réajustées vers des valeurs plus réalistes
# (recherche de tarifs actuels pour Dakar — taxi en ville, hausse des
# tickets Tata/AFTU, tarif TER Dakar-Diamniadio, BRT à tarif fixe...).
# Appliqué par UPDATE conditionné au contenu actuel (voir
# _mettre_a_jour_tarifs_2026), donc sûr à rejouer sur une base qui a déjà
# ces tarifs.
# ---------------------------------------------------------------------
TARIFS_2026 = {
    "Taxi": (1000, 5000),
    "Clando": (200, 800),
    "Dakar Dem Dikk": (150, 350),
    "Car rapide": (100, 300),
    "Minibus Tata (AFTU)": (150, 300),
    "Jakarta (moto-taxi)": (1000, 3000),
    "TER": (1500, 2500),
    "BRT (Bus Rapid Transit)": (400, 500),
}


def _mettre_a_jour_tarifs_2026(cursor):
    """Recale les fourchettes de prix de chaque moyen de transport vers des
    valeurs 2026 plus réalistes. Fonctionne par UPDATE sur le nom, comme
    _raccourcir_conseils_verbeux : met bien à jour les lignes déjà
    présentes sur une base existante (pas seulement à la création)."""
    for nom, (cout_min, cout_max) in TARIFS_2026.items():
        cursor.execute(
            "UPDATE moyens_transport SET cout_min = ?, cout_max = ? "
            "WHERE nom = ? AND (cout_min != ? OR cout_max != ?)",
            (cout_min, cout_max, nom, cout_min, cout_max)
        )


# Descriptions retravaillées pour les 3 transports mis en avant sur
# l'accueil (Taxi, Clando, Minibus Tata) : les phrases d'origine, denses et
# à rallonge, sont remplacées par un ton plus direct et parlé. Ce champ
# étant partagé avec /transports, le bénéfice profite à tout le site.
DESCRIPTIONS_NATURELLES = {
    "Taxi": "Le taxi jaune et noir de Dakar, pour un trajet direct sans détour. Le prix se négocie avec le chauffeur avant de monter.",
    "Clando": "Une voiture partagée sur un axe fixe, à tarif divisé entre passagers. Moins cher qu'un taxi, un peu moins confortable.",
    "Minibus Tata (AFTU)": "Le minibus qui dessert la quasi-totalité des quartiers de Dakar, à prix fixe et très abordable.",
}


def _naturaliser_descriptions_transport(cursor):
    """Recale la description de quelques transports vers un ton plus
    naturel et moins encyclopédique (UPDATE conditionné au contenu actuel,
    donc sûr à rejouer sur une base déjà à jour)."""
    for nom, description in DESCRIPTIONS_NATURELLES.items():
        cursor.execute(
            "UPDATE moyens_transport SET description = ? WHERE nom = ? AND description != ?",
            (description, nom, description)
        )


def _migrer_taxi_et_clando(cursor):
    """Le taxi (officiel, réglementé) et le clando (taxi clandestin,
    informel et collectif) étaient historiquement regroupés dans une seule
    ligne 'Taxi clando' de `moyens_transport`. On les traite désormais comme
    deux moyens de transport distincts et synchronisés avec le reste de la
    base (mêmes colonnes, mêmes conventions).

    Migration idempotente :
    - si 'Taxi clando' existe encore, on la renomme en 'Taxi' (on conserve
      son id_transport pour ne rien casser côté relations existantes) ;
    - si 'Clando' n'existe pas encore, on l'insère avec ses propres tarifs,
      photo et capacité.
    """
    ancien = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom = 'Taxi clando'"
    ).fetchone()
    if ancien:
        cursor.execute(
            """UPDATE moyens_transport SET
                   nom = 'Taxi',
                   image_url = '/static/img/taxi.jpg',
                   description = 'Le taxi jaune et noir de Dakar, pour un trajet direct sans détour. Le prix se négocie avec le chauffeur avant de monter.',
                   cout_min = 1000,
                   cout_max = 5000,
                   avantages = 'Rapide, disponible partout, trajet direct porte-à-porte, véhicule identifiable et réglementé',
                   inconvenients = 'Prix à négocier, confort variable, pas de compteur systématique'
               WHERE id_transport = ?""",
            (ancien["id_transport"],)
        )

    existe_clando = cursor.execute(
        "SELECT 1 FROM moyens_transport WHERE nom = 'Clando'"
    ).fetchone()
    if not existe_clando:
        cursor.execute(
            """INSERT INTO moyens_transport
                   (nom, image_url, description, cout_min, cout_max, niveau_confort, disponibilite, avantages, inconvenients)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "Clando", "/static/img/clando.jpg",
                "Une voiture partagée sur un axe fixe, à tarif divisé entre passagers. Moins cher qu'un taxi, un peu moins confortable.",
                200, 800, "Faible", "24h/24",
                "Très économique car partagé, dense dans les quartiers périphériques, facile à héler aux points de rassemblement informels",
                "Aucun signe distinctif officiel, prix variable selon le trajet et les pratiques locales, confort limité, pas toujours sécurisant",
            )
        )


def _ajouter_transport_ndiaga_ndiaye(cursor):
    """Ajoute le Ndiaga Ndiaye (minibus blanc de transport collectif, souvent
    construit sur d'anciens châssis Mercedes-Benz) à la page /transports.
    Idempotent : n'insère que si ce moyen de transport n'existe pas déjà."""
    existe = cursor.execute(
        "SELECT 1 FROM moyens_transport WHERE nom = 'Ndiaga Ndiaye'"
    ).fetchone()
    if existe:
        return
    cursor.execute(
        """INSERT INTO moyens_transport
               (nom, image_url, description, cout_min, cout_max, niveau_confort, disponibilite, avantages, inconvenients)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "Ndiaga Ndiaye", "",
            "Minibus blanc, souvent construit sur d'anciens châssis Mercedes-Benz, très utilisé pour le transport "
            "collectif au Sénégal. Dessert Dakar et sa banlieue (Pikine, Guédiawaye, Keur Massar, Rufisque...) ainsi "
            "que quelques liaisons interurbaines, surtout le matin et aux heures de pointe.",
            100, 350, "Faible", "Le matin et aux heures de pointe",
            "Dessert de nombreuses destinations, plus économique qu'un taxi, très présent dans la banlieue de Dakar, "
            "accès à des zones moins bien desservies",
            "Très chargé aux heures de pointe, confort parfois limité, temps d'attente variable selon les lignes",
        )
    )


def _corriger_id_transport_errones(cursor):
    """Corrige un bug hérité de la scission Taxi/Clando : l'insertion de la
    nouvelle ligne 'Clando' juste après 'Taxi' dans moyens_transport a
    décalé d'un cran les id_transport de tous les moyens suivants (Dakar
    Dem Dikk, Car rapide, Minibus Tata, Jakarta, TER, BRT), mais les lignes
    de bus de la donnée d'origine référençaient encore les anciens
    id_transport codés en dur. Résultat : des lignes Tata comptées comme
    Car rapide, des lignes Car rapide comptées comme Dakar Dem Dikk, etc.

    Corrige chaque ligne en se basant sur le texte de sa propre
    description (qui, lui, a toujours été correct, ex. "Minibus Tata
    (AFTU) reliant..."), plutôt que sur un décalage numérique supposé —
    fonctionne donc quel que soit l'état exact de la base. Idempotent : ne
    modifie que les lignes encore mal rattachées."""
    corrections = [
        ('Dakar Dem Dikk', 'Dakar Dem Dikk %'),
        ('Car rapide', 'Car rapide %'),
        ('Minibus Tata (AFTU)', 'Minibus Tata (AFTU) %'),
        ('TER', 'TER %'),
        ('BRT (Bus Rapid Transit)', 'BRT (Bus Rapid Transit) %'),
    ]
    for nom_transport, motif_description in corrections:
        id_correct = cursor.execute(
            "SELECT id_transport FROM moyens_transport WHERE nom = ?", (nom_transport,)
        ).fetchone()
        if not id_correct:
            continue
        cursor.execute(
            "UPDATE lignes_bus SET id_transport = ? WHERE description LIKE ? AND id_transport != ?",
            (id_correct[0], motif_description, id_correct[0])
        )


CONSEILS_RETIRES = (
    'Vêtements adaptés',
    'Climatisation non garantie',
    'Se protéger du soleil',
    'Affluence pendant les vacances',
    'Prévoir du temps en saison des pluies',
)


def _purger_conseils_obsoletes(cursor):
    """Retire quelques conseils jugés redondants ou trop anecdotiques pour
    alléger la page /conseils, et corrige le numéro national du SAMU
    (1515 au Sénégal, à ne pas confondre avec le 15 français)."""
    cursor.executemany(
        "DELETE FROM conseils WHERE titre = ?",
        [(titre,) for titre in CONSEILS_RETIRES]
    )
    cursor.execute(
        "UPDATE infos_utiles SET valeur = '1515' "
        "WHERE categorie = 'Urgence' AND libelle LIKE '%SAMU%' AND valeur != '1515'"
    )


def _reseeder_donnees_manquantes(cursor):
    """Réinsère les conseils / infos utiles si les tables correspondantes
    sont vides (base créée avant l'ajout de ces données)."""
    if cursor.execute("SELECT COUNT(*) AS n FROM conseils").fetchone()["n"] == 0:
        cursor.executemany(
            "INSERT INTO conseils (categorie, titre, contenu, periode) VALUES (?, ?, ?, ?)",
            [
                ('Avant de partir', 'Prévoir de la monnaie', "Gardez des petites coupures : les chauffeurs ont rarement la monnaie sur un gros billet.", "Toute l'année"),
                ('Dans le transport', 'Négocier avant de monter', 'Taxis et clandos : fixez toujours le prix avant de monter.', "Toute l'année"),
                ('Dans le transport', 'Vérifier la destination', 'Confirmez la destination avec le chauffeur avant de partir.', "Toute l'année"),
                ('Argent et paiement', 'Montant fixe pour le DDD et le BRT', 'DDD et BRT appliquent un tarif fixe, sans négociation.', "Toute l'année"),
                ('Argent et paiement', "Éviter de montrer trop d'argent", 'Ne sortez que la somme nécessaire au moment de payer.', "Toute l'année"),
                ('Saisons et météo', 'Circulation dense le vendredi', 'Circulation très dense le vendredi après-midi (travail et prière).', 'Heures de pointe'),
                ('Saisons et météo', 'Éviter les heures de pointe', 'Heures de pointe : 7h-9h et 17h-20h. Prévoyez une marge.', 'Heures de pointe'),
                ('Pour les femmes', 'Privilégier les transports connus', 'Le soir, préférez le TER, le BRT ou le DDD à un taxi inconnu.', "Toute l'année"),
            ]
        )

    if cursor.execute("SELECT COUNT(*) AS n FROM infos_utiles").fetchone()["n"] == 0:
        cursor.executemany(
            "INSERT INTO infos_utiles (categorie, libelle, valeur) VALUES (?, ?, ?)",
            [
                ('Urgence', 'Police nationale', '17'),
                ('Urgence', 'SAMU (urgences médicales)', '1515'),
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
# Conseils "Cars rapides" et "Tata (bus)" : retours de terrain sur les
# usages réels à bord (tarifs, rôle de l'apprenti, paiement, descente),
# ajoutés après le lancement initial de la page /conseils.
# ---------------------------------------------------------------------
NOUVEAUX_CONSEILS_CARS_RAPIDES_ET_TATA = [
    (
        'Cars rapides', 'Le tarif de base tourne autour de 100 FCFA',
        "Trajet court : comptez environ 100 FCFA, un bon repère contre les tarifs exagérés.",
        "Toute l'année"
    ),
    (
        'Cars rapides', 'Face à un tarif qui semble abusif',
        "Tarif trop élevé ? Demandez une explication à l'apprenti ou descendez avant le départ.",
        "Toute l'année"
    ),
    (
        'Cars rapides', "Suivre les consignes de l'apprenti",
        "L'apprenti donne les consignes à bord : suivez-les, même sans comprendre le wolof.",
        "Toute l'année"
    ),
    (
        'Cars rapides', 'Frapper la carrosserie pour signaler votre arrêt',
        "Pour descendre, frappez doucement la carrosserie : c'est le signal habituel.",
        "Toute l'année"
    ),
    (
        'Cars rapides', 'Le remplissage varie selon les contrôles',
        "Le remplissage et les arrêts respectés varient selon les contrôles routiers.",
        "Toute l'année"
    ),
    (
        'Tata (bus)', 'La chaîne de paiement entre passagers',
        "L'argent circule parfois de main en main entre passagers. Restez discret si besoin.",
        "Toute l'année"
    ),
    (
        'Tata (bus)', "Conserver son ticket jusqu'à la fin du trajet",
        "Gardez votre ticket jusqu'à la descente : un contrôle peut le demander.",
        "Toute l'année"
    ),
    (
        'Tata (bus)', 'Anticiper sa descente',
        "Repérez les arrêts à l'avance pour ne pas dépasser votre destination.",
        "Toute l'année"
    ),
]

NOUVEAUX_CONSEILS_NDIAGA_NDIAYE = [
    (
        'Ndiaga Ndiaye', 'Confirmer la destination avant de monter',
        "Demandez au receveur où va le véhicule avant de monter : les Ndiaga Ndiaye n'affichent pas toujours leur destination.",
        "Toute l'année"
    ),
    (
        'Ndiaga Ndiaye', 'Prévoir de la petite monnaie à bord',
        "Ayez des petites coupures sur vous : la monnaie facilite et accélère le paiement à bord.",
        "Toute l'année"
    ),
    (
        'Ndiaga Ndiaye', 'Prévenir avant de descendre',
        "Repérez votre arrêt à l'avance et prévenez quelques instants avant, le temps que le véhicule s'arrête.",
        "Toute l'année"
    ),
    (
        'Ndiaga Ndiaye', 'Demander en cas de doute',
        "Un doute sur l'itinéraire ? Le receveur ou les autres passagers vous orienteront volontiers.",
        "Toute l'année"
    ),
]

# Relecture éditoriale : version raccourcie de l'ensemble des conseils
# (les 8 conseils de base + les 8 Cars rapides/Tata), jugés trop longs pour
# une carte compacte. Appliquée via UPDATE (voir _raccourcir_conseils_verbeux)
# pour couvrir aussi les bases déjà migrées, où les anciens textes verbeux
# sont déjà en place.
NOUVEAUX_CONSEILS_TEXTE_RACCOURCI = [
    ('Prévoir de la monnaie', "Gardez des petites coupures : les chauffeurs ont rarement la monnaie sur un gros billet."),
    ('Négocier avant de monter', "Taxis et clandos : fixez toujours le prix avant de monter."),
    ('Vérifier la destination', "Confirmez la destination avec le chauffeur avant de partir."),
    ('Montant fixe pour le DDD et le BRT', "DDD et BRT appliquent un tarif fixe, sans négociation."),
    ("Éviter de montrer trop d'argent", "Ne sortez que la somme nécessaire au moment de payer."),
    ('Circulation dense le vendredi', "Circulation très dense le vendredi après-midi (travail et prière)."),
    ('Éviter les heures de pointe', "Heures de pointe : 7h-9h et 17h-20h. Prévoyez une marge."),
    ('Privilégier les transports connus', "Le soir, préférez le TER, le BRT ou le DDD à un taxi inconnu."),
    (
        'Le tarif de base tourne autour de 100 FCFA',
        "Trajet court : comptez environ 100 FCFA, un bon repère contre les tarifs exagérés."
    ),
    (
        'Face à un tarif qui semble abusif',
        "Tarif trop élevé ? Demandez une explication à l'apprenti ou descendez avant le départ."
    ),
    (
        "Suivre les consignes de l'apprenti",
        "L'apprenti donne les consignes à bord : suivez-les, même sans comprendre le wolof."
    ),
    (
        'Frapper la carrosserie pour signaler votre arrêt',
        "Pour descendre, frappez doucement la carrosserie : c'est le signal habituel."
    ),
    (
        'Le remplissage varie selon les contrôles',
        "Le remplissage et les arrêts respectés varient selon les contrôles routiers."
    ),
    (
        'La chaîne de paiement entre passagers',
        "L'argent circule parfois de main en main entre passagers. Restez discret si besoin."
    ),
    (
        "Conserver son ticket jusqu'à la fin du trajet",
        "Gardez votre ticket jusqu'à la descente : un contrôle peut le demander."
    ),
    (
        'Anticiper sa descente',
        "Repérez les arrêts à l'avance pour ne pas dépasser votre destination."
    ),
]


def _ajouter_conseils_cars_rapides_et_tata(cursor):
    """Ajoute les conseils Cars rapides / Tata s'ils n'existent pas déjà
    (vérification par titre), sans jamais dupliquer sur une base déjà à jour."""
    for categorie, titre, contenu, periode in NOUVEAUX_CONSEILS_CARS_RAPIDES_ET_TATA:
        existe = cursor.execute("SELECT 1 FROM conseils WHERE titre = ?", (titre,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO conseils (categorie, titre, contenu, periode) VALUES (?, ?, ?, ?)",
                (categorie, titre, contenu, periode)
            )


def _ajouter_conseils_ndiaga_ndiaye(cursor):
    """Ajoute les conseils pratiques Ndiaga Ndiaye s'ils n'existent pas déjà
    (vérification par titre), même logique que _ajouter_conseils_cars_rapides_et_tata."""
    for categorie, titre, contenu, periode in NOUVEAUX_CONSEILS_NDIAGA_NDIAYE:
        existe = cursor.execute("SELECT 1 FROM conseils WHERE titre = ?", (titre,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO conseils (categorie, titre, contenu, periode) VALUES (?, ?, ?, ?)",
                (categorie, titre, contenu, periode)
            )


def _raccourcir_conseils_verbeux(cursor):
    """Recale le texte de quelques conseils vers une version plus concise
    (relecture éditoriale pour la soutenance). Fonctionne par UPDATE sur le
    titre : contrairement à _ajouter_conseils_cars_rapides_et_tata (qui
    n'insère que si le titre est absent), cette fonction met bien à jour le
    contenu des lignes déjà présentes sur une base existante."""
    for titre, contenu in NOUVEAUX_CONSEILS_TEXTE_RACCOURCI:
        cursor.execute(
            "UPDATE conseils SET contenu = ? WHERE titre = ? AND contenu != ?",
            (contenu, titre, contenu)
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

# ---------------------------------------------------------------------
# REFONTE DU LEXIQUE WOLOF (page /wolof) — voir _reorganiser_lexique_wolof_transport
# ---------------------------------------------------------------------
# Les intitulés grammaticaux d'origine ('Salutations', 'Politesse',
# 'Négociation', 'Transport', 'Direction', 'Nombres', 'Urgence') sont
# remplacés par des catégories pensées autour d'une situation réelle de
# déplacement à Dakar. Chaque entrée : (wolof, nouvelle_situation, contexte
# ou None). Le texte wolof sert de clé (inchangé) : cette table ne modifie
# jamais le wolof/français/phonétique déjà validés, seulement le
# classement et, pour certaines phrases, un petit contexte d'usage.
RECLASSEMENT_PHRASES_WOLOF = [
    ('Salaam aleekum', 'Saluer', "Salutation standard, à toute heure de la journée"),
    ('Maleekum salaam', 'Saluer', "Réponse automatique à « Salaam aleekum »"),
    ('Nanga def ?', 'Saluer', None),
    ('Maa ngi fi', 'Saluer', "Réponse à « Nanga def ? »"),
    ('Jamm ak jamm', 'Saluer', "Autre réponse possible à « Nanga def ? »"),
    ('Ana yow ?', 'Saluer', None),
    ('Naka nga tudd ?', 'Saluer', None),

    ('Jërejëf', 'Remercier et prendre congé', None),
    ('Amul solo', 'Remercier et prendre congé', "Réponse habituelle à un merci"),
    ('Ba beneen yoon', 'Remercier et prendre congé', None),
    ('Ballago', 'Remercier et prendre congé', None),
    ('Ma mangi dem', 'Remercier et prendre congé', None),

    ('Baal ma', 'Poser une question', "À dire avant toute question à un inconnu"),
    ('Waaw', 'Poser une question', None),
    ('Déedéet', 'Poser une question', None),
    ('Ndank ndank', 'Poser une question', "Pour demander de répéter ou de ralentir"),
    ('Baal ma, dama bëgg laa laaj', 'Poser une question', None),
    ('Su la neexee', 'Poser une question', None),

    ('Nak bu baax ?', 'Payer et connaître le tarif', None),
    ('Ñaata la ?', 'Payer et connaître le tarif', None),
    ('Dafa seer', 'Payer et connaître le tarif', None),
    ('Dafa seer lool', 'Payer et connaître le tarif', None),
    ('Baax na', 'Payer et connaître le tarif', "Pour valider un prix négocié"),
    ('Dina dem', 'Payer et connaître le tarif', "Argument de négociation si le prix reste trop élevé"),
    ('Dafa yomb', 'Payer et connaître le tarif', None),
    ('Wesaare', 'Payer et connaître le tarif', None),
    ('Benn, ñaar, ñett', 'Payer et connaître le tarif', "Utile pour comprendre un prix annoncé"),
    ('Ñeent, juróom', 'Payer et connaître le tarif', None),
    ('Juróom-benn', 'Payer et connaître le tarif', None),
    ('Fukk', 'Payer et connaître le tarif', None),
    ('Fukk ak juróom', 'Payer et connaître le tarif', None),
    ('Téeméer', 'Payer et connaître le tarif', None),

    ('Dem ci [lieu]', 'Monter dans un Tata', "À dire directement au chauffeur ou au receveur"),
    ('Dama bëgg dem [lieu]', 'Monter dans un Tata', "Variante un peu plus polie de « Dem ci »"),
    ('Ban gaal moo dem [lieu] ?', 'Monter dans un Tata', "Utile si plusieurs véhicules attendent au même endroit"),
    ('Fan la gare bi nekk ?', 'Monter dans un Tata', None),
    ('Kañ nga dem ?', 'Monter dans un Tata', "À demander au chauffeur qui attend encore des passagers"),
    ('Bus bi dafa fees', 'Monter dans un Tata', None),
    ('Ana taxi yi ?', 'Monter dans un Tata', None),

    ('Taxawal fii !', 'Demander un arrêt', None),
    ('Yëgël ma ci...', 'Demander un arrêt', None),
    ('Wàcc fi !', 'Demander un arrêt', "Peut être dit par le receveur pour indiquer votre arrêt"),

    ('Fan la [lieu] nekk ?', 'Demander son chemin', None),
    ('Jëm ci kanam', 'Demander son chemin', None),
    ('Ci kanam rekk', 'Demander son chemin', None),
    ('Jëm ci ndey', 'Demander son chemin', None),
    ('Jëm ci kaw', 'Demander son chemin', None),
    ('Yagg na ?', 'Demander son chemin', None),
    ('Foofu la', 'Demander son chemin', None),
    ('Fii la', 'Demander son chemin', None),

    ('Dama metti', 'Situations d\'urgence', None),
    ('Wóoy !', 'Situations d\'urgence', None),
    ('Sama xel dafa tang', 'Situations d\'urgence', None),
    ('Wallal ma !', 'Situations d\'urgence', "Interpellation directe, pour une urgence réelle"),
    ('Fabu police bi', 'Situations d\'urgence', None),
]

# Nouvelles expressions ajoutées pour couvrir les situations concrètes d'un
# trajet en Tata/taxi/Jakarta à Dakar (montée, arrêt, chemin, paiement,
# urgence). Wolof standard tel qu'employé à Dakar — y compris les emprunts
# au français (« arrêt », « gare », « BRT », « TER »...) couramment utilisés
# tels quels dans une phrase wolof, comme c'est réellement le cas au
# quotidien pour le vocabulaire des transports modernes.
# Chaque entrée : (wolof, francais, phonetique, situation, contexte ou None).
NOUVELLES_PHRASES_WOLOF_TRANSPORT = [
    ('Naka guddi gi ?', 'Bonsoir, comment se passe la soirée ?', 'na-ka gou-di gui', 'Saluer', "Salutation utilisée en fin de journée"),

    ('Tata bii, dafa dem [lieu] ?', 'Ce Tata va-t-il à [lieu] ?', 'ta-ta bii da-fa dem', 'Monter dans un Tata', "À demander avant de monter"),
    ('Ban ligne moo dem [lieu] ?', 'Quelle ligne va à [lieu] ?', 'ban ligne mo dem', 'Monter dans un Tata', None),
    ('Ligne bii, dafa jaar ci [lieu] ?', 'Cette ligne passe-t-elle par [lieu] ?', 'ligne bii da-fa diar si', 'Monter dans un Tata', None),
    ('Fan la bus bii di jaar ?', 'Où passe cette ligne ?', 'fan la bous bii di diar', 'Monter dans un Tata', None),
    ('Fan la terminus bi nekk ?', 'Où est le terminus ?', 'fan la ter-mi-nuss bi nèk', 'Monter dans un Tata', None),
    ('Fan laa mëna jël BRT bi ?', 'Où puis-je prendre le BRT ?', 'fan la mè-na djël bi-èr-té bi', 'Monter dans un Tata', None),
    ('Fan laa mëna jël TER bi ?', 'Où puis-je prendre le TER ?', 'fan la mè-na djël té-euh-èr bi', 'Monter dans un Tata', None),
    ('Am na correspondance ?', 'Y a-t-il une correspondance ?', 'am na kor-res-pon-dans', 'Monter dans un Tata', None),
    ('Ñaata waxtu la war ?', 'Combien de temps faut-il ?', 'nya-ta wakh-tou la war', 'Monter dans un Tata', None),
    ('Xibaar ma bu nu egsee', 'Pouvez-vous me prévenir quand nous arrivons ?', 'xi-baar ma bou nou èg-sé', 'Monter dans un Tata', "À dire en montant si vous ne connaissez pas le trajet"),

    ('Fan la arrêt bi nekk ?', 'Où est cet arrêt ?', 'fan la a-rè bi nèk', 'Demander un arrêt', None),
    ('Fan laa wara wàcc ?', 'Où dois-je descendre ?', 'fan la wa-ra watch', 'Demander un arrêt', None),
    ('Fii, mooy sama arrêt ?', 'Cet arrêt est-il le bon ?', 'fi-i mo-y sa-ma a-rè', 'Demander un arrêt', "Pour confirmer avant de descendre"),
    ('Ban arrêt bu topp ?', 'Quel est le prochain arrêt ?', 'ban a-rè bou top', 'Demander un arrêt', None),

    ('Réer naa', 'Je suis perdu(e)', 'ré-èr na', 'Demander son chemin', None),
    ('Wallal ma, su la neexee', 'Pouvez-vous m\'aider ?', 'wa-lal ma sou la né-é', 'Demander son chemin', "Formule polie, à distinguer du « Wallal ma ! » d'urgence"),
    ('Dama wut universite bi', 'Je cherche l\'université', 'da-ma wout u-ni-vèr-si-té bi', 'Demander son chemin', None),
    ('Dama wut opitaal bi', 'Je cherche l\'hôpital', 'da-ma wout o-pi-tal bi', 'Demander son chemin', None),
    ('Dama wut marse bi', 'Je cherche le marché', 'da-ma wout mar-sé bi', 'Demander son chemin', None),
    ('Dama wut Plateau bi', 'Je cherche le centre-ville (le Plateau)', 'da-ma wout pla-to bi', 'Demander son chemin', None),
    ('Dama wut tefes bi', 'Je cherche la plage', 'da-ma wout té-fess bi', 'Demander son chemin', None),
    ('Dama wut station bi', 'Je cherche la station', 'da-ma wout sta-syon bi', 'Demander son chemin', None),

    ('Ñaata la trajet bi ?', 'Combien coûte le trajet ?', 'nya-ta la tra-djè bi', 'Payer et connaître le tarif', None),
    ('Fii laa fey ?', 'Je paie ici ?', 'fi-i la féy', 'Payer et connaître le tarif', None),
    ('Amuma wesaare', "Je n'ai pas de monnaie", 'a-mou-ma wé-sa-ré', 'Payer et connaître le tarif', None),
    ('Wesaareal ma', 'Pouvez-vous rendre la monnaie ?', 'wé-sa-ré-al ma', 'Payer et connaître le tarif', None),

    ('Waxuma wolof', 'Je ne parle pas wolof', 'wa-xou-ma wo-lof', 'Poser une question', "Pour prévenir tout de suite votre interlocuteur"),
    ('Dégg nga farañse ?', 'Parlez-vous français ?', 'dègue nga fa-rañ-sé', 'Poser une question', None),
    ('Dégg nga angale ?', 'Parlez-vous anglais ?', 'dègue nga an-ga-lé', 'Poser une question', None),

    ('Jërejëf, chauffeur !', 'Merci chauffeur', 'djé-ré-djef so-fer', 'Remercier et prendre congé', None),
    ('Jërejëf, apprenti !', 'Merci receveur', 'djé-ré-djef a-pran-ti', 'Remercier et prendre congé', "« Apprenti » désigne le receveur qui collecte les tickets dans le Tata"),
    ('Fanaan ak jamm', 'Bonne soirée / bonne nuit', 'fa-naan ak diam', 'Remercier et prendre congé', "Pour se quitter en fin de journée"),
]


def _reorganiser_lexique_wolof_transport(cursor):
    """Reclasse le lexique wolof existant dans des catégories orientées
    situation de déplacement (voir RECLASSEMENT_PHRASES_WOLOF) et ajoute les
    nouvelles expressions de NOUVELLES_PHRASES_WOLOF_TRANSPORT. Idempotent :
    le reclassement est un UPDATE sans condition sur la valeur actuelle (sûr
    à rejouer) ; pour les nouvelles phrases, `situation` est elle aussi
    remise à jour si la phrase existe déjà (et pas seulement insérée si
    absente), afin qu'un changement d'intitulé de catégorie se propage
    toujours aux lignes déjà en base plutôt que de rester figé."""
    for wolof, situation, contexte in RECLASSEMENT_PHRASES_WOLOF:
        cursor.execute(
            "UPDATE phrases_wolof SET situation = ?, contexte = COALESCE(contexte, ?) WHERE wolof = ?",
            (situation, contexte, wolof)
        )

    for wolof, francais, phonetique, situation, contexte in NOUVELLES_PHRASES_WOLOF_TRANSPORT:
        existe = cursor.execute("SELECT 1 FROM phrases_wolof WHERE wolof = ?", (wolof,)).fetchone()
        if existe:
            cursor.execute(
                "UPDATE phrases_wolof SET situation = ?, contexte = COALESCE(contexte, ?) WHERE wolof = ?",
                (situation, contexte, wolof)
            )
        else:
            cursor.execute(
                "INSERT INTO phrases_wolof (wolof, francais, phonetique, situation, contexte) VALUES (?, ?, ?, ?, ?)",
                (wolof, francais, phonetique, situation, contexte)
            )


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

# ---------------------------------------------------------------------
# Deuxième vague d'enrichissement du réseau Minibus Tata (AFTU) : le
# réseau est le moyen de transport en commun le moins cher de Dakar et le
# plus adapté au budget étudiant, mais restait sous-représenté par rapport
# au nombre réel de lignes AFTU. On densifie ici la couverture de quartiers
# déjà référencés dans `lieux` mais encore mal desservis par une ligne
# directe (Hann Maristes, Sicap Liberté, Rufisque profond, etc.).
# ---------------------------------------------------------------------
NOUVELLES_LIGNES_MINIBUS_2 = [
    {
        "numero_ligne": "Ligne 81", "nom_ligne": "Petersen - Hann Maristes",
        "description": "Minibus Tata (AFTU) reliant Petersen à Hann Maristes via Hann, Hann Bel-Air",
        "arrets": ["Petersen", "Hann", "Hann Bel-Air", "Hann Maristes"],
    },
    {
        "numero_ligne": "Ligne 82", "nom_ligne": "Sandaga - Sicap Liberté",
        "description": "Minibus Tata (AFTU) reliant Sandaga à Sicap Liberté via Colobane, HLM, Liberté 1",
        "arrets": ["Sandaga", "Colobane", "HLM", "Liberté 1", "Sicap Liberté"],
    },
    {
        "numero_ligne": "Ligne 83", "nom_ligne": "Médina - Fenêtre Mermoz",
        "description": "Minibus Tata (AFTU) reliant Médina à Fenêtre Mermoz via Fass, Point E, Amitié",
        "arrets": ["Médina", "Fass", "Point E", "Amitié", "Fenêtre Mermoz"],
    },
    {
        "numero_ligne": "Ligne 84", "nom_ligne": "Grand Yoff - Cité Assemblée",
        "description": "Minibus Tata (AFTU) reliant Grand Yoff à Cité Assemblée via Zone de Captage",
        "arrets": ["Grand Yoff", "Zone de Captage", "Cité Assemblée"],
    },
    {
        "numero_ligne": "Ligne 85", "nom_ligne": "Colobane - Yarakh",
        "description": "Minibus Tata (AFTU) reliant Colobane à Yarakh via Hann",
        "arrets": ["Colobane", "Hann", "Yarakh"],
    },
    {
        "numero_ligne": "Ligne 86", "nom_ligne": "Petersen - Cité Comico",
        "description": "Minibus Tata (AFTU) reliant Petersen à Cité Comico via Grand Dakar, Dieuppeul",
        "arrets": ["Petersen", "Grand Dakar", "Dieuppeul", "Cité Comico"],
    },
    {
        "numero_ligne": "Ligne 87", "nom_ligne": "Pikine - Cité Aliou Sow",
        "description": "Minibus Tata (AFTU) reliant Pikine à Cité Aliou Sow via Thiaroye Gare",
        "arrets": ["Pikine", "Thiaroye Gare", "Cité Aliou Sow"],
    },
    {
        "numero_ligne": "Ligne 88", "nom_ligne": "Mbao - Cité Millionnaire",
        "description": "Minibus Tata (AFTU) reliant Mbao à Cité Millionnaire via Petit Mbao",
        "arrets": ["Mbao", "Petit Mbao", "Cité Millionnaire"],
    },
    {
        "numero_ligne": "Ligne 89", "nom_ligne": "Rufisque - Diokoul",
        "description": "Minibus Tata (AFTU) reliant Rufisque à Diokoul via Rufisque Nord",
        "arrets": ["Rufisque", "Rufisque Nord", "Diokoul"],
    },
    {
        "numero_ligne": "Ligne 90", "nom_ligne": "Rufisque - Arafat",
        "description": "Minibus Tata (AFTU) reliant Rufisque à Arafat via Rufisque Est",
        "arrets": ["Rufisque", "Rufisque Est", "Arafat"],
    },
]

# ---------------------------------------------------------------------
# Enrichissement massif du réseau Car Rapide : à budget étudiant égal, le
# car rapide reste le moyen de transport le moins cher de Dakar (100-200
# FCFA la course) mais n'était couvert que par 4 lignes (CR-1 à CR-4),
# très en retrait par rapport au réseau minibus Tata. On porte le réseau
# à 20 lignes pour refléter la densité réelle du car rapide sur les grands
# axes de la capitale et de la banlieue.
# ---------------------------------------------------------------------
NOUVELLES_LIGNES_CAR_RAPIDE = [
    {
        "numero_ligne": "CR-5", "nom_ligne": "Colobane - Guédiawaye (Car rapide)",
        "description": "Car rapide reliant Colobane à Guédiawaye via Grand Dakar, HLM, Front de Terre, Parcelles Assainies, Golf",
        "arrets": ["Colobane", "Grand Dakar", "HLM", "Front de Terre", "Parcelles Assainies", "Golf"],
    },
    {
        "numero_ligne": "CR-6", "nom_ligne": "Petersen - Yoff (Car rapide)",
        "description": "Car rapide reliant Petersen à Yoff via Bopp, Fann, Ouakam, Ngor",
        "arrets": ["Petersen", "Bopp", "Fann", "Ouakam", "Ngor", "Yoff"],
    },
    {
        "numero_ligne": "CR-7", "nom_ligne": "Sandaga - Keur Massar (Car rapide)",
        "description": "Car rapide reliant Sandaga à Keur Massar via Colobane, Pikine, Thiaroye, Yeumbeul",
        "arrets": ["Sandaga", "Colobane", "Pikine", "Thiaroye", "Yeumbeul", "Keur Massar"],
    },
    {
        "numero_ligne": "CR-8", "nom_ligne": "Médina - Almadies (Car rapide)",
        "description": "Car rapide reliant Médina à Almadies via Fass, Point E, Mermoz, Ngor",
        "arrets": ["Médina", "Fass", "Point E", "Mermoz", "Ngor", "Almadies"],
    },
    {
        "numero_ligne": "CR-9", "nom_ligne": "Plateau - Rufisque (Car rapide)",
        "description": "Car rapide reliant Plateau à Rufisque via Hann Bel-Air, Thiaroye sur Mer, Rufisque Nord",
        "arrets": ["Plateau", "Hann Bel-Air", "Thiaroye sur Mer", "Rufisque Nord", "Rufisque"],
    },
    {
        "numero_ligne": "CR-10", "nom_ligne": "Colobane - Malika (Car rapide)",
        "description": "Car rapide reliant Colobane à Malika via Cambérène, Thiaroye sur Mer",
        "arrets": ["Colobane", "Cambérène", "Thiaroye sur Mer", "Malika"],
    },
    {
        "numero_ligne": "CR-11", "nom_ligne": "Petersen - Diamniadio (Car rapide)",
        "description": "Car rapide reliant Petersen à Diamniadio via Grand Mbao, Bargny",
        "arrets": ["Petersen", "Grand Mbao", "Bargny", "Diamniadio"],
    },
    {
        "numero_ligne": "CR-12", "nom_ligne": "Sandaga - Golf (Car rapide)",
        "description": "Car rapide reliant Sandaga à Golf via HLM, Patte d'Oie, Parcelles Assainies",
        "arrets": ["Sandaga", "HLM", "Patte d'Oie", "Parcelles Assainies", "Golf"],
    },
    {
        "numero_ligne": "CR-13", "nom_ligne": "Médina - Sicap Baobab (Car rapide)",
        "description": "Car rapide reliant Médina à Sicap Baobab via Fass, Liberté 2, Sicap Karack",
        "arrets": ["Médina", "Fass", "Liberté 2", "Sicap Karack", "Sicap Baobab"],
    },
    {
        "numero_ligne": "CR-14", "nom_ligne": "Petersen - Front de Terre (Car rapide)",
        "description": "Car rapide reliant Petersen à Front de Terre via Grand Dakar, Biscuiterie, HLM",
        "arrets": ["Petersen", "Grand Dakar", "Biscuiterie", "HLM", "Front de Terre"],
    },
    {
        "numero_ligne": "CR-15", "nom_ligne": "Colobane - Yeumbeul (Car rapide)",
        "description": "Car rapide reliant Colobane à Yeumbeul via Dalifort, Pikine, Guinaw Rail",
        "arrets": ["Colobane", "Dalifort", "Pikine", "Guinaw Rail", "Yeumbeul"],
    },
    {
        "numero_ligne": "CR-16", "nom_ligne": "Sandaga - Ouest Foire (Car rapide)",
        "description": "Car rapide reliant Sandaga à Ouest Foire via Grand Dakar, Grand Yoff, Zone de Captage",
        "arrets": ["Sandaga", "Grand Dakar", "Grand Yoff", "Zone de Captage", "Ouest Foire"],
    },
    {
        "numero_ligne": "CR-17", "nom_ligne": "Petersen - Cambérène (Car rapide)",
        "description": "Car rapide reliant Petersen à Cambérène via Grand Yoff, Grand Médine, Parcelles Assainies",
        "arrets": ["Petersen", "Grand Yoff", "Grand Médine", "Parcelles Assainies", "Cambérène"],
    },
    {
        "numero_ligne": "CR-18", "nom_ligne": "Rufisque - Diamniadio (Car rapide)",
        "description": "Car rapide reliant Rufisque à Diamniadio via Rufisque Est, Bargny",
        "arrets": ["Rufisque", "Rufisque Est", "Bargny", "Diamniadio"],
    },
    {
        "numero_ligne": "CR-19", "nom_ligne": "Guédiawaye - Keur Massar (Car rapide)",
        "description": "Car rapide reliant Guédiawaye à Keur Massar via Wakhinane, Médina Gounass",
        "arrets": ["Guédiawaye", "Wakhinane", "Médina Gounass", "Keur Massar"],
    },
    {
        "numero_ligne": "CR-20", "nom_ligne": "Petersen - Mbao (Car rapide)",
        "description": "Car rapide reliant Petersen à Mbao via Hann, Hann Bel-Air, Petit Mbao",
        "arrets": ["Petersen", "Hann", "Hann Bel-Air", "Petit Mbao", "Mbao"],
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
    ligne_transport_cr = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom = 'Car rapide'"
    ).fetchone()
    if not ligne_transport:
        return
    id_transport_tata = ligne_transport[0]
    id_transport_car_rapide = ligne_transport_cr[0] if ligne_transport_cr else None

    # Regroupe les 3 vagues d'enrichissement (Tata historique + Tata
    # densification + Car rapide) : chaque lot est associé à l'id_transport
    # correspondant, avec est_minibus=1 dans tous les cas (réseau minibus
    # au sens large = Tata + Car rapide, le duo le moins cher de Dakar).
    lots = [(NOUVELLES_LIGNES_MINIBUS, id_transport_tata), (NOUVELLES_LIGNES_MINIBUS_2, id_transport_tata)]
    if id_transport_car_rapide:
        lots.append((NOUVELLES_LIGNES_CAR_RAPIDE, id_transport_car_rapide))

    for lignes, id_transport_lot in lots:
        for ligne in lignes:
            existe = cursor.execute(
                "SELECT 1 FROM lignes_bus WHERE numero_ligne = ?", (ligne["numero_ligne"],)
            ).fetchone()
            if existe:
                continue

            cursor.execute(
                "INSERT INTO lignes_bus (numero_ligne, nom_ligne, id_transport, est_minibus, description) "
                "VALUES (?, ?, ?, 1, ?)",
                (ligne["numero_ligne"], ligne["nom_ligne"], id_transport_lot, ligne["description"])
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
                    (f"Arrêt {nom_lieu} ({ligne['numero_ligne']})", id_lieu, lat, lng)
                )
                id_arret = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO ligne_arrets (id_ligne, id_arret, ordre) VALUES (?, ?, ?)",
                    (id_ligne, id_arret, ordre)
                )


# ---------------------------------------------------------------------
# Réseau minibus curé autour du pôle SONATEL (siège social, sur la VDN
# entre Ouest Foire, Sacré-Cœur et Cité Keur Gorgui). Remplace l'ancienne
# liste générique de ~90 lignes Tata sur la page /minibus par une
# sélection d'itinéraires réels, centrée sur les quartiers où les
# étudiants sont les plus concentrés.
# ---------------------------------------------------------------------
LIEU_SONATEL = (
    'SONATEL', 'entreprise', 14.7259, -17.4793,
    "Siège social SONATEL / Orange, sur la Voie de Dégagement Nord (VDN) — repère central pour les minibus "
    "vers les quartiers étudiants (UCAD, Sacré-Cœur, Liberté 5/6...)"
)

LIGNES_MINIBUS_SONATEL = [
    {
        "numero_ligne": "SN-1", "nom_ligne": "SONATEL - UCAD",
        "description": "Minibus reliant le pôle SONATEL (VDN) à l'UCAD via Sacré-Cœur, Point E et Fann — l'un "
                       "des trajets les plus empruntés par les étudiants domiciliés côté VDN.",
        "arrets": ["SONATEL", "Sacré-Cœur", "Point E", "Fann", "UCAD"],
    },
    {
        "numero_ligne": "SN-2", "nom_ligne": "SONATEL - Ouakam",
        "description": "Minibus reliant SONATEL à Ouakam via Ouest Foire, sur un axe court et très fréquenté.",
        "arrets": ["SONATEL", "Ouest Foire", "Ouakam"],
    },
    {
        "numero_ligne": "SN-3", "nom_ligne": "SONATEL - Liberté 6",
        "description": "Minibus reliant SONATEL à Liberté 6 via Sacré-Cœur et Liberté 6 Extension.",
        "arrets": ["SONATEL", "Sacré-Cœur", "Liberté 6 Extension", "Liberté 6"],
    },
    {
        "numero_ligne": "SN-4", "nom_ligne": "SONATEL - Liberté 5",
        "description": "Minibus reliant SONATEL à Liberté 5 via Sacré-Cœur et Liberté 6.",
        "arrets": ["SONATEL", "Sacré-Cœur", "Liberté 6", "Liberté 5"],
    },
    {
        "numero_ligne": "SN-5", "nom_ligne": "SONATEL - Sacré-Cœur",
        "description": "Minibus reliant SONATEL à Sacré-Cœur, trajet direct et rapide sur la VDN.",
        "arrets": ["SONATEL", "Sacré-Cœur"],
    },
    {
        "numero_ligne": "SN-6", "nom_ligne": "SONATEL - Cité Keur Gorgui",
        "description": "Minibus reliant SONATEL à Cité Keur Gorgui via Ouest Foire, vers le pôle d'affaires "
                       "proche de la VDN.",
        "arrets": ["SONATEL", "Ouest Foire", "Cité Keur Gorgui"],
    },
    {
        "numero_ligne": "SN-7", "nom_ligne": "SONATEL - Ouest Foire",
        "description": "Minibus reliant SONATEL à Ouest Foire, quartier voisin et carrefour de correspondance "
                       "vers plusieurs autres lignes.",
        "arrets": ["SONATEL", "Ouest Foire"],
    },
    {
        "numero_ligne": "SN-8", "nom_ligne": "SONATEL - Ngor",
        "description": "Minibus reliant SONATEL à Ngor via Mermoz et Almadies, pour rejoindre la façade littorale.",
        "arrets": ["SONATEL", "Mermoz", "Almadies", "Ngor"],
    },
]


def _ajouter_reseau_sonatel(cursor):
    """Ajoute le lieu SONATEL et les lignes minibus curées SN-1 à SN-8
    s'ils n'existent pas déjà (vérification par nom / numéro de ligne),
    en réutilisant le même schéma (arrets + ligne_arrets) que
    `_enrichir_reseau_et_lexique`."""
    nom_lieu, type_lieu, lat, lng, desc = LIEU_SONATEL
    existe = cursor.execute("SELECT 1 FROM lieux WHERE nom = ?", (nom_lieu,)).fetchone()
    if not existe:
        cursor.execute(
            "INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES (?, ?, ?, ?, ?)",
            (nom_lieu, type_lieu, lat, lng, desc)
        )

    ligne_transport = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom LIKE 'Minibus Tata%'"
    ).fetchone()
    if not ligne_transport:
        return
    id_transport_tata = ligne_transport[0]

    for ligne in LIGNES_MINIBUS_SONATEL:
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

        for ordre, nom_arret in enumerate(ligne["arrets"], start=1):
            lieu_row = cursor.execute(
                "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom_arret,)
            ).fetchone()
            if not lieu_row:
                continue
            id_lieu, lat_arret, lng_arret = lieu_row
            cursor.execute(
                "INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES (?, ?, ?, ?)",
                (f"Arrêt {nom_arret} ({ligne['numero_ligne']})", id_lieu, lat_arret, lng_arret)
            )
            id_arret = cursor.lastrowid
            cursor.execute(
                "INSERT INTO ligne_arrets (id_ligne, id_arret, ordre) VALUES (?, ?, ?)",
                (id_ligne, id_arret, ordre)
            )


def _retirer_lignes_dit_fictives(cursor):
    """Retire les lignes 'DIT-1' à 'DIT-5' créées lors d'une itération
    précédente du projet : c'étaient des lignes inventées pour l'occasion,
    cloisonnées dans un onglet à part, plutôt que des lignes réellement
    exploitées par le réseau Tata. Idempotent : ne fait rien si ces lignes
    n'existent pas ou plus."""
    lignes = cursor.execute(
        "SELECT id_ligne FROM lignes_bus WHERE numero_ligne LIKE 'DIT-%'"
    ).fetchall()
    for row in lignes:
        id_ligne = row[0]
        arrets_a_supprimer = cursor.execute(
            "SELECT id_arret FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,)
        ).fetchall()
        cursor.execute("DELETE FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,))
        for arret_row in arrets_a_supprimer:
            cursor.execute("DELETE FROM arrets WHERE id_arret = ?", (arret_row[0],))
        cursor.execute("DELETE FROM lignes_bus WHERE id_ligne = ?", (id_ligne,))


# ---------------------------------------------------------------------
# Troisième vague d'enrichissement du réseau : nouveaux lieux (monuments,
# hôpitaux, marchés, stades — des repères réels de Dakar encore absents de
# la base) et nouvelles lignes Tata/Car rapide. Les numéros de ligne
# utilisés ici (17, 35, 37, 54, 59, 62, 69, 71, 73, 74, 76, 77, 79, puis
# 91+) ont été choisis pour ne JAMAIS entrer en collision avec les
# numéros déjà pris par le reste du réseau (1-90 très majoritairement
# occupés par la donnée d'origine et les deux premières vagues
# d'enrichissement) — une précédente tentative avait réutilisé des
# numéros déjà existants (Ligne 4, 42, 47, 67, 78), ce qui les faisait
# silencieusement ignorer par la vérification d'idempotence. Ces lignes ne
# reçoivent aucun traitement particulier : elles sont insérées exactement
# comme toutes les autres, qu'elles passent ou non par le secteur VDN /
# Sacré-Cœur / Cité Keur Gorgui.
# ---------------------------------------------------------------------
NOUVEAUX_LIEUX_3 = [
    ('Stade Léopold Sédar Senghor', 'site_touristique', 14.7196, -17.4780, "Principal stade national du Sénégal, proche de Fenêtre Mermoz"),
    ('Hôpital Principal de Dakar', 'site_touristique', 14.6819, -17.4342, "Grand hôpital militaire et civil du Plateau"),
    ('Hôpital Dalal Jamm', 'site_touristique', 14.7825, -17.3872, "Hôpital de référence de la banlieue nord, à Guédiawaye"),
    ('Grande Mosquée de Dakar', 'site_touristique', 14.6759, -17.4437, "Principale mosquée de la capitale, à la Médina"),
    ('CICES', 'site_touristique', 14.7420, -17.4880, "Centre International du Commerce Extérieur du Sénégal, proche de Nord Foire"),
    ("Place de l'Indépendance", 'site_touristique', 14.6690, -17.4290, "Place centrale du Plateau, cœur historique de Dakar"),
    ('Cathédrale du Souvenir Africain', 'site_touristique', 14.6717, -17.4308, "Cathédrale du Plateau"),
    ('Village Artisanal de Soumbédioune', 'site_touristique', 14.6839, -17.4611, "Marché d'art et d'artisanat en bord de Corniche"),
    ('Marché Kermel', 'site_touristique', 14.6698, -17.4285, "Marché couvert historique du Plateau"),
    ('Stade Iba Mar Diop', 'site_touristique', 14.6795, -17.4453, "Stade omnisports de la Médina"),
    ('Cimetière de Yoff', 'quartier', 14.7490, -17.4720, "Repère du quartier de Yoff, proche de la Corniche nord"),
    ('Corniche Ouest', 'quartier', 14.6850, -17.4750, "Route côtière reliant le Plateau à la pointe des Almadies"),
]

NOUVELLES_LIGNES_MINIBUS_3 = [
    {"numero_ligne": "Ligne 17", "nom_ligne": "Sandaga - Grande Mosquée de Dakar", "description": "Minibus Tata (AFTU) reliant Sandaga à la Grande Mosquée de Dakar via Médina.", "arrets": ["Sandaga", "Médina", "Grande Mosquée de Dakar"]},
    {"numero_ligne": "Ligne 35", "nom_ligne": "Ouakam - Almadies (via Route de l'Aéroport)", "description": "Minibus Tata (AFTU) reliant Ouakam à Almadies via Virage Ouakam et Mamelles.", "arrets": ["Ouakam", "Virage Ouakam", "Mamelles", "Almadies"]},
    {"numero_ligne": "Ligne 37", "nom_ligne": "Guédiawaye - Golf", "description": "Minibus Tata (AFTU) reliant Guédiawaye à Golf via Wakhinane.", "arrets": ["Guédiawaye", "Wakhinane", "Golf"]},
    {"numero_ligne": "Ligne 54", "nom_ligne": "Pikine - Thiaroye sur Mer", "description": "Minibus Tata (AFTU) reliant Pikine à Thiaroye sur Mer via Guinaw Rail.", "arrets": ["Pikine", "Guinaw Rail", "Thiaroye sur Mer"]},
    {"numero_ligne": "Ligne 59", "nom_ligne": "Wakhinane - Médina Gounass", "description": "Minibus Tata (AFTU) reliant Wakhinane à Médina Gounass, liaison locale de Guédiawaye.", "arrets": ["Wakhinane", "Médina Gounass"]},
    {"numero_ligne": "Ligne 62", "nom_ligne": "Rufisque Nord - Bargny", "description": "Minibus Tata (AFTU) reliant Rufisque Nord à Bargny.", "arrets": ["Rufisque Nord", "Bargny"]},
    {"numero_ligne": "Ligne 69", "nom_ligne": "Colobane - CICES", "description": "Minibus Tata (AFTU) reliant Colobane au CICES via Grand Dakar et Nord Foire.", "arrets": ["Colobane", "Grand Dakar", "Nord Foire", "CICES"]},
    {"numero_ligne": "Ligne 71", "nom_ligne": "Gueule Tapée - Keur Massar (via Grand Dakar)", "description": "Minibus Tata (AFTU) reliant Gueule Tapée à Keur Massar via Grand Dakar, Pikine et Diacksao.", "arrets": ["Gueule Tapée", "Grand Dakar", "Pikine", "Diacksao", "Keur Massar"]},
    {"numero_ligne": "Ligne 73", "nom_ligne": "Fann - Village Artisanal de Soumbédioune", "description": "Minibus Tata (AFTU) reliant Fann au Village Artisanal de Soumbédioune, le long de la Corniche.", "arrets": ["Fann", "Village Artisanal de Soumbédioune"]},
    {"numero_ligne": "Ligne 74", "nom_ligne": "Médina - Stade Iba Mar Diop", "description": "Minibus Tata (AFTU) reliant Médina au Stade Iba Mar Diop via Tilène.", "arrets": ["Médina", "Tilène", "Stade Iba Mar Diop"]},
    {"numero_ligne": "Ligne 76", "nom_ligne": "Liberté 6 - Sicap Baobab", "description": "Minibus Tata (AFTU) reliant Liberté 6 à Sicap Baobab.", "arrets": ["Liberté 6", "Sicap Baobab"]},
    {"numero_ligne": "Ligne 77", "nom_ligne": "Grand Yoff - Stade Léopold Sédar Senghor", "description": "Minibus Tata (AFTU) reliant Grand Yoff au Stade Léopold Sédar Senghor via Zone de Captage et Fenêtre Mermoz.", "arrets": ["Grand Yoff", "Zone de Captage", "Fenêtre Mermoz", "Stade Léopold Sédar Senghor"]},
    {"numero_ligne": "Ligne 79", "nom_ligne": "Cambérène - Cimetière de Yoff", "description": "Minibus Tata (AFTU) reliant Cambérène au secteur du Cimetière de Yoff.", "arrets": ["Cambérène", "Cimetière de Yoff"]},
    {"numero_ligne": "Ligne 91", "nom_ligne": "Plateau - Hôpital Principal de Dakar", "description": "Minibus Tata (AFTU) reliant le Plateau à l'Hôpital Principal de Dakar.", "arrets": ["Plateau", "Hôpital Principal de Dakar"]},
    {"numero_ligne": "Ligne 92", "nom_ligne": "Petersen - Place de l'Indépendance", "description": "Minibus Tata (AFTU) reliant Petersen à la Place de l'Indépendance via le Plateau.", "arrets": ["Petersen", "Plateau", "Place de l'Indépendance"]},
    {"numero_ligne": "Ligne 93", "nom_ligne": "Yoff - Cimetière de Yoff", "description": "Minibus Tata (AFTU), courte liaison locale du village de Yoff.", "arrets": ["Yoff", "Cimetière de Yoff"]},
    {"numero_ligne": "Ligne 94", "nom_ligne": "Ouest Foire - CICES", "description": "Minibus Tata (AFTU) reliant Ouest Foire au CICES via Nord Foire.", "arrets": ["Ouest Foire", "Nord Foire", "CICES"]},
    {"numero_ligne": "Ligne 95", "nom_ligne": "Sacré-Cœur - Stade Léopold Sédar Senghor", "description": "Minibus Tata (AFTU) reliant Sacré-Cœur au Stade Léopold Sédar Senghor via Fenêtre Mermoz.", "arrets": ["Sacré-Cœur", "Fenêtre Mermoz", "Stade Léopold Sédar Senghor"]},
    {"numero_ligne": "Ligne 96", "nom_ligne": "Rufisque - Sébikotane", "description": "Minibus Tata (AFTU) reliant Rufisque à Sébikotane via Rufisque Est et Bargny.", "arrets": ["Rufisque", "Rufisque Est", "Bargny", "Sébikotane"]},
    {"numero_ligne": "Ligne 97", "nom_ligne": "Bargny - Diamniadio", "description": "Minibus Tata (AFTU) reliant Bargny à Diamniadio.", "arrets": ["Bargny", "Diamniadio"]},
    {"numero_ligne": "Ligne 98", "nom_ligne": "Yenne - Bargny", "description": "Minibus Tata (AFTU) reliant Yenne à Bargny.", "arrets": ["Yenne", "Bargny"]},
    {"numero_ligne": "Ligne 99", "nom_ligne": "Diamniadio - Sangalkam", "description": "Minibus Tata (AFTU) reliant Diamniadio à Sangalkam.", "arrets": ["Diamniadio", "Sangalkam"]},
    {"numero_ligne": "Ligne 100", "nom_ligne": "Guédiawaye - Hôpital Dalal Jamm", "description": "Minibus Tata (AFTU) reliant Guédiawaye à l'Hôpital Dalal Jamm via Wakhinane.", "arrets": ["Guédiawaye", "Wakhinane", "Hôpital Dalal Jamm"]},
    {"numero_ligne": "Ligne 101", "nom_ligne": "Ngor - Village Artisanal de Soumbédioune", "description": "Minibus Tata (AFTU) reliant Ngor au Village Artisanal de Soumbédioune via la Corniche Ouest et Fann.", "arrets": ["Ngor", "Corniche Ouest", "Fann", "Village Artisanal de Soumbédioune"]},
    {"numero_ligne": "Ligne 102", "nom_ligne": "Colobane - Grande Mosquée de Dakar", "description": "Minibus Tata (AFTU) reliant Colobane à la Grande Mosquée de Dakar via Médina.", "arrets": ["Colobane", "Médina", "Grande Mosquée de Dakar"]},
]

NOUVELLES_LIGNES_CAR_RAPIDE_2 = [
    {"numero_ligne": "CR-21", "nom_ligne": "Plateau - Marché Kermel (Car rapide)", "description": "Car rapide reliant le Plateau au Marché Kermel.", "arrets": ["Plateau", "Marché Kermel"]},
    {"numero_ligne": "CR-22", "nom_ligne": "Médina - Grande Mosquée de Dakar (Car rapide)", "description": "Car rapide reliant Médina à la Grande Mosquée de Dakar.", "arrets": ["Médina", "Grande Mosquée de Dakar"]},
    {"numero_ligne": "CR-23", "nom_ligne": "Sandaga - CICES (Car rapide)", "description": "Car rapide reliant Sandaga au CICES via Grand Dakar et Nord Foire.", "arrets": ["Sandaga", "Grand Dakar", "Nord Foire", "CICES"]},
    {"numero_ligne": "CR-24", "nom_ligne": "Rufisque - Sébikotane (Car rapide)", "description": "Car rapide reliant Rufisque à Sébikotane via Bargny et Diamniadio.", "arrets": ["Rufisque", "Bargny", "Diamniadio", "Sébikotane"]},
    {"numero_ligne": "CR-25", "nom_ligne": "Guédiawaye - Hôpital Dalal Jamm (Car rapide)", "description": "Car rapide reliant Guédiawaye à l'Hôpital Dalal Jamm.", "arrets": ["Guédiawaye", "Hôpital Dalal Jamm"]},
]


def _enrichir_reseau_vague_3(cursor):
    """Troisième vague d'enrichissement du réseau (lieux + lignes Tata et
    Car rapide), avec les mêmes garanties d'idempotence que
    `_enrichir_reseau_et_lexique` (vérification par nom / numéro de ligne
    avant chaque insertion)."""
    for nom, type_lieu, lat, lng, desc in NOUVEAUX_LIEUX_3:
        existe = cursor.execute("SELECT 1 FROM lieux WHERE nom = ?", (nom,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES (?, ?, ?, ?, ?)",
                (nom, type_lieu, lat, lng, desc)
            )

    ligne_transport = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom LIKE 'Minibus Tata%'"
    ).fetchone()
    ligne_transport_cr = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom = 'Car rapide'"
    ).fetchone()
    if not ligne_transport:
        return
    id_transport_tata = ligne_transport[0]
    id_transport_car_rapide = ligne_transport_cr[0] if ligne_transport_cr else None

    lots = [(NOUVELLES_LIGNES_MINIBUS_3, id_transport_tata)]
    if id_transport_car_rapide:
        lots.append((NOUVELLES_LIGNES_CAR_RAPIDE_2, id_transport_car_rapide))

    for lignes, id_transport_lot in lots:
        for ligne in lignes:
            existe = cursor.execute(
                "SELECT 1 FROM lignes_bus WHERE numero_ligne = ?", (ligne["numero_ligne"],)
            ).fetchone()
            if existe:
                continue

            cursor.execute(
                "INSERT INTO lignes_bus (numero_ligne, nom_ligne, id_transport, est_minibus, description) "
                "VALUES (?, ?, ?, 1, ?)",
                (ligne["numero_ligne"], ligne["nom_ligne"], id_transport_lot, ligne["description"])
            )
            id_ligne = cursor.lastrowid

            for ordre, nom_arret in enumerate(ligne["arrets"], start=1):
                lieu_row = cursor.execute(
                    "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom_arret,)
                ).fetchone()
                if not lieu_row:
                    continue
                id_lieu, lat_arret, lng_arret = lieu_row
                cursor.execute(
                    "INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES (?, ?, ?, ?)",
                    (f"Arrêt {nom_arret} ({ligne['numero_ligne']})", id_lieu, lat_arret, lng_arret)
                )
                id_arret = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO ligne_arrets (id_ligne, id_arret, ordre) VALUES (?, ?, ?)",
                    (id_ligne, id_arret, ordre)
                )


# ---------------------------------------------------------------------
# Quatrième vague d'enrichissement, focalisée sur le réseau Tata (AFTU)
# spécifiquement : nouveaux lieux (campus, terminus, marchés de quartier)
# et 28 nouvelles lignes Tata supplémentaires, avec la même règle de
# numérotation que la vague 3 (numéros jamais réutilisés : 103 à 130).
# ---------------------------------------------------------------------
NOUVEAUX_LIEUX_4 = [
    ('Technopole', 'entreprise', 14.7280, -17.4550, "Zone d'activités technologiques et tertiaires proche de la VDN"),
    ('Parc Zoologique de Hann', 'site_touristique', 14.7255, -17.4285, "Parc zoologique et forestier de Hann"),
    ('Ouagou Niayes', 'quartier', 14.7600, -17.4150, "Quartier à la frontière de Pikine et Guédiawaye"),
    ('Terminus Yoff', 'quartier', 14.7440, -17.4690, "Terminus des lignes desservant Yoff"),
    ('École Supérieure Polytechnique', 'universite', 14.6930, -17.4620, "École d'ingénieurs du campus de l'UCAD"),
    ('Marché Syndicat', 'quartier', 14.7710, -17.4020, "Grand marché de quartier à Guédiawaye"),
    ('Terminus Rufisque', 'quartier', 14.7170, -17.2670, "Terminus des lignes desservant Rufisque"),
    ('Ngor Plage', 'site_touristique', 14.7520, -17.5160, "Plage du village de Ngor, face à l'île de Ngor"),
]

NOUVELLES_LIGNES_MINIBUS_4 = [
    {"numero_ligne": "Ligne 103", "nom_ligne": "Petersen - Technopole (via Cité Keur Gorgui)", "description": "Minibus Tata (AFTU) reliant Petersen à Technopole via Sacré-Cœur et Cité Keur Gorgui.", "arrets": ["Petersen", "Sacré-Cœur", "Cité Keur Gorgui", "Technopole"]},
    {"numero_ligne": "Ligne 104", "nom_ligne": "Sandaga - Parc Zoologique de Hann", "description": "Minibus Tata (AFTU) reliant Sandaga au Parc Zoologique de Hann via Colobane et Hann.", "arrets": ["Sandaga", "Colobane", "Hann", "Parc Zoologique de Hann"]},
    {"numero_ligne": "Ligne 105", "nom_ligne": "Pikine - Ouagou Niayes", "description": "Minibus Tata (AFTU) reliant Pikine à Ouagou Niayes via Guinaw Rail.", "arrets": ["Pikine", "Guinaw Rail", "Ouagou Niayes"]},
    {"numero_ligne": "Ligne 106", "nom_ligne": "Yoff - Terminus Yoff", "description": "Minibus Tata (AFTU), liaison locale du village de Yoff.", "arrets": ["Yoff", "Terminus Yoff"]},
    {"numero_ligne": "Ligne 107", "nom_ligne": "UCAD - École Supérieure Polytechnique", "description": "Minibus Tata (AFTU), navette du campus universitaire.", "arrets": ["UCAD", "École Supérieure Polytechnique"]},
    {"numero_ligne": "Ligne 108", "nom_ligne": "Guédiawaye - Marché Syndicat", "description": "Minibus Tata (AFTU) reliant Guédiawaye au Marché Syndicat.", "arrets": ["Guédiawaye", "Marché Syndicat"]},
    {"numero_ligne": "Ligne 109", "nom_ligne": "Rufisque - Terminus Rufisque", "description": "Minibus Tata (AFTU), liaison locale de Rufisque.", "arrets": ["Rufisque", "Terminus Rufisque"]},
    {"numero_ligne": "Ligne 110", "nom_ligne": "Ngor - Ngor Plage", "description": "Minibus Tata (AFTU), courte liaison vers la plage de Ngor.", "arrets": ["Ngor", "Ngor Plage"]},
    {"numero_ligne": "Ligne 111", "nom_ligne": "Médina - Fann (direct)", "description": "Minibus Tata (AFTU) reliant Médina à Fann via Fass.", "arrets": ["Médina", "Fass", "Fann"]},
    {"numero_ligne": "Ligne 112", "nom_ligne": "Colobane - Point E", "description": "Minibus Tata (AFTU) reliant Colobane à Point E via Fass.", "arrets": ["Colobane", "Fass", "Point E"]},
    {"numero_ligne": "Ligne 113", "nom_ligne": "HLM - Grand Médine", "description": "Minibus Tata (AFTU) reliant HLM à Grand Médine via Front de Terre.", "arrets": ["HLM", "Front de Terre", "Grand Médine"]},
    {"numero_ligne": "Ligne 114", "nom_ligne": "Sicap Baobab - Zone de Captage", "description": "Minibus Tata (AFTU) reliant Sicap Baobab à Zone de Captage.", "arrets": ["Sicap Baobab", "Zone de Captage"]},
    {"numero_ligne": "Ligne 115", "nom_ligne": "Liberté 1 - Amitié", "description": "Minibus Tata (AFTU) reliant Liberté 1 à Amitié.", "arrets": ["Liberté 1", "Amitié"]},
    {"numero_ligne": "Ligne 116", "nom_ligne": "Dieuppeul - Derklé", "description": "Minibus Tata (AFTU) reliant Dieuppeul à Derklé.", "arrets": ["Dieuppeul", "Derklé"]},
    {"numero_ligne": "Ligne 117", "nom_ligne": "Grand Dakar - Castors", "description": "Minibus Tata (AFTU) reliant Grand Dakar à Castors.", "arrets": ["Grand Dakar", "Castors"]},
    {"numero_ligne": "Ligne 118", "nom_ligne": "Parcelles Assainies - Cambérène (direct)", "description": "Minibus Tata (AFTU) reliant Parcelles Assainies à Cambérène via Grand Médine.", "arrets": ["Parcelles Assainies", "Grand Médine", "Cambérène"]},
    {"numero_ligne": "Ligne 119", "nom_ligne": "Golf - Wakhinane", "description": "Minibus Tata (AFTU) reliant Golf à Wakhinane.", "arrets": ["Golf", "Wakhinane"]},
    {"numero_ligne": "Ligne 120", "nom_ligne": "Thiaroye - Djidah Thiaroye Kao", "description": "Minibus Tata (AFTU) reliant Thiaroye à Djidah Thiaroye Kao.", "arrets": ["Thiaroye", "Djidah Thiaroye Kao"]},
    {"numero_ligne": "Ligne 121", "nom_ligne": "Yeumbeul - Malika", "description": "Minibus Tata (AFTU) reliant Yeumbeul à Malika.", "arrets": ["Yeumbeul", "Malika"]},
    {"numero_ligne": "Ligne 122", "nom_ligne": "Keur Massar - Diacksao", "description": "Minibus Tata (AFTU) reliant Keur Massar à Diacksao.", "arrets": ["Keur Massar", "Diacksao"]},
    {"numero_ligne": "Ligne 123", "nom_ligne": "Rufisque Est - Diokoul", "description": "Minibus Tata (AFTU) reliant Rufisque Est à Diokoul.", "arrets": ["Rufisque Est", "Diokoul"]},
    {"numero_ligne": "Ligne 124", "nom_ligne": "Arafat - Rufisque Nord", "description": "Minibus Tata (AFTU) reliant Arafat à Rufisque Nord.", "arrets": ["Arafat", "Rufisque Nord"]},
    {"numero_ligne": "Ligne 125", "nom_ligne": "Bargny - Sangalkam", "description": "Minibus Tata (AFTU) reliant Bargny à Sangalkam.", "arrets": ["Bargny", "Sangalkam"]},
    {"numero_ligne": "Ligne 126", "nom_ligne": "Sébikotane - Bambilor", "description": "Minibus Tata (AFTU) reliant Sébikotane à Bambilor.", "arrets": ["Sébikotane", "Bambilor"]},
    {"numero_ligne": "Ligne 127", "nom_ligne": "Almadies - Corniche Ouest", "description": "Minibus Tata (AFTU) reliant Almadies à la Corniche Ouest.", "arrets": ["Almadies", "Corniche Ouest"]},
    {"numero_ligne": "Ligne 128", "nom_ligne": "Mermoz - Fenêtre Mermoz", "description": "Minibus Tata (AFTU), liaison locale du secteur Mermoz.", "arrets": ["Mermoz", "Fenêtre Mermoz"]},
    {"numero_ligne": "Ligne 129", "nom_ligne": "Point E - Amitié", "description": "Minibus Tata (AFTU) reliant Point E à Amitié.", "arrets": ["Point E", "Amitié"]},
    {"numero_ligne": "Ligne 130", "nom_ligne": "Sacré-Cœur 3 - Liberté 6 Extension", "description": "Minibus Tata (AFTU) reliant Sacré-Cœur 3 à Liberté 6 Extension.", "arrets": ["Sacré-Cœur 3", "Liberté 6 Extension"]},
]


def _enrichir_reseau_vague_4(cursor):
    """Quatrième vague d'enrichissement, centrée sur le réseau Tata : mêmes
    garanties d'idempotence que les vagues précédentes (vérification par
    nom / numéro de ligne avant chaque insertion)."""
    for nom, type_lieu, lat, lng, desc in NOUVEAUX_LIEUX_4:
        existe = cursor.execute("SELECT 1 FROM lieux WHERE nom = ?", (nom,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES (?, ?, ?, ?, ?)",
                (nom, type_lieu, lat, lng, desc)
            )

    ligne_transport = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom LIKE 'Minibus Tata%'"
    ).fetchone()
    if not ligne_transport:
        return
    id_transport_tata = ligne_transport[0]

    for ligne in NOUVELLES_LIGNES_MINIBUS_4:
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

        for ordre, nom_arret in enumerate(ligne["arrets"], start=1):
            lieu_row = cursor.execute(
                "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom_arret,)
            ).fetchone()
            if not lieu_row:
                continue
            id_lieu, lat_arret, lng_arret = lieu_row
            cursor.execute(
                "INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES (?, ?, ?, ?)",
                (f"Arrêt {nom_arret} ({ligne['numero_ligne']})", id_lieu, lat_arret, lng_arret)
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

def get_lignes_sonatel():
    """Retourne uniquement les lignes minibus curées au départ du pôle
    SONATEL (numéros SN-1 à SN-8). Conservé pour compatibilité ; la page
    /minibus utilise désormais get_toutes_les_lignes_tata()."""
    conn = get_connection()
    lignes = conn.execute(
        "SELECT * FROM lignes_bus WHERE numero_ligne LIKE 'SN-%' ORDER BY numero_ligne"
    ).fetchall()
    conn.close()
    return lignes


def get_toutes_les_lignes_tata():
    """Retourne l'intégralité des lignes du réseau Minibus Tata (AFTU) —
    utilisée par la page /minibus, qui référence désormais tout le réseau
    et non plus seulement les itinéraires curés SONATEL. Le Car rapide,
    bien que marqué est_minibus=1 en base pour le calcul d'itinéraires,
    est un moyen de transport distinct et n'est pas inclus ici."""
    conn = get_connection()
    lignes = conn.execute("""
        SELECT lb.* FROM lignes_bus lb
        JOIN moyens_transport mt ON mt.id_transport = lb.id_transport
        WHERE mt.nom LIKE 'Minibus Tata%'
        ORDER BY lb.numero_ligne
    """).fetchall()
    conn.close()
    return lignes


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

def ajouter_recherche_historique(dep_nom, arr_nom, dep_lat=None, dep_lng=None, arr_lat=None, arr_lng=None,
                                  id_lieu_depart=None, id_lieu_arrivee=None):
    """Enregistre une recherche effectuée par l'utilisateur."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO historique_recherches
            (adresse_depart, adresse_arrivee, lat_depart, lng_depart, lat_arrivee, lng_arrivee,
             id_lieu_depart, id_lieu_arrivee)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (dep_nom, arr_nom, dep_lat, dep_lng, arr_lat, arr_lng, id_lieu_depart, id_lieu_arrivee))
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


def vider_historique():
    """Supprime la totalité de l'historique de recherches de l'utilisateur."""
    conn = get_connection()
    conn.execute("DELETE FROM historique_recherches")
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
        if o["nom_transport"] not in ("Taxi", "Clando", "Jakarta (moto-taxi)", "À pied"):
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
        lieu_arrivee["latitude"], lieu_arrivee["longitude"],
        id_lieu_depart=id_depart, id_lieu_arrivee=id_arrivee
    )

    reponse = _construire_reponse(conn, lieu_depart, lieu_arrivee)
    conn.close()

    return {"trouve": True, "trajet": reponse["trajet"], "options": reponse["options"]}