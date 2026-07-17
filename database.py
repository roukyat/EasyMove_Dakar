"""
database.py
------------
Module Python chargé de tout ce qui concerne la base de données SQL (SQLite)
du projet EasyMoveDakar : création, connexion, et fonctions de recherche
utilisées par app.py.
"""

import re
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

    # Le Tata ne circule pas de façon fiable "tard le soir" (service qui se
    # raréfie fortement en fin de journée) : la disponibilité affichée est
    # recentrée sur le matin, plutôt que de laisser croire à un service
    # tardif équivalent au matin. Idempotent, même logique que les tarifs.
    _corriger_disponibilite_tata(cursor)

    # Alignement des avantages/inconvénients (3 + 3, par axe prix / couverture
    # / confort) pour les 9 moyens de transport, y compris Ndiaga Ndiaye :
    # idempotent (UPDATE conditionné au contenu actuel), sûr à rejouer sur
    # une base déjà à jour.
    _aligner_avantages_inconvenients_transports(cursor)

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

    # Ajout de l'Université Amadou Mahtar Mbow (UAM), pôle universitaire de
    # Diamniadio distinct de l'UCAD, pour permettre des trajets réels comme
    # "Colobane -> Université Amadou Mahtar Mbow" (page /prix). Idempotent
    # (vérification par nom), même logique que les autres enrichissements
    # de lieux ci-dessus.
    _ajouter_universite_amadou_mahtar_mbow(cursor)

    # Remplacement des lignes Tata par les 70 lignes réelles officielles de
    # l'AFTU (opérateur officiel du réseau, source aftu-senegal.org, relevé
    # 2026-07-17), à la demande explicite de l'utilisateur ("les vraies
    # lignes officielles, terminus réels seulement"). Pour chaque numéro de
    # ligne officiel qui entre en collision avec une ligne fictive existante
    # (ce qui concerne la quasi-totalité des 70 lignes), l'ancien tracé
    # inventé est retiré et remplacé par les deux vrais terminus publiés par
    # l'AFTU — voir _remplacer_par_lignes_aftu_reelles_2026 pour le détail
    # et les niveaux de confiance des coordonnées. Idempotent (marqueur de
    # description dédié empêchant toute ré-exécution destructive).
    _remplacer_par_lignes_aftu_reelles_2026(cursor)

    # Retrait des ~60 lignes Tata restées fictives (numéros 6-23, 39, 47,
    # 90, 92-130 : la partie du réseau imaginé lors d'itérations
    # précédentes qui ne correspond à AUCUN numéro publié par l'AFTU,
    # contrairement aux 70 lignes ci-dessus). Décision explicite de
    # l'utilisateur après qu'on lui a montré que /minibus affichait ces
    # lignes inventées à côté des vraies sans distinction possible : plutôt
    # que de les garder ou de les flaguer, il a choisi de les retirer pour
    # que le réseau affiché soit intégralement réel. Idempotent (ne fait
    # rien si ces lignes ont déjà été retirées).
    _retirer_lignes_tata_non_officielles_2026(cursor)

    # Enrichissement des lignes BRT (B1/B2) avec les vraies stations
    # SunuBRT (CETUD + presse + OSM network=SunuBRT), à la demande de
    # l'utilisateur après avoir remarqué l'absence du BRT comme option pour
    # un trajet Sacré-Cœur -> Liberté 6 — la station Liberté 6 (réelle)
    # manquait du tracé. Voir _enrichir_lignes_brt_2026 pour le détail des
    # sources et des niveaux de confiance. Idempotent (marqueur dédié).
    _enrichir_lignes_brt_2026(cursor)

    # Nettoyage (audit du 2026-07-17) : `trajets` et `trajet_options`
    # n'ont jamais été alimentées depuis que le moteur d'itinéraire calcule
    # tout à la volée (voir itineraire.py) — retirées de schema.sql, et
    # supprimées ici sur les bases déjà créées. Idempotent (vérifie
    # l'existence avant de DROP).
    _supprimer_tables_mortes(cursor)

    # Retrait de toute mention de l'opérateur AFTU et de la clause "seuls
    # les deux terminus sont cartographiés..." dans les descriptions des
    # lignes Tata (page /minibus), et renommage de 'Minibus Tata (AFTU)'
    # en 'Minibus Tata' : l'utilisateur ne veut voir apparaître ni la
    # source des données ni le nom de l'opérateur aux visiteurs du site,
    # juste les deux terminus. Idempotent (chaque étape est un no-op sur
    # les lignes déjà nettoyées).
    _retirer_source_description_tata_2026(cursor)

    # Corrections du lexique wolof (page /wolof) fournies par l'utilisateur,
    # locuteur natif : remplace plusieurs formulations approximatives par
    # les vraies expressions employées à Dakar, corrige un contresens
    # ("Kañ nga dem ?" pris pour un futur) et ajoute les tournures
    # manquantes (tutoiement/vouvoiement, urgence...). Idempotent (voir
    # _corriger_lexique_wolof_reel_2026).
    _corriger_lexique_wolof_reel_2026(cursor)

    # Vraies lignes urbaines et banlieue de Dakar Dem Dikk (demdikk.sn),
    # à la demande de l'utilisateur, pour que DDD apparaisse dans les
    # suggestions de recherche d'itinéraire au même titre que Tata/Car
    # rapide/BRT. Idempotent (voir _ajouter_lignes_dem_dikk_reelles_2026).
    _ajouter_lignes_dem_dikk_reelles_2026(cursor)

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


def _supprimer_tables_mortes(cursor):
    """Supprime les tables `trajets` et `trajet_options` : elles n'ont
    jamais été alimentées depuis que le moteur d'itinéraire (itineraire.py)
    calcule tout à la volée plutôt que de lire des trajets pré-calculés en
    base. Retirées de schema.sql pour les nouvelles installations ; cette
    fonction les retire aussi des bases déjà créées avant ce nettoyage.
    Idempotent : vérifie l'existence de chaque table avant de la DROP."""
    for nom_table in ("trajet_options", "trajets"):
        existe = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nom_table,)
        ).fetchone()
        if existe:
            cursor.execute(f"DROP TABLE {nom_table}")


def _retirer_source_description_tata_2026(cursor):
    """Retire de toute description déjà en base les formulations qui
    indiquent explicitement d'où vient l'information sur le réseau Tata
    (site aftu-senegal.org, mention "officiel"/"publié par l'AFTU",
    "l'AFTU ne publiant pas le détail des arrêts..."...), retire la phrase
    "Seuls les deux terminus sont cartographiés..." dans son intégralité
    (l'utilisateur ne veut plus voir cette précision du tout, pas
    seulement la partie qui cite l'AFTU comme source), et retire la
    mention "(AFTU)" partout où elle accolait le nom de l'opérateur à
    "Minibus Tata" ou "Tata" (nom de ligne affiché : "Minibus Tata"
    seul). Renomme aussi la ligne 'Minibus Tata (AFTU)' de
    `moyens_transport` en 'Minibus Tata'.

    Basé sur des regex (pas des REPLACE de chaîne exacte) pour rester
    robuste aux variantes d'apostrophe (' vs ’) et d'espacement qui
    peuvent exister selon la version du texte déjà stockée en base.
    Idempotent : ne modifie une ligne que si son contenu change
    réellement."""
    motif_prefixe_source = re.compile(
        r"Ligne officielle r[ée]elle de l['’]AFTU\s*\(source[^)]*\)\s*;?\s*",
        re.IGNORECASE,
    )
    motif_clause_source_longue = re.compile(
        r"\.?\s*Seuls? les deux terminus sont cartographi[ée]s,?\s*"
        r"l['’]AFTU ne publiant pas le d[ée]tail des arr[êe]ts "
        r"interm[ée]diaires pour cette ligne\.?",
        re.IGNORECASE,
    )
    motif_clause_terminus_courte = re.compile(
        r"\.?\s*Seuls? les deux terminus sont cartographi[ée]s pour cette "
        r"ligne\.?",
        re.IGNORECASE,
    )
    motif_aftu_parenthese = re.compile(r"\s*\(AFTU\)", re.IGNORECASE)
    motif_tata_slash_aftu = re.compile(r"Tata/AFTU", re.IGNORECASE)

    cursor.execute(
        "UPDATE moyens_transport SET nom = 'Minibus Tata' WHERE nom = 'Minibus Tata (AFTU)'"
    )

    for table, colonne in (("lignes_bus", "description"), ("lieux", "description"),
                            ("moyens_transport", "description")):
        lignes = cursor.execute(
            f"SELECT rowid, {colonne} FROM {table} WHERE {colonne} LIKE '%AFTU%'"
        ).fetchall()
        for rowid, texte in lignes:
            if not texte:
                continue
            nouveau = motif_prefixe_source.sub("", texte)
            nouveau = motif_clause_source_longue.sub("", nouveau)
            nouveau = motif_clause_terminus_courte.sub("", nouveau)
            nouveau = motif_aftu_parenthese.sub("", nouveau)
            nouveau = motif_tata_slash_aftu.sub("Tata", nouveau)
            nouveau = nouveau.replace(MARQUEUR_LIGNE_AFTU_REELLE_2026, "")
            nouveau = re.sub(r"\s{2,}", " ", nouveau).strip()
            if nouveau != texte:
                cursor.execute(
                    f"UPDATE {table} SET {colonne} = ? WHERE rowid = ?",
                    (nouveau, rowid),
                )


# ---------------------------------------------------------------------
# ENRICHISSEMENT DAKAR DEM DIKK (2026-07-17) — à la demande de l'utilisateur
# ("la base de données du site officiel de Dem Dikk... pour que lorsqu'on
# fait des recherches on ait aussi Dem Dikk dans les suggestions"). Source :
# demdikk.sn/reseau-urbain-dakar/ (lignes urbaines et banlieue), relevé
# 2026-07-17.
#
# Dakar Dem Dikk (DDD) avait 7 lignes fictives dans la donnée d'origine
# (numéros bruts "Ligne 7/9/14/18/22/25/28", inventées comme le reste du
# réseau à l'époque). Trois d'entre elles (7, 9, 18) correspondent à un
# vrai numéro DDD mais avec un tracé complètement différent de la ligne
# réelle publiée — remplacées ci-dessous. Les quatre autres (14, 22, 25,
# 28) n'ont aucun équivalent dans la numérotation officielle DDD trouvée
# sur le site — retirées, même logique que pour les ~60 lignes Tata non
# officielles (l'utilisateur veut un réseau affiché intégralement réel).
#
# Comme pour les lignes AFTU, seuls les deux terminus publiés sont
# modélisés (pas de tracé intermédiaire inventé) : le site liste souvent
# les arrêts intermédiaires, mais ceux-ci sont des points de rue trop fins
# (« Rond point JVC », « Marché HLM »...) pour être ajoutés comme lieux
# fiables sans coordonnées propres.
#
# Numérotation stockée avec le préfixe "DDD " (ex. "DDD 7") plutôt que le
# numéro brut ("Ligne 7") : la numérotation officielle DDD (1, 2, 4, 5...)
# chevauche largement celle, purement inventée, du réseau Minibus Tata
# (qui utilise aussi "Ligne 1", "Ligne 2"...) — sans préfixe distinct, une
# ligne DDD et une ligne Tata pourraient partager le même `numero_ligne`
# et se confondre dans toute requête qui ne filtre pas aussi par
# `id_transport` (déjà le cas de `_remplacer_par_lignes_aftu_reelles_2026`
# pour Tata, mais ce risque ne s'est jamais matérialisé côté Tata car son
# numérotage n'a jamais recoupé celui de DDD jusqu'ici).
# ---------------------------------------------------------------------
NOUVEAUX_LIEUX_DEM_DIKK_2026 = [
    ('Place Leclerc', 'site_touristique', 14.6935, -17.4245, "Rond-point et terminus historique du Plateau, près de l'Embarcadère de Gorée"),
    ('Palais 1', 'site_touristique', 14.6699, -17.4257, "Terminus DDD proche du Palais présidentiel, côté Avenue Léopold Sédar Senghor"),
    ('Palais 2', 'site_touristique', 14.6705, -17.4247, "Second terminus DDD proche du Palais présidentiel, côté Avenue Nelson Mandela"),
    ('Lat Dior', 'site_touristique', 14.6745, -17.4330, "Avenue Lat Dior, artère commerçante du Plateau proche de Sandaga"),
    ('Daroukhane', 'quartier', 14.7870, -17.4020, "Quartier de Guédiawaye, en bord de corniche"),
    ('Bayakh', 'ville', 14.85, -17.05, "Commune rurale au nord de Rufisque, sur l'axe vers Kayar"),
    ('Baux Maraîchers', 'quartier', 14.7150, -17.4430, "Zone maraîchère proche de Hann et Cambérène"),
    ('Jaxaay', 'quartier', 14.7750, -17.3350, "Cité de recasement proche de Keur Massar"),
    ('Gadaye', 'quartier', 14.7900, -17.3600, "Quartier proche de Malika, aussi appelé Gadaye-Filaos"),
    ('Aéroport LSS', 'aeroport', 14.7397, -17.4902, "Ancien aéroport international Léopold Sédar Senghor, à Yoff"),
]

# (numéro officiel DDD, terminus A, terminus B) — numéro tel que publié sur
# demdikk.sn, sans le préfixe "DDD " (ajouté au moment de l'insertion).
LIGNES_DEM_DIKK_OFFICIELLES_2026 = [
    ("1", "Parcelles Assainies", "Place Leclerc"),
    ("2", "Daroukhane", "Place Leclerc"),
    ("4", "Liberté 5", "Place Leclerc"),
    ("5", "Guédiawaye", "Palais 1"),
    ("6", "Guédiawaye", "Palais 1"),
    ("7", "Ouakam", "Palais 2"),
    ("8", "Aéroport LSS", "Palais 2"),
    ("9", "Liberté 6", "Palais 2"),
    ("10", "Liberté 5", "Palais 2"),
    ("11", "Keur Massar", "Lat Dior"),
    ("12", "Guédiawaye", "Palais 1"),
    ("13", "Liberté 5", "Palais 2"),
    ("15", "Rufisque", "Palais 1"),
    ("16A", "Malika", "Palais 1"),
    ("16B", "Malika", "Palais 1"),
    ("18", "Dieuppeul", "Plateau"),
    ("208", "Bayakh", "Rufisque"),
    ("213", "Rufisque", "Dieuppeul"),
    ("217", "Thiaroye", "Ouakam"),
    ("218", "Thiaroye", "Aéroport LSS"),
    ("219", "Daroukhane", "Ouakam"),
    ("220", "Rufisque", "Guédiawaye"),
    ("221", "Gadaye", "Almadies"),
    ("227", "Keur Massar", "Parcelles Assainies"),
    ("228", "Rufisque", "Yenne"),
    ("232", "Baux Maraîchers", "Aéroport LSS"),
    ("233", "Baux Maraîchers", "Palais 1"),
    ("234", "Jaxaay", "Place Leclerc"),
    ("311", "Lac Rose (Retba)", "Keur Massar"),
    ("319", "Liberté 6", "Ouakam"),
    ("327", "Keur Massar", "Parcelles Assainies"),
    ("501", "Palais 2", "Place Leclerc"),
]

# Anciennes lignes DDD fictives sans aucun équivalent dans la numérotation
# officielle relevée sur demdikk.sn : retirées (numéro brut, sans préfixe,
# tel qu'inséré à l'origine par donnees.sql).
NUMEROS_LIGNES_DDD_FICTIVES_SANS_EQUIVALENT_2026 = ['Ligne 14', 'Ligne 22', 'Ligne 25', 'Ligne 28']

# Anciennes lignes DDD fictives dont le numéro correspond à une vraie ligne
# DDD mais avec un tracé différent : retirées puis recréées ci-dessous sous
# leur numéro préfixé ("DDD 7", "DDD 9", "DDD 18") avec le vrai tracé.
NUMEROS_LIGNES_DDD_FICTIVES_A_REMPLACER_2026 = ['Ligne 7', 'Ligne 9', 'Ligne 18']


def _supprimer_ligne_dem_dikk_2026(cursor, numero_ligne, id_transport_ddd):
    """Retire une ligne DDD (et ses arrêts devenus orphelins) en ne
    cherchant que parmi les lignes de DDD (`id_transport` filtré) : le
    même texte de `numero_ligne` ("Ligne 7"...) peut exister pour un autre
    opérateur (Minibus Tata), qu'il ne faut surtout pas toucher. No-op si
    la ligne n'existe pas ou plus (idempotent)."""
    ligne = cursor.execute(
        "SELECT id_ligne FROM lignes_bus WHERE numero_ligne = ? AND id_transport = ?",
        (numero_ligne, id_transport_ddd)
    ).fetchone()
    if not ligne:
        return
    id_ligne = ligne[0]
    arrets_a_supprimer = cursor.execute(
        "SELECT id_arret FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,)
    ).fetchall()
    cursor.execute("DELETE FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,))
    for arret_row in arrets_a_supprimer:
        id_arret_candidat = arret_row[0]
        encore_reference = cursor.execute(
            "SELECT 1 FROM ligne_arrets WHERE id_arret = ?", (id_arret_candidat,)
        ).fetchone()
        if not encore_reference:
            cursor.execute("DELETE FROM arrets WHERE id_arret = ?", (id_arret_candidat,))
    cursor.execute("DELETE FROM lignes_bus WHERE id_ligne = ?", (id_ligne,))


def _ajouter_lignes_dem_dikk_reelles_2026(cursor):
    """Ajoute les vraies lignes urbaines et banlieue de Dakar Dem Dikk
    (voir LIGNES_DEM_DIKK_OFFICIELLES_2026), après avoir retiré les
    quelques lignes DDD fictives de la donnée d'origine (voir les deux
    listes NUMEROS_LIGNES_DDD_FICTIVES_* ci-dessus). Idempotent : chaque
    ligne réelle n'est insérée que si son `numero_ligne` préfixé
    ("DDD 7"...) n'existe pas déjà pour DDD ; les suppressions de lignes
    fictives sont elles-mêmes des no-op une fois faites une première
    fois."""
    for nom, type_lieu, lat, lng, desc in NOUVEAUX_LIEUX_DEM_DIKK_2026:
        existe = cursor.execute("SELECT 1 FROM lieux WHERE nom = ?", (nom,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES (?, ?, ?, ?, ?)",
                (nom, type_lieu, lat, lng, desc)
            )

    transport_row = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom = 'Dakar Dem Dikk'"
    ).fetchone()
    if not transport_row:
        return
    id_transport_ddd = transport_row[0]

    for numero in NUMEROS_LIGNES_DDD_FICTIVES_SANS_EQUIVALENT_2026:
        _supprimer_ligne_dem_dikk_2026(cursor, numero, id_transport_ddd)
    for numero in NUMEROS_LIGNES_DDD_FICTIVES_A_REMPLACER_2026:
        _supprimer_ligne_dem_dikk_2026(cursor, numero, id_transport_ddd)

    for numero_officiel, terminus_a, terminus_b in LIGNES_DEM_DIKK_OFFICIELLES_2026:
        numero_ligne = f"DDD {numero_officiel}"
        deja_migree = cursor.execute(
            "SELECT 1 FROM lignes_bus WHERE numero_ligne = ? AND id_transport = ?",
            (numero_ligne, id_transport_ddd)
        ).fetchone()
        if deja_migree:
            continue

        nom_ligne = f"{terminus_a} - {terminus_b}"
        description = f"Dakar Dem Dikk reliant {terminus_a} à {terminus_b}."
        cursor.execute(
            "INSERT INTO lignes_bus (numero_ligne, nom_ligne, id_transport, est_minibus, description) "
            "VALUES (?, ?, ?, 0, ?)",
            (numero_ligne, nom_ligne, id_transport_ddd, description)
        )
        id_ligne = cursor.lastrowid

        for ordre, nom_terminus in enumerate((terminus_a, terminus_b), start=1):
            lieu_row = cursor.execute(
                "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom_terminus,)
            ).fetchone()
            if not lieu_row:
                continue
            id_lieu, lat_arret, lng_arret = lieu_row
            cursor.execute(
                "INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES (?, ?, ?, ?)",
                (f"Arrêt {nom_terminus} ({numero_ligne})", id_lieu, lat_arret, lng_arret)
            )
            id_arret = cursor.lastrowid
            cursor.execute(
                "INSERT INTO ligne_arrets (id_ligne, id_arret, ordre) VALUES (?, ?, ?)",
                (id_ligne, id_arret, ordre)
            )


def _completer_images_transport_manquantes(cursor):
    """Complète l'image de certains moyens de transport ajoutée après le
    lancement initial (photos DDD et TER uploadées dans static/img/).
    Ne touche que les lignes où image_url est encore vide, pour ne jamais
    écraser une valeur déjà personnalisée."""
    images_par_defaut = {
        # Corrigé : le fichier réel livré dans static/img/ est "ddd.png"
        # (minuscules, extension .png) — l'ancien chemin "/static/img/DDD.jpg"
        # ne correspondait à aucun fichier existant et aurait affiché une
        # image cassée sur toute base migrée avant l'ajout de cette photo.
        "Dakar Dem Dikk": "/static/img/ddd.png",
        "TER": "/static/img/TER.jpg",
        "Ndiaga Ndiaye": "/static/img/Ndiaga_Ndiaye.png",
    }
    for nom, chemin_image in images_par_defaut.items():
        cursor.execute(
            "UPDATE moyens_transport SET image_url = ? WHERE nom = ? AND (image_url IS NULL OR image_url = '')",
            (chemin_image, nom)
        )


# ---------------------------------------------------------------------
# Tarifs 2026 : fourchettes réajustées vers des valeurs plus réalistes
# (recherche de tarifs actuels pour Dakar — taxi en ville, hausse des
# tickets Tata, tarif TER Dakar-Diamniadio, BRT à tarif fixe...).
# Appliqué par UPDATE conditionné au contenu actuel (voir
# _mettre_a_jour_tarifs_2026), donc sûr à rejouer sur une base qui a déjà
# ces tarifs.
# ---------------------------------------------------------------------
TARIFS_2026 = {
    "Taxi": (1000, 5000),
    "Clando": (200, 800),
    "Dakar Dem Dikk": (150, 350),
    "Car rapide": (100, 300),
    "Minibus Tata": (150, 300),
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


# Avantages / inconvénients retravaillés pour les 9 moyens de transport de
# la page /transports : exactement 3 avantages et 3 inconvénients par
# transport, alignés terme à terme sur les mêmes 3 axes (prix, couverture/
# disponibilité, confort/sécurité) pour une lecture plus structurée en
# vis-à-vis.
#
# Chaque item est un résumé court (une poignée de mots), pas une phrase
# complète : la première version (voir historique) tenait sur des phrases
# de 70-100 caractères qui s'étalaient sur 2-3 lignes dans la colonne
# étroite de la carte, rendant les cartes très inégales en hauteur. Le
# contenu est raccourci à la source (résumé), pas coupé visuellement en CSS.
#
# Important : le template (/transports) sépare les items avec
# `avantages.split(',')` — un item ne doit donc jamais contenir de virgule
# interne (utiliser "et"/parenthèses à la place), sous peine d'être découpé
# en plus de 3 puces à l'affichage.
AVANTAGES_INCONVENIENTS_2026 = {
    "Taxi": (
        "Tarif négociable, "
        "Disponible 24h/24 partout, "
        "Trajet direct porte-à-porte",
        "Plus cher que les autres transports, "
        "Rare et cher la nuit ou sous la pluie, "
        "Pas de compteur et confort variable",
    ),
    "Clando": (
        "Très économique car partagé, "
        "Dense sur les axes de banlieue, "
        "Alternative rapide au taxi",
        "Prix variable selon le chauffeur, "
        "Trajet fixe sans détour possible, "
        "Aucun signe distinctif et confort limité",
    ),
    "Dakar Dem Dikk": (
        "Tarif fixe et abordable, "
        "Réseau étendu à Dakar et en banlieue, "
        "Bus stable et plus grand qu'un minibus",
        "Plus cher qu'un Tata ou un car rapide, "
        "Fréquence irrégulière, "
        "Souvent bondé aux heures de pointe",
    ),
    "Car rapide": (
        "Le moins cher de Dakar, "
        "Présent sur de nombreux axes, "
        "Expérience authentique et populaire",
        "Tarif flou à vérifier avec l'apprenti, "
        "Aucun horaire fixe, "
        "Confort et sécurité limités",
    ),
    "Minibus Tata": (
        "Tarif fixe et très abordable, "
        "Réseau dense dans tous les quartiers, "
        "Bon rapport prix/fiabilité",
        "Ticket à garder jusqu'à la descente, "
        "Pas d'horaires fixes, "
        "Souvent bondé aux heures de pointe",
    ),
    "Jakarta (moto-taxi)": (
        "Prix raisonnable vu le temps gagné, "
        "Rapide et évite les embouteillages, "
        "Disponible 24h/24",
        "Plus cher qu'un Tata ou un car rapide, "
        "Peu adapté aux bagages ou longs trajets, "
        "Casque pas toujours fourni",
    ),
    "TER": (
        "Tarif fixe sans négociation, "
        "Liaison rapide Dakar-Diamniadio, "
        "Climatisé et confortable",
        "Plus cher qu'un bus ou un Tata, "
        "Peu de gares et inutile en intra-Dakar, "
        "Correspondance souvent nécessaire",
    ),
    "BRT (Bus Rapid Transit)": (
        "Tarif fixe et abordable, "
        "Un bus toutes les 6 minutes, "
        "Climatisé et quai de plain-pied",
        "Plus cher qu'un Tata sur le même trajet, "
        "Un seul axe (Petersen-Guédiawaye), "
        "Stations parfois éloignées",
    ),
    "Ndiaga Ndiaye": (
        "Un des tarifs les plus bas, "
        "Dessert des zones mal couvertes, "
        "Direct vers Pikine Guédiawaye et Keur Massar",
        "Tarif à confirmer avec le receveur, "
        "Rare en dehors du matin, "
        "Très chargé aux heures de pointe",
    ),
}


def _corriger_disponibilite_tata(cursor):
    """Recentre la disponibilité affichée du Tata sur le matin : le service
    se raréfie nettement en soirée, donc "tard le soir" donnait une
    impression de couverture tardive trompeuse. Fonctionne par UPDATE sur
    le nom, comme _mettre_a_jour_tarifs_2026 : met bien à jour les lignes
    déjà présentes sur une base existante (pas seulement à la création)."""
    nouvelle_disponibilite = "Tôt le matin, selon l'affluence"
    cursor.execute(
        "UPDATE moyens_transport SET disponibilite = ? "
        "WHERE nom = 'Minibus Tata' AND disponibilite != ?",
        (nouvelle_disponibilite, nouvelle_disponibilite)
    )


def _aligner_avantages_inconvenients_transports(cursor):
    """Recale les avantages/inconvénients de chaque moyen de transport vers
    exactement 3 avantages et 3 inconvénients alignés terme à terme (prix,
    couverture/disponibilité, confort/sécurité). Fonctionne par UPDATE sur
    le nom, comme _mettre_a_jour_tarifs_2026 : met bien à jour les lignes
    déjà présentes sur une base existante (pas seulement à la création)."""
    for nom, (avantages, inconvenients) in AVANTAGES_INCONVENIENTS_2026.items():
        cursor.execute(
            "UPDATE moyens_transport SET avantages = ?, inconvenients = ? "
            "WHERE nom = ? AND (avantages != ? OR inconvenients != ?)",
            (avantages, inconvenients, nom, avantages, inconvenients)
        )


# Descriptions retravaillées pour les 3 transports mis en avant sur
# l'accueil (Taxi, Clando, Minibus Tata) : les phrases d'origine, denses et
# à rallonge, sont remplacées par un ton plus direct et parlé. Ce champ
# étant partagé avec /transports, le bénéfice profite à tout le site.
DESCRIPTIONS_NATURELLES = {
    "Taxi": "Le taxi jaune et noir de Dakar, pour un trajet direct sans détour. Le prix se négocie avec le chauffeur avant de monter.",
    "Clando": "Une voiture partagée sur un axe fixe, à tarif divisé entre passagers. Moins cher qu'un taxi, un peu moins confortable.",
    "Minibus Tata": "Le minibus qui dessert la quasi-totalité des quartiers de Dakar, à prix fixe et très abordable.",
    # Version raccourcie : l'original listait le châssis Mercedes-Benz et le
    # détail des banlieues desservies (déjà couvert par les avantages),
    # ce qui rendait la carte /transports nettement plus longue que ses
    # voisines et cassait l'alignement des prix/avantages sur la même ligne.
    "Ndiaga Ndiaye": "Minibus blanc traditionnel, pilier du transport collectif vers Dakar et sa banlieue, surtout le matin et aux heures de pointe.",
    # DDD et BRT étaient les descriptions les plus longues restantes de la
    # page /transports (détails d'opérateur / de lignes déjà présents dans
    # les avantages) : résumées ici pour rester au même gabarit que leurs
    # voisines.
    "Dakar Dem Dikk": "Bus officiel de la ville de Dakar (DDD), lignes numérotées à tarif fixe, distinct du réseau Tata.",
    "BRT (Bus Rapid Transit)": "Bus électrique à haut niveau de service, reliant Petersen à Guédiawaye (lignes B1 et B2).",
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
            "Ndiaga Ndiaye", "/static/img/Ndiaga_Ndiaye.png",
            "Minibus blanc traditionnel, pilier du transport collectif vers Dakar et sa banlieue, surtout le matin "
            "et aux heures de pointe.",
            100, 350, "Faible", "Le matin et aux heures de pointe",
            "Très économique avec l'un des tarifs les plus bas du transport collectif, Dessert de nombreuses zones "
            "de banlieue mal couvertes par d'autres réseaux, Alternative directe et peu chère vers Pikine "
            "Guédiawaye ou Keur Massar",
            "Aucun tarif affiché à confirmer auprès du receveur avant de monter, Circule surtout le matin et aux "
            "heures de pointe et se fait rare en journée creuse, Très chargé aux heures de pointe avec un confort "
            "parfois limité",
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
    reliant..."), plutôt que sur un décalage numérique supposé —
    fonctionne donc quel que soit l'état exact de la base. Idempotent : ne
    modifie que les lignes encore mal rattachées."""
    corrections = [
        ('Dakar Dem Dikk', 'Dakar Dem Dikk %'),
        ('Car rapide', 'Car rapide %'),
        ('Minibus Tata', 'Minibus Tata %'),
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


# ---------------------------------------------------------------------
# CORRECTION DU LEXIQUE WOLOF (2026-07-17) — à la demande de l'utilisateur,
# locuteur natif, qui a fourni la liste des formulations réellement
# employées à Dakar en remplacement de plusieurs phrases approximatives
# introduites lors des vagues précédentes (ex. "Wesaare" pour "monnaie" au
# lieu de "Wéthiét", "Taxawal fii" au lieu de "Mayma fi", contresens sur
# "Kañ nga dem ?" pris pour un futur alors que c'est un passé...).
#
# CORRECTIONS_TEXTE_PHRASES_WOLOF : (ancien_wolof, nouveau_wolof,
# nouveau_francais ou None si inchangé, nouveau_phonetique ou None si
# inchangé). La clé de correspondance est l'ancien texte wolof exact, donc
# rejouable sans risque (une fois corrigée, la ligne ne matche plus
# l'ancien texte et la seconde exécution ne fait rien).
# ---------------------------------------------------------------------
CORRECTIONS_TEXTE_PHRASES_WOLOF = [
    ('Amuma wesaare', 'Amuma wéthiét', None, 'a-mou-ma wé-thi-ét'),
    ('Wesaareal ma', 'Wéthi ma', 'Rends-moi ma monnaie', 'wé-thi ma'),
    ('Wesaare', 'Wéthiét', 'Monnaie', 'wé-thi-ét'),
    ('Su la neexee', 'Su la neex', None, 'sou la néx'),
    ('Baal ma, dama bëgg laa laaj', 'Baal ma, dama la bëgg laaj', None, 'baal ma dama la beug laadj'),
    ('Waxuma wolof', 'Degguma wolof', None, 'dé-gou-ma wo-lof'),
    ('Ba beneen yoon', 'Ba benen', 'Au revoir', 'ba bé-nén'),
    ('Dama metti', 'Dama metti', 'Ça me fait mal / J\'ai mal', None),
    ('Sama xel dafa tang', 'Sama xel dafa jaxaso', 'Je suis inquiet(ète)', 'sa-ma xèl da-fa dja-xa-so'),
    ('Wallal ma !', 'Wallouma', 'Aide-moi', 'wa-lou-ma'),
    ('Fabu police bi', 'Wo len police', 'Appelez la police', 'wo lén po-lis'),
    ('Jëm ci kanam', 'Foubaleul ci kanam', None, 'fou-ba-lél ci ka-nam'),
    ('Jëm ci kaw', 'Felleul sa ndey-djoor', None, 'fè-lél sa ndèy-djor'),
    ('Jëm ci ndey', 'Felleul sa thiamon', None, 'fè-lél sa thia-mon'),
    ('Yagg na ?', 'Yagg na ?', 'Ça dure ?', None),
    ('Wallal ma, su la neexee', 'Neun nga ma diapalé ?', None, 'neun nga ma dia-pa-lé'),
    ('Dama wut universite bi', 'Damay weur université bi', None, 'da-may wér u-ni-vèr-si-té bi'),
    ('Dama wut opitaal bi', 'Opitaal bi lay wër ou seet', None, 'o-pi-tal bi lay wér ou séét'),
    ('Dama wut marse bi', 'Marse bi lay weur ou weet', None, 'mar-sé bi lay wér ou wéét'),
    ('Dama wut Plateau bi', 'Plateau bi lay weur ou weet', None, 'pla-to bi lay wér ou wéét'),
    ('Dama wut tefes bi', 'Guédj bi lay seet', None, 'guédj bi lay séét'),
    ('Dama wut station bi', 'Station bi lay seet', None, 'sta-syon bi lay séét'),
    ('Dina dem', 'Bayil ma dem', None, 'ba-yil ma dem'),
    ('Fii laa fey ?', 'Fi laay feyé', 'Je paie ici', 'fi laay fé-yé'),
    ('Fan laa mëna jël BRT bi ?', 'Fann la mëna jëler BRT bi ?', None, 'fann la mè-na djè-lér bi-èr-té bi'),
    ('Fan laa mëna jël TER bi ?', 'Fann la mëna jëler TER bi ?', None, 'fann la mè-na djè-lér té-euh-èr bi'),
    ('Ñaata waxtu la war ?', 'Ñaata waxtu no war ?', None, 'nya-ta wakh-tou no war'),
    ('Xibaar ma bu nu egsee', 'Meun nga ma wax bu nu egée', None, 'meun nga ma wakh bou nou é-gé'),
    ('Ana yow ?', 'Yaw nak, nodef ?', None, 'yaw nak no-déf'),
    ('Naka guddi gi ?', 'Naka guddii gi', 'Comment se passe la soirée ?', 'na-ka gou-dii gui'),
    ('Kañ nga dem ?', 'Kañ nga dem ?', 'Quand est-ce que tu es parti ? (il est déjà parti)', None),
    ('Ban gaal moo dem [lieu] ?', 'Ban mooy dem [lieu] ?', None, 'ban mo-y dem'),
    ('Tata bii, dafa dem [lieu] ?', 'Tata bi dafay dem [lieu] ?', None, 'ta-ta bi da-fay dem'),
    ('Ban ligne moo dem [lieu] ?', 'Ban ligne mooy dem [lieu] ?', None, 'ban ligne mo-y dem'),
    ('Ligne bii, dafa jaar ci [lieu] ?', 'Ligne bi dafay jaar [lieu] ?', None, 'ligne bi da-fay diar'),
    ('Taxawal fii !', 'Mayma fi', 'Arrêtez-vous ici', 'may-ma fi'),
    ('Yëgël ma ci...', 'Wathié ma ci...', None, 'wa-thi-é ma si...'),
    ('Wàcc fi !', 'Wàccal fi !', None, 'wa-tchal fi'),
    ('Ban arrêt bu topp ?', 'Ban arrêt mo ci toog ?', None, 'ban a-rè mo ci tog'),
]

# Nouvelles expressions signalées par l'utilisateur et absentes du lexique
# jusqu'ici (formes complémentaires : tutoiement/vouvoiement, urgence vs
# usage courant...). Même format que NOUVELLES_PHRASES_WOLOF_TRANSPORT.
NOUVELLES_PHRASES_WOLOF_REELLES_2026 = [
    ('Wéthi ko', 'Donne sa monnaie', 'wé-thi ko', 'Payer et connaître le tarif', None),
    ('Wéthi woma', "Vous ne m'avez pas rendu la monnaie", 'wé-thi wo-ma', 'Payer et connaître le tarif', None),
    ('Wéthi woko', "Il ne lui a pas rendu la monnaie", 'wé-thi wo-ko', 'Payer et connaître le tarif', None),
    ('Nguir Yàlla', "S'il te plaît", 'ngir yal-la', 'Poser une question', "Autre façon de dire « s'il te plaît »"),
    ('Dama feebar', 'Je suis malade', 'da-ma fé-bar', "Situations d'urgence", "À distinguer de « Dama metti » (j'ai mal)"),
    ('Walloo !', 'Aidez-moi ! (urgence)', 'wa-lo', "Situations d'urgence", "À crier en cas d'urgence réelle"),
    ('Kay len wallouma', "Venez m'aider !", 'kay lén wa-lou-ma', "Situations d'urgence", None),
    ('Wo waal police', 'Appelle la police', 'wo wal po-lis', "Situations d'urgence", "Forme au tutoiement"),
    ('Sori na ?', "C'est loin ?", 'so-ri na', 'Demander son chemin', None),
    ('Université bi lay weet', "Je cherche l'université", 'u-ni-vèr-si-té bi lay wéét', 'Demander son chemin', "Forme plus polie"),
    ('Waxma bou nu egée', 'Dis-moi quand nous arrivons', 'wakh-ma bou nou é-gé', 'Monter dans un Tata', None),
    ('Yaw nak', 'Et toi ?', 'yaw nak', 'Saluer', None),
    ('Kañ ngay dem ?', 'Quand pars-tu ?', 'kagn ngay dem', 'Monter dans un Tata', "À demander au chauffeur qui attend encore des passagers"),
    ('Ci tay wathie', "C'est ici que je descends", 'ci tay wa-thi-é', 'Demander un arrêt', None),
]


def _corriger_lexique_wolof_reel_2026(cursor):
    """Applique les corrections fournies par l'utilisateur (locuteur natif)
    sur le lexique wolof existant, et ajoute les expressions manquantes.
    Idempotent : chaque UPDATE cible l'ancien texte wolof exact (une fois
    corrigée, la ligne ne matche plus et la ré-exécution est un no-op) ; les
    ajouts sont conditionnés à l'absence de la phrase (vérification par
    texte wolof)."""
    for ancien_wolof, nouveau_wolof, nouveau_francais, nouveau_phonetique in CORRECTIONS_TEXTE_PHRASES_WOLOF:
        cursor.execute(
            "UPDATE phrases_wolof SET wolof = ?, francais = COALESCE(?, francais), "
            "phonetique = COALESCE(?, phonetique) WHERE wolof = ?",
            (nouveau_wolof, nouveau_francais, nouveau_phonetique, ancien_wolof)
        )

    # "Kañ nga dem ?" ne signifie pas "quand pars-tu ?" mais "quand es-tu
    # parti ?" (passé) : le contexte "à demander au chauffeur qui attend
    # encore des passagers", hérité du sens fautif, ne s'applique plus et
    # est retiré (il est repris par le nouveau "Kañ ngay dem ?" ci-dessus).
    cursor.execute(
        "UPDATE phrases_wolof SET contexte = NULL "
        "WHERE wolof = 'Kañ nga dem ?' "
        "AND contexte = 'À demander au chauffeur qui attend encore des passagers'"
    )

    for wolof, francais, phonetique, situation, contexte in NOUVELLES_PHRASES_WOLOF_REELLES_2026:
        existe = cursor.execute("SELECT 1 FROM phrases_wolof WHERE wolof = ?", (wolof,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO phrases_wolof (wolof, francais, phonetique, situation, contexte) VALUES (?, ?, ?, ?, ?)",
                (wolof, francais, phonetique, situation, contexte)
            )


NOUVELLES_LIGNES_MINIBUS = [
    {
        "numero_ligne": "Ligne 23", "nom_ligne": "Petersen - Yoff Layène",
        "description": "Minibus Tata reliant Petersen à Yoff Layène via Sacré-Cœur, Ouest Foire, Yoff",
        "arrets": ["Petersen", "Sacré-Cœur", "Ouest Foire", "Yoff", "Yoff Layène"],
    },
    {
        "numero_ligne": "Ligne 31", "nom_ligne": "Grand Yoff - Cité Djily Mbaye",
        "description": "Minibus Tata reliant Grand Yoff à Cité Djily Mbaye via Liberté 6, Liberté 6 Extension",
        "arrets": ["Grand Yoff", "Liberté 6", "Liberté 6 Extension", "Cité Djily Mbaye"],
    },
    {
        "numero_ligne": "Ligne 33", "nom_ligne": "Ouakam - Village des Arts",
        "description": "Minibus Tata reliant Ouakam au Village des Arts via Virage Ouakam et le Monument de la Renaissance Africaine",
        "arrets": ["Ouakam", "Virage Ouakam", "Monument de la Renaissance Africaine", "Village des Arts", "Cité Fadia"],
    },
    {
        "numero_ligne": "Ligne 51", "nom_ligne": "Colobane - Zac Mbao",
        "description": "Minibus Tata reliant Colobane à Zac Mbao via Hann, Mbao, Petit Mbao",
        "arrets": ["Colobane", "Hann", "Mbao", "Petit Mbao", "Zac Mbao"],
    },
    {
        "numero_ligne": "Ligne 61", "nom_ligne": "Pikine - Yeumbeul Sud",
        "description": "Minibus Tata reliant Pikine à Yeumbeul Sud via Thiaroye, Yeumbeul",
        "arrets": ["Pikine", "Thiaroye", "Yeumbeul", "Yeumbeul Sud"],
    },
    {
        "numero_ligne": "Ligne 68", "nom_ligne": "Médina - Gare de Dakar",
        "description": "Minibus Tata reliant Médina à la Gare de Dakar via Tilène, Plateau",
        "arrets": ["Médina", "Tilène", "Plateau", "Gare de Dakar"],
    },
]

# ---------------------------------------------------------------------
# Deuxième vague d'enrichissement du réseau Minibus Tata : le
# réseau est le moyen de transport en commun le moins cher de Dakar et le
# plus adapté au budget étudiant, mais restait sous-représenté par rapport
# au nombre réel de lignes AFTU. On densifie ici la couverture de quartiers
# déjà référencés dans `lieux` mais encore mal desservis par une ligne
# directe (Hann Maristes, Sicap Liberté, Rufisque profond, etc.).
# ---------------------------------------------------------------------
NOUVELLES_LIGNES_MINIBUS_2 = [
    {
        "numero_ligne": "Ligne 81", "nom_ligne": "Petersen - Hann Maristes",
        "description": "Minibus Tata reliant Petersen à Hann Maristes via Hann, Hann Bel-Air",
        "arrets": ["Petersen", "Hann", "Hann Bel-Air", "Hann Maristes"],
    },
    {
        "numero_ligne": "Ligne 82", "nom_ligne": "Sandaga - Sicap Liberté",
        "description": "Minibus Tata reliant Sandaga à Sicap Liberté via Colobane, HLM, Liberté 1",
        "arrets": ["Sandaga", "Colobane", "HLM", "Liberté 1", "Sicap Liberté"],
    },
    {
        "numero_ligne": "Ligne 83", "nom_ligne": "Médina - Fenêtre Mermoz",
        "description": "Minibus Tata reliant Médina à Fenêtre Mermoz via Fass, Point E, Amitié",
        "arrets": ["Médina", "Fass", "Point E", "Amitié", "Fenêtre Mermoz"],
    },
    {
        "numero_ligne": "Ligne 84", "nom_ligne": "Grand Yoff - Cité Assemblée",
        "description": "Minibus Tata reliant Grand Yoff à Cité Assemblée via Zone de Captage",
        "arrets": ["Grand Yoff", "Zone de Captage", "Cité Assemblée"],
    },
    {
        "numero_ligne": "Ligne 85", "nom_ligne": "Colobane - Yarakh",
        "description": "Minibus Tata reliant Colobane à Yarakh via Hann",
        "arrets": ["Colobane", "Hann", "Yarakh"],
    },
    {
        "numero_ligne": "Ligne 86", "nom_ligne": "Petersen - Cité Comico",
        "description": "Minibus Tata reliant Petersen à Cité Comico via Grand Dakar, Dieuppeul",
        "arrets": ["Petersen", "Grand Dakar", "Dieuppeul", "Cité Comico"],
    },
    {
        "numero_ligne": "Ligne 87", "nom_ligne": "Pikine - Cité Aliou Sow",
        "description": "Minibus Tata reliant Pikine à Cité Aliou Sow via Thiaroye Gare",
        "arrets": ["Pikine", "Thiaroye Gare", "Cité Aliou Sow"],
    },
    {
        "numero_ligne": "Ligne 88", "nom_ligne": "Mbao - Cité Millionnaire",
        "description": "Minibus Tata reliant Mbao à Cité Millionnaire via Petit Mbao",
        "arrets": ["Mbao", "Petit Mbao", "Cité Millionnaire"],
    },
    {
        "numero_ligne": "Ligne 89", "nom_ligne": "Rufisque - Diokoul",
        "description": "Minibus Tata reliant Rufisque à Diokoul via Rufisque Nord",
        "arrets": ["Rufisque", "Rufisque Nord", "Diokoul"],
    },
    {
        "numero_ligne": "Ligne 90", "nom_ligne": "Rufisque - Arafat",
        "description": "Minibus Tata reliant Rufisque à Arafat via Rufisque Est",
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


# Coordonnées réelles de l'Université Amadou Mahtar Mbow (UAM), campus
# universitaire du Pôle urbain de Diamniadio inauguré en 2022 — distinct de
# l'UCAD (Dakar intra-muros). Source : OpenStreetMap (way 593944367).
LIEU_UNIVERSITE_AMADOU_MAHTAR_MBOW = (
    'Université Amadou Mahtar Mbow', 'universite', 14.733981, -17.197246,
    "Université publique du Pôle urbain de Diamniadio, inaugurée en 2022 — distincte de l'UCAD"
)


def _ajouter_universite_amadou_mahtar_mbow(cursor):
    """Ajoute le lieu 'Université Amadou Mahtar Mbow' s'il n'existe pas déjà
    (vérification par nom), sans lui associer d'arrêt/ligne dédié : à environ
    30 km du centre de Dakar et à plus de 2 km du pôle TER de Diamniadio, ce
    trajet reste couvert par les options Taxi/Clando/Jakarta/Ndiaga Ndiaye
    (calculées à la volée par itineraire.py à partir de la distance), comme
    pour tout lieu réel non desservi par une ligne cartographiée."""
    nom, type_lieu, lat, lng, desc = LIEU_UNIVERSITE_AMADOU_MAHTAR_MBOW
    existe = cursor.execute("SELECT 1 FROM lieux WHERE nom = ?", (nom,)).fetchone()
    if not existe:
        cursor.execute(
            "INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES (?, ?, ?, ?, ?)",
            (nom, type_lieu, lat, lng, desc)
        )


# ---------------------------------------------------------------------
# Réseau Tata réel — remplacement des lignes fictives par les 70
# vraies lignes officielles publiées par l'AFTU (Association de
# Financement des professionnels du Transport Urbain), opérateur officiel
# du réseau, sur aftu-senegal.org/infos-pratiques/ (relevé du 2026-07-17).
# Numéros officiels couverts : 1-5, 24-38, 40-46, 48-89, 91 (70 lignes ;
# les numéros manquants entre 1 et 91 ne sont simplement pas publiés par
# l'AFTU à ce jour).
#
# Niveau de confiance des coordonnées des nouveaux lieux ci-dessous :
# - "position vérifiée" : coordonnées confirmées par une source
#   indépendante (recherche web ciblée, carte).
# - "position approximative" : aucune coordonnée précise publiée trouvée ;
#   estimation au niveau du quartier/de la commune connue, à corriger si
#   une source plus précise est un jour disponible. Ceci est explicitement
#   documenté ici plutôt que présenté comme une donnée exacte.
# ---------------------------------------------------------------------
NOUVEAUX_LIEUX_AFTU_REEL_2026 = [
    ('Terminus Lat Dior', 'quartier', 14.670416, -17.444279,
     "Terminus historique du réseau Tata, Plateau, à proximité du Palais de Justice (position approximative)"),
    ('HLM Grand Yoff', 'quartier', 14.7220, -17.4520,
     "Secteur à la frontière des quartiers HLM et Grand Yoff (position approximative)"),
    ('Sam Notaire (Guédiawaye)', 'quartier', 14.778, -17.408,
     "Commune d'arrondissement Sam Notaire, Guédiawaye (position approximative)"),
    ('Marché Boubess', 'quartier', 14.786387, -17.379171,
     "Marché de quartier à Guédiawaye, commune Wakhinane Nimzatt (position vérifiée)"),
    ('Hamo V/VI', 'quartier', 14.780, -17.390,
     "Secteur de la commune Ndiarème Limamoulaye, Guédiawaye (position approximative)"),
    ('Cité Nation Unies (Cambérène)', 'quartier', 14.752, -17.451,
     "Secteur de Cambérène (position approximative)"),
    ('Gadaye', 'quartier', 14.780, -17.395,
     "Quartier nord-est de Guédiawaye (position approximative)"),
    ('Tally Icotaf', 'quartier', 14.760, -17.395,
     "Carrefour avec la route des Niayes, secteur Pikine/Guédiawaye (position approximative)"),
    ('Hôpital Abass Ndao', 'site_touristique', 14.688030, -17.451800,
     "Hôpital public, avenue Cheikh Anta Diop, Gueule Tapée-Fass-Colobane (position vérifiée)"),
    ('Sahm', 'quartier', 14.773342, -17.396806,
     "Marché Sahm, commune Sam Notaire, Guédiawaye (position vérifiée)"),
    ('Serigne Assane', 'quartier', 14.771, -17.399,
     "Secteur du quartier Baghdad, commune Sam Notaire, Guédiawaye (position approximative)"),
    ('Marché Ndiareme', 'quartier', 14.776, -17.412,
     "Marché de quartier, commune Ndiarème Limamoulaye, Guédiawaye (position approximative)"),
    ('Diamalaye', 'quartier', 14.753250, -17.463281,
     "Secteur de Yoff, à la frontière avec Grand Médine (position vérifiée)"),
    ('Cité Claudel', 'quartier', 14.693, -17.462,
     "Connue localement sous le nom de Cité Aline Sitoe Diatta, secteur Fann/Point E (position approximative)"),
    ('Cité des Enseignants', 'quartier', 14.765, -17.412,
     "Secteur du quartier Golf, Guédiawaye/Pikine (position approximative)"),
    ('Ouakam Baye', 'quartier', 14.721248, -17.488743,
     "Secteur d'Ouakam (position vérifiée à l'échelle du quartier)"),
    ('Thierno Ndiaye', 'quartier', 14.722, -17.478,
     "Secteur à la frontière d'Ouakam et Grand Yoff (position approximative)"),
    ('Kounoune Ngalam', 'quartier', 14.714542, -17.275169,
     "Commune de Kounoune, département de Rufisque (position vérifiée)"),
    ('Cité Serigne Mansour', 'quartier', 14.768, -17.406,
     "Secteur de Guédiawaye (position approximative)"),
    ('Malika Cimetière', 'quartier', 14.787, -17.352,
     "Secteur du cimetière de Malika (position approximative)"),
    ('Jaxaay', 'quartier', 14.770533, -17.279533,
     "Cité de recasement de Jaxaay-Parcelles, Keur Massar (position vérifiée)"),
    ('Gare des Baux Maraîchers', 'gare', 14.741116, -17.402185,
     "Gare routière des Baux Maraîchers, en face du marché aux poissons (position vérifiée)"),
    ('Bountou Pikine', 'quartier', 14.744827, -17.400780,
     "Secteur le long de l'autoroute Seydina Limamoulaye, Pikine (position vérifiée)"),
    ('Terminus Keur Massar (Cité MTOA)', 'quartier', 14.786, -17.310,
     "Cité MTOA, secteur de Keur Massar (position approximative)"),
    ('Terminus Rufisque Sonadis', 'quartier', 14.712, -17.264,
     "Zone industrielle Sonadis, Rufisque Est (position approximative)"),
    ('Jaxaay 2', 'quartier', 14.768, -17.276,
     "Extension de la cité de Jaxaay (position approximative)"),
    ('Mbarou Samba Deme (Mbeubeuss)', 'quartier', 14.80963, -17.30342,
     "Secteur proche de la décharge de Mbeubeuss, Keur Massar Nord (position approximative)"),
    ('Arrêt Chérif', 'quartier', 14.718, -17.268,
     "Secteur de Rufisque (position approximative)"),
    ('Terminus Camp Marchand Rufisque', 'site_touristique', 14.715254, -17.270022,
     "Site historique de Rufisque Est (position approximative à l'échelle communale)"),
    ('Gorom 1', 'quartier', 14.760, -17.462,
     "Secteur côtier proche de Yoff/Cambérène cité par la ligne AFTU Yoff-Gorom 1 (position approximative et incertaine — non confirmée par une source cartographique indépendante)"),
    ('Thiawlène Rufisque', 'quartier', 14.708, -17.262,
     "Secteur côtier de Rufisque Est (position approximative)"),
    ('Terminus Tivaouane Peul', 'quartier', 14.800, -17.280,
     "Village proche de Mbeubeuss, commune Keur Massar Nord (position approximative)"),
    ('Daroukhane', 'quartier', 14.762, -17.398,
     "Secteur Daroukhoune, Pikine/Guédiawaye (position approximative)"),
    ('Sipres', 'quartier', 14.759, -17.397,
     "Cité Sipres — plusieurs cités portent ce nom au Sénégal ; position approximative pour le secteur Pikine/Guédiawaye visé par cette ligne"),
    ('Cité Assurance', 'quartier', 14.757, -17.393,
     "Secteur de Pikine (position approximative)"),
    ('Diamaguène', 'quartier', 14.747283, -17.320758,
     "Commune de Mbao, département de Pikine (position vérifiée)"),
    ('Darou Thioub', 'quartier', 14.760, -17.402,
     "Secteur Pikine/Guédiawaye (position approximative)"),
    ('Banoba', 'quartier', 14.726686, -17.280244,
     "Secteur du département Rufisque-Bargny (position approximative)"),
    ('Tournalou Boune', 'quartier', 14.690, -17.210,
     "Secteur côtier proche de Bargny/Sendou (position approximative)"),
    ('Toubab Dialaw', 'ville', 14.6061, -17.1503,
     "Village côtier connu pour son centre culturel, au sud de Bargny (position vérifiée)"),
    ('Mosquée Massalikoul Djinane', 'site_touristique', 14.704950, -17.453646,
     "Grande mosquée du secteur Grand Dakar (position vérifiée)"),
    ('Croisement Niague', 'quartier', 14.737155, -17.215637,
     "Village de la commune de Sangalkam (position vérifiée)"),
    ('APIX (Pôle urbain de Diamniadio)', 'entreprise', 14.720, -17.190,
     "Zone d'activités liée à l'agence APIX, proche de Diamniadio (position approximative)"),
    ('Dougar', 'quartier', 14.69, -17.17,
     "Village de l'arrondissement de Sébikotane (position approximative)"),
    ('Liberté 5', 'quartier', 14.708, -17.455,
     "Quartier voisin de Liberté 6 (position approximative)"),
]

# (numero_ligne, terminus A, terminus B) — noms de lieux devant exister
# soit dans NOUVEAUX_LIEUX_AFTU_REEL_2026 ci-dessus, soit déjà dans la
# table lieux (Petersen, UCAD, Colobane, Yoff, Ngor, Parcelles Assainies,
# Nord Foire, Grand Mbao, Ouakam, Keur Massar, Sébikotane, Liberté 6,
# Rufisque, Almadies, Bargny, Guédiawaye, Yeumbeul, Lac Rose (Retba),
# Sangalkam, Cambérène, Bambilor, Arafat, Zone de Captage, Malika, Gueule
# Tapée, Cité Comico, Stade Léopold Sédar Senghor, Pikine, Thiaroye).
LIGNES_AFTU_OFFICIELLES_2026 = [
    ("Ligne 1", "Terminus Lat Dior", "HLM Grand Yoff"),
    ("Ligne 2", "Parcelles Assainies", "Petersen"),
    ("Ligne 3", "Yoff", "Petersen"),
    ("Ligne 4", "Yoff", "Petersen"),
    ("Ligne 5", "Parcelles Assainies", "Petersen"),
    ("Ligne 24", "UCAD", "Sam Notaire (Guédiawaye)"),
    ("Ligne 25", "Parcelles Assainies", "Petersen"),
    ("Ligne 26", "Parcelles Assainies", "Thiaroye"),
    ("Ligne 27", "Marché Boubess", "Petersen"),
    ("Ligne 28", "Hamo V/VI", "Petersen"),
    ("Ligne 29", "Cité Nation Unies (Cambérène)", "Petersen"),
    ("Ligne 30", "Gadaye", "Colobane"),
    ("Ligne 31", "Tally Icotaf", "Hôpital Abass Ndao"),
    ("Ligne 32", "Sahm", "Serigne Assane"),
    ("Ligne 33", "Colobane", "Serigne Assane"),
    ("Ligne 34", "Nord Foire", "Terminus Lat Dior"),
    ("Ligne 35", "Ngor", "Pikine"),
    ("Ligne 36", "Marché Ndiareme", "Ngor"),
    ("Ligne 37", "Diamalaye", "Cité Claudel"),
    ("Ligne 38", "Cité des Enseignants", "Sahm"),
    ("Ligne 40", "Grand Mbao", "Petersen"),
    ("Ligne 41", "Petersen", "Marché Boubess"),
    ("Ligne 42", "Gadaye", "Ouakam Baye"),
    ("Ligne 43", "Ouakam", "Thierno Ndiaye"),
    ("Ligne 44", "Grand Mbao", "Ouakam"),
    ("Ligne 45", "Kounoune Ngalam", "Parcelles Assainies"),
    ("Ligne 46", "Serigne Assane", "Terminus Lat Dior"),
    ("Ligne 48", "Cité Serigne Mansour", "Terminus Lat Dior"),
    ("Ligne 49", "Gadaye", "Ngor"),
    ("Ligne 50", "Petersen", "Malika Cimetière"),
    ("Ligne 51", "Jaxaay", "Gare des Baux Maraîchers"),
    ("Ligne 52", "Bountou Pikine", "Keur Massar"),
    ("Ligne 53", "Keur Massar", "Sébikotane"),
    ("Ligne 54", "Terminus Keur Massar (Cité MTOA)", "UCAD"),
    ("Ligne 55", "Terminus Rufisque Sonadis", "Petersen"),
    ("Ligne 56", "Jaxaay 2", "Petersen"),
    ("Ligne 57", "Liberté 6", "Rufisque"),
    ("Ligne 58", "Sahm", "Cité Comico"),
    ("Ligne 59", "Stade Léopold Sédar Senghor", "Mbarou Samba Deme (Mbeubeuss)"),
    ("Ligne 60", "Colobane", "Bargny"),
    ("Ligne 61", "Almadies", "Keur Massar"),
    ("Ligne 62", "Arrêt Chérif", "Gueule Tapée"),
    ("Ligne 63", "Terminus Camp Marchand Rufisque", "Stade Léopold Sédar Senghor"),
    ("Ligne 64", "Guédiawaye", "Rufisque"),
    ("Ligne 65", "Colobane", "Jaxaay"),
    ("Ligne 66", "Yoff", "Gorom 1"),
    ("Ligne 67", "Ouakam", "Thiawlène Rufisque"),
    ("Ligne 68", "Yeumbeul", "Sébikotane"),
    ("Ligne 69", "Diamalaye", "Terminus Tivaouane Peul"),
    ("Ligne 70", "Daroukhane", "Jaxaay 2"),
    ("Ligne 71", "Keur Massar", "Cité Claudel"),
    ("Ligne 72", "Guédiawaye", "Kounoune Ngalam"),
    ("Ligne 73", "Lac Rose (Retba)", "Thiaroye"),
    ("Ligne 74", "Bargny", "Terminus Tivaouane Peul"),
    ("Ligne 75", "Malika", "Colobane"),
    ("Ligne 76", "Sipres", "Cité Assurance"),
    ("Ligne 77", "Rufisque", "Liberté 5"),
    ("Ligne 78", "Diamaguène", "Liberté 5"),
    ("Ligne 79", "Sangalkam", "Cambérène"),
    ("Ligne 80", "Diamalaye", "Darou Thioub"),
    ("Ligne 81", "Gare des Baux Maraîchers", "Terminus Tivaouane Peul"),
    ("Ligne 82", "Terminus Lat Dior", "Cité Comico"),
    ("Ligne 83", "Arafat", "Zone de Captage"),
    ("Ligne 84", "UCAD", "Jaxaay"),
    ("Ligne 85", "Banoba", "Liberté 5"),
    ("Ligne 86", "Tournalou Boune", "Toubab Dialaw"),
    ("Ligne 87", "Bambilor", "Mosquée Massalikoul Djinane"),
    ("Ligne 88", "Terminus Keur Massar (Cité MTOA)", "Liberté 5"),
    ("Ligne 89", "Bargny", "Croisement Niague"),
    ("Ligne 91", "APIX (Pôle urbain de Diamniadio)", "Dougar"),
]

MARQUEUR_LIGNE_AFTU_REELLE_2026 = "[AFTU officiel 2026]"


def _remplacer_par_lignes_aftu_reelles_2026(cursor):
    """Remplace, pour chaque numéro officiel AFTU listé dans
    LIGNES_AFTU_OFFICIELLES_2026, la ligne existante (fictive, inventée
    lors d'itérations précédentes du projet) par la vraie ligne Tata
    correspondante — mêmes deux vrais terminus que ceux publiés par
    l'AFTU. Les lignes qui n'ont pas de détail d'arrêts intermédiaires
    publié par l'AFTU sont volontairement modélisées comme des lignes à 2
    arrêts (terminus de départ / terminus d'arrivée) plutôt que
    d'inventer un tracé intermédiaire fictif.

    Idempotent et non-destructif vis-à-vis des données réelles : si une
    ligne existe déjà pour ce numéro avec le nom exact
    "{terminus_a} - {terminus_b}", elle est considérée comme déjà migrée
    et la fonction ne la retouche plus jamais (elle ne supprime donc que
    l'ancien contenu FICTIF, une seule fois, jamais les vraies données une
    fois en place). Le nom de ligne (deux vrais terminus) sert lui-même de
    marqueur — pas besoin d'exposer de mention de source ni le nom de
    l'opérateur dans la description affichée aux visiteurs."""
    for nom, type_lieu, lat, lng, desc in NOUVEAUX_LIEUX_AFTU_REEL_2026:
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

    for numero_ligne, terminus_a, terminus_b in LIGNES_AFTU_OFFICIELLES_2026:
        nom_ligne_reelle = f"{terminus_a} - {terminus_b}"
        deja_migree = cursor.execute(
            "SELECT 1 FROM lignes_bus WHERE numero_ligne = ? AND nom_ligne = ?",
            (numero_ligne, nom_ligne_reelle)
        ).fetchone()
        if deja_migree:
            continue

        ancienne_ligne = cursor.execute(
            "SELECT id_ligne FROM lignes_bus WHERE numero_ligne = ?", (numero_ligne,)
        ).fetchone()
        if ancienne_ligne:
            id_ancienne = ancienne_ligne[0]
            # Ordre important : ligne_arrets référence arrets par clé
            # étrangère (PRAGMA foreign_keys = ON dans schema.sql), donc on
            # supprime d'abord les lignes de jonction avant les arrêts
            # eux-mêmes (même ordre que _retirer_lignes_dit_fictives).
            #
            # MAIS contrairement aux lignes DIT-1..5 (qui avaient leurs
            # propres arrêts dédiés), le réseau fictif d'origine (donnees.sql)
            # PARTAGE de nombreux arrêts-carrefour entre plusieurs lignes
            # (ex: id_arret 14, 24... référencés par 4-5 lignes différentes
            # à la fois). Un arrêt ne doit donc être supprimé que s'il n'est
            # plus référencé par AUCUNE autre ligne après la suppression du
            # tracé fictif remplacé ici — sinon on casse la contrainte de
            # clé étrangère des autres lignes qui l'utilisent encore.
            arrets_a_supprimer = cursor.execute(
                "SELECT id_arret FROM ligne_arrets WHERE id_ligne = ?", (id_ancienne,)
            ).fetchall()
            cursor.execute("DELETE FROM ligne_arrets WHERE id_ligne = ?", (id_ancienne,))
            for arret_row in arrets_a_supprimer:
                id_arret_candidat = arret_row[0]
                encore_reference = cursor.execute(
                    "SELECT 1 FROM ligne_arrets WHERE id_arret = ?", (id_arret_candidat,)
                ).fetchone()
                if not encore_reference:
                    cursor.execute("DELETE FROM arrets WHERE id_arret = ?", (id_arret_candidat,))
            cursor.execute("DELETE FROM lignes_bus WHERE id_ligne = ?", (id_ancienne,))

        nom_ligne = f"{terminus_a} - {terminus_b}"
        description = f"Minibus Tata reliant {terminus_a} à {terminus_b}."
        cursor.execute(
            "INSERT INTO lignes_bus (numero_ligne, nom_ligne, id_transport, est_minibus, description) "
            "VALUES (?, ?, ?, 1, ?)",
            (numero_ligne, nom_ligne, id_transport_tata, description)
        )
        id_ligne = cursor.lastrowid

        for ordre, nom_terminus in enumerate((terminus_a, terminus_b), start=1):
            lieu_row = cursor.execute(
                "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom_terminus,)
            ).fetchone()
            if not lieu_row:
                continue
            id_lieu, lat_arret, lng_arret = lieu_row
            cursor.execute(
                "INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES (?, ?, ?, ?)",
                (f"Arrêt {nom_terminus} ({numero_ligne})", id_lieu, lat_arret, lng_arret)
            )
            id_arret = cursor.lastrowid
            cursor.execute(
                "INSERT INTO ligne_arrets (id_ligne, id_arret, ordre) VALUES (?, ?, ?)",
                (id_ligne, id_arret, ordre)
            )


NUMEROS_LIGNES_TATA_NON_OFFICIELLES_2026 = (
    list(range(6, 24)) + [39, 47, 90] + list(range(92, 131))
)


def _retirer_lignes_tata_non_officielles_2026(cursor):
    """Retire les lignes Tata dont le numéro ne fait PAS partie des 70
    numéros officiels publiés par l'AFTU (voir LIGNES_AFTU_OFFICIELLES_2026
    ci-dessus) : ces ~60 lignes (numéros 6-23, 39, 47, 90, 92-130) restaient
    du réseau inventé lors d'itérations précédentes du projet, sans aucune
    correspondance avec un numéro AFTU réel — l'utilisateur a explicitement
    demandé leur suppression plutôt que de les laisser affichées à côté des
    70 vraies lignes sur /minibus sans distinction possible.

    Même précaution que _remplacer_par_lignes_aftu_reelles_2026 : certains
    arrêts de ces lignes fictives sont partagés avec d'autres lignes encore
    présentes en base (arrêts-carrefour du réseau d'origine), donc un arrêt
    n'est supprimé que s'il n'est plus référencé par aucune autre ligne
    après le retrait de celle-ci. Idempotent : ne fait rien si ces lignes
    ont déjà été retirées lors d'une exécution précédente."""
    for numero in NUMEROS_LIGNES_TATA_NON_OFFICIELLES_2026:
        numero_ligne = f"Ligne {numero}"
        ligne_row = cursor.execute(
            "SELECT id_ligne FROM lignes_bus WHERE numero_ligne = ?", (numero_ligne,)
        ).fetchone()
        if not ligne_row:
            continue
        id_ligne = ligne_row[0]

        arrets_a_supprimer = cursor.execute(
            "SELECT id_arret FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,)
        ).fetchall()
        cursor.execute("DELETE FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,))
        for arret_row in arrets_a_supprimer:
            id_arret_candidat = arret_row[0]
            encore_reference = cursor.execute(
                "SELECT 1 FROM ligne_arrets WHERE id_arret = ?", (id_arret_candidat,)
            ).fetchone()
            if not encore_reference:
                cursor.execute("DELETE FROM arrets WHERE id_arret = ?", (id_arret_candidat,))
        cursor.execute("DELETE FROM lignes_bus WHERE id_ligne = ?", (id_ligne,))


# ---------------------------------------------------------------------
# Enrichissement du réseau BRT (lignes B1/B2) avec les vraies stations
# officielles du SunuBRT Petersen-Guédiawaye, à la demande de l'utilisateur
# après avoir signalé que le BRT n'apparaissait pas comme option pour un
# trajet Sacré-Cœur -> Liberté 6 alors que c'est le moyen le plus sûr pour
# un étranger. Cause identifiée : la ligne B1 existante ne comportait que 8
# arrêts (Petersen, Grand Dakar, Sacré-Cœur, Front de Terre, Patte d'Oie,
# Parcelles Assainies, Golf Sud, Préfecture Guédiawaye) — "Front de Terre"
# et "Patte d'Oie" ne correspondent à aucun nom de station BRT officielle
# trouvé (CETUD, presse, OSM network=SunuBRT), et surtout aucun arrêt
# n'existait près de Liberté 6, qui est pourtant une vraie station BRT (le
# rond-point Liberté 6 lui-même — confirmé par CETUD et par la presse
# locale lors du vandalisme de la station en 2024).
#
# Sources : CETUD (cetud.sn/les-caracteristiques-techniques-du-projet-brt),
# liste des 14 gares au lancement (mai 2024, SENTV/Senego), annonces
# d'ouverture de gares supplémentaires (2025), et les points OSM tagués
# network=SunuBRT pour les coordonnées. La station "Gueule Tapée" citée
# dans une annonce d'ouverture n'a pas été intégrée : sa localisation
# annoncée (secteur de Guédiawaye) entre en conflit avec le quartier bien
# connu du même nom près de la Médina, et aucune coordonnée fiable n'a pu
# distinguer les deux — plutôt que de risquer une confusion, cette station
# est délibérément omise pour l'instant.
# ---------------------------------------------------------------------
NOUVEAUX_LIEUX_BRT_2026 = [
    ('Place de la Nation (BRT)', 'quartier', 14.694, -17.449,
     "Anciennement Place de l'Obélisque, boulevard Général de Gaulle (position vérifiée)"),
    ('Dial Diop (BRT)', 'quartier', 14.705, -17.454,
     "Secteur du boulevard Dial Diop, Grand Dakar (position approximative — centroïde du quartier Grand Dakar)"),
    ('Khar Yàlla', 'quartier', 14.729, -17.451,
     "Secteur de Grand Yoff, entre Sicap-Liberté et Dieuppeul-Derklé (position vérifiée)"),
    ('Scat Urbam', 'quartier', 14.736, -17.459,
     "Secteur de Grand Yoff, proche de Sicap-Liberté (position vérifiée)"),
    ('Cardinal Hyacinthe Thiandoum (BRT)', 'quartier', 14.737, -17.453,
     "Près de l'échangeur Aliou Sow, Grand Yoff (position approximative — centroïde du quartier Grand Yoff, nom exact de la station non localisé précisément)"),
    ('Police des Parcelles', 'quartier', 14.751, -17.440,
     "Station BRT taguée dans OpenStreetMap (network=SunuBRT), Parcelles Assainies (position vérifiée)"),
    ('Croisement 22', 'quartier', 14.753, -17.434,
     "Station BRT taguée dans OpenStreetMap (network=SunuBRT), Parcelles Assainies (position vérifiée)"),
    ('Ndingala', 'quartier', 14.752, -17.438,
     "Secteur de Parcelles Assainies, entre Police des Parcelles et Golf Sud (position approximative — aucune coordonnée précise trouvée)"),
    ('Golf Nord', 'quartier', 14.776, -17.399,
     "Station BRT taguée dans OpenStreetMap (network=SunuBRT), Guédiawaye (position vérifiée)"),
    ('Fith Mith', 'quartier', 14.775, -17.406,
     "Station BRT taguée dans OpenStreetMap (network=SunuBRT), Guédiawaye, ouverte en 2025 (position vérifiée)"),
]

# Ordre géographique Petersen -> Préfecture de Guédiawaye. Les noms déjà
# présents dans `lieux` (Petersen, Grande Mosquée de Dakar, Grand Dakar,
# Liberté 1, Sacré-Cœur, Liberté 5, Liberté 6, Grand Médine, Parcelles
# Assainies, Golf Sud, Hôpital Dalal Jamm, Guédiawaye) sont réutilisés tels
# quels, sans créer de doublon.
STATIONS_BRT_B1_OMNIBUS_2026 = [
    "Petersen", "Grande Mosquée de Dakar", "Place de la Nation (BRT)", "Dial Diop (BRT)",
    "Grand Dakar", "Liberté 1", "Sacré-Cœur", "Liberté 5", "Liberté 6",
    "Khar Yàlla", "Scat Urbam", "Cardinal Hyacinthe Thiandoum (BRT)", "Grand Médine",
    "Police des Parcelles", "Croisement 22", "Parcelles Assainies", "Ndingala",
    "Golf Sud", "Hôpital Dalal Jamm", "Golf Nord", "Fith Mith", "Guédiawaye",
]

# Ligne semi-express : ne dessert que les pôles principaux du corridor.
STATIONS_BRT_B2_SEMI_EXPRESS_2026 = [
    "Petersen", "Place de la Nation (BRT)", "Grand Dakar", "Sacré-Cœur",
    "Grand Médine", "Hôpital Dalal Jamm", "Guédiawaye",
]

MARQUEUR_BRT_ENRICHI_2026 = "[BRT enrichi 2026]"


def _enrichir_lignes_brt_2026(cursor):
    """Remplace le tracé (arrêts) des lignes B1 et B2 par la vraie liste de
    stations SunuBRT ci-dessus, en conservant le même numero_ligne (B1/B2)
    et donc le même id_ligne — contrairement au remplacement des lignes
    Tata fictives, il ne s'agit pas de renuméroter quoi que ce soit, juste
    de corriger le tracé d'une ligne réelle déjà existante.

    Même précaution que pour les autres suppressions de ce module : un
    arrêt n'est supprimé que s'il n'est plus référencé par aucune autre
    ligne. Idempotent (marqueur dédié dans la description empêchant toute
    ré-exécution destructive une fois le tracé réel en place)."""
    for nom, type_lieu, lat, lng, desc in NOUVEAUX_LIEUX_BRT_2026:
        existe = cursor.execute("SELECT 1 FROM lieux WHERE nom = ?", (nom,)).fetchone()
        if not existe:
            cursor.execute(
                "INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES (?, ?, ?, ?, ?)",
                (nom, type_lieu, lat, lng, desc)
            )

    for numero_ligne, stations in (
        ("B1", STATIONS_BRT_B1_OMNIBUS_2026),
        ("B2", STATIONS_BRT_B2_SEMI_EXPRESS_2026),
    ):
        ligne_row = cursor.execute(
            "SELECT id_ligne, description FROM lignes_bus WHERE numero_ligne = ?", (numero_ligne,)
        ).fetchone()
        if not ligne_row:
            continue
        id_ligne, description_actuelle = ligne_row
        if description_actuelle and MARQUEUR_BRT_ENRICHI_2026 in description_actuelle:
            continue

        arrets_a_supprimer = cursor.execute(
            "SELECT id_arret FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,)
        ).fetchall()
        cursor.execute("DELETE FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,))
        for arret_row in arrets_a_supprimer:
            id_arret_candidat = arret_row[0]
            encore_reference = cursor.execute(
                "SELECT 1 FROM ligne_arrets WHERE id_arret = ?", (id_arret_candidat,)
            ).fetchone()
            if not encore_reference:
                cursor.execute("DELETE FROM arrets WHERE id_arret = ?", (id_arret_candidat,))

        nouvelle_description = (
            f"{description_actuelle or ''} {MARQUEUR_BRT_ENRICHI_2026}".strip()
        )
        cursor.execute(
            "UPDATE lignes_bus SET description = ? WHERE id_ligne = ?",
            (nouvelle_description, id_ligne)
        )

        for ordre, nom_station in enumerate(stations, start=1):
            lieu_row = cursor.execute(
                "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom_station,)
            ).fetchone()
            if not lieu_row:
                continue
            id_lieu, lat_arret, lng_arret = lieu_row
            cursor.execute(
                "INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES (?, ?, ?, ?)",
                (f"Station {nom_station} ({numero_ligne})", id_lieu, lat_arret, lng_arret)
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
    {"numero_ligne": "Ligne 17", "nom_ligne": "Sandaga - Grande Mosquée de Dakar", "description": "Minibus Tata reliant Sandaga à la Grande Mosquée de Dakar via Médina.", "arrets": ["Sandaga", "Médina", "Grande Mosquée de Dakar"]},
    {"numero_ligne": "Ligne 35", "nom_ligne": "Ouakam - Almadies (via Route de l'Aéroport)", "description": "Minibus Tata reliant Ouakam à Almadies via Virage Ouakam et Mamelles.", "arrets": ["Ouakam", "Virage Ouakam", "Mamelles", "Almadies"]},
    {"numero_ligne": "Ligne 37", "nom_ligne": "Guédiawaye - Golf", "description": "Minibus Tata reliant Guédiawaye à Golf via Wakhinane.", "arrets": ["Guédiawaye", "Wakhinane", "Golf"]},
    {"numero_ligne": "Ligne 54", "nom_ligne": "Pikine - Thiaroye sur Mer", "description": "Minibus Tata reliant Pikine à Thiaroye sur Mer via Guinaw Rail.", "arrets": ["Pikine", "Guinaw Rail", "Thiaroye sur Mer"]},
    {"numero_ligne": "Ligne 59", "nom_ligne": "Wakhinane - Médina Gounass", "description": "Minibus Tata reliant Wakhinane à Médina Gounass, liaison locale de Guédiawaye.", "arrets": ["Wakhinane", "Médina Gounass"]},
    {"numero_ligne": "Ligne 62", "nom_ligne": "Rufisque Nord - Bargny", "description": "Minibus Tata reliant Rufisque Nord à Bargny.", "arrets": ["Rufisque Nord", "Bargny"]},
    {"numero_ligne": "Ligne 69", "nom_ligne": "Colobane - CICES", "description": "Minibus Tata reliant Colobane au CICES via Grand Dakar et Nord Foire.", "arrets": ["Colobane", "Grand Dakar", "Nord Foire", "CICES"]},
    {"numero_ligne": "Ligne 71", "nom_ligne": "Gueule Tapée - Keur Massar (via Grand Dakar)", "description": "Minibus Tata reliant Gueule Tapée à Keur Massar via Grand Dakar, Pikine et Diacksao.", "arrets": ["Gueule Tapée", "Grand Dakar", "Pikine", "Diacksao", "Keur Massar"]},
    {"numero_ligne": "Ligne 73", "nom_ligne": "Fann - Village Artisanal de Soumbédioune", "description": "Minibus Tata reliant Fann au Village Artisanal de Soumbédioune, le long de la Corniche.", "arrets": ["Fann", "Village Artisanal de Soumbédioune"]},
    {"numero_ligne": "Ligne 74", "nom_ligne": "Médina - Stade Iba Mar Diop", "description": "Minibus Tata reliant Médina au Stade Iba Mar Diop via Tilène.", "arrets": ["Médina", "Tilène", "Stade Iba Mar Diop"]},
    {"numero_ligne": "Ligne 76", "nom_ligne": "Liberté 6 - Sicap Baobab", "description": "Minibus Tata reliant Liberté 6 à Sicap Baobab.", "arrets": ["Liberté 6", "Sicap Baobab"]},
    {"numero_ligne": "Ligne 77", "nom_ligne": "Grand Yoff - Stade Léopold Sédar Senghor", "description": "Minibus Tata reliant Grand Yoff au Stade Léopold Sédar Senghor via Zone de Captage et Fenêtre Mermoz.", "arrets": ["Grand Yoff", "Zone de Captage", "Fenêtre Mermoz", "Stade Léopold Sédar Senghor"]},
    {"numero_ligne": "Ligne 79", "nom_ligne": "Cambérène - Cimetière de Yoff", "description": "Minibus Tata reliant Cambérène au secteur du Cimetière de Yoff.", "arrets": ["Cambérène", "Cimetière de Yoff"]},
    {"numero_ligne": "Ligne 91", "nom_ligne": "Plateau - Hôpital Principal de Dakar", "description": "Minibus Tata reliant le Plateau à l'Hôpital Principal de Dakar.", "arrets": ["Plateau", "Hôpital Principal de Dakar"]},
    {"numero_ligne": "Ligne 92", "nom_ligne": "Petersen - Place de l'Indépendance", "description": "Minibus Tata reliant Petersen à la Place de l'Indépendance via le Plateau.", "arrets": ["Petersen", "Plateau", "Place de l'Indépendance"]},
    {"numero_ligne": "Ligne 93", "nom_ligne": "Yoff - Cimetière de Yoff", "description": "Minibus Tata, courte liaison locale du village de Yoff.", "arrets": ["Yoff", "Cimetière de Yoff"]},
    {"numero_ligne": "Ligne 94", "nom_ligne": "Ouest Foire - CICES", "description": "Minibus Tata reliant Ouest Foire au CICES via Nord Foire.", "arrets": ["Ouest Foire", "Nord Foire", "CICES"]},
    {"numero_ligne": "Ligne 95", "nom_ligne": "Sacré-Cœur - Stade Léopold Sédar Senghor", "description": "Minibus Tata reliant Sacré-Cœur au Stade Léopold Sédar Senghor via Fenêtre Mermoz.", "arrets": ["Sacré-Cœur", "Fenêtre Mermoz", "Stade Léopold Sédar Senghor"]},
    {"numero_ligne": "Ligne 96", "nom_ligne": "Rufisque - Sébikotane", "description": "Minibus Tata reliant Rufisque à Sébikotane via Rufisque Est et Bargny.", "arrets": ["Rufisque", "Rufisque Est", "Bargny", "Sébikotane"]},
    {"numero_ligne": "Ligne 97", "nom_ligne": "Bargny - Diamniadio", "description": "Minibus Tata reliant Bargny à Diamniadio.", "arrets": ["Bargny", "Diamniadio"]},
    {"numero_ligne": "Ligne 98", "nom_ligne": "Yenne - Bargny", "description": "Minibus Tata reliant Yenne à Bargny.", "arrets": ["Yenne", "Bargny"]},
    {"numero_ligne": "Ligne 99", "nom_ligne": "Diamniadio - Sangalkam", "description": "Minibus Tata reliant Diamniadio à Sangalkam.", "arrets": ["Diamniadio", "Sangalkam"]},
    {"numero_ligne": "Ligne 100", "nom_ligne": "Guédiawaye - Hôpital Dalal Jamm", "description": "Minibus Tata reliant Guédiawaye à l'Hôpital Dalal Jamm via Wakhinane.", "arrets": ["Guédiawaye", "Wakhinane", "Hôpital Dalal Jamm"]},
    {"numero_ligne": "Ligne 101", "nom_ligne": "Ngor - Village Artisanal de Soumbédioune", "description": "Minibus Tata reliant Ngor au Village Artisanal de Soumbédioune via la Corniche Ouest et Fann.", "arrets": ["Ngor", "Corniche Ouest", "Fann", "Village Artisanal de Soumbédioune"]},
    {"numero_ligne": "Ligne 102", "nom_ligne": "Colobane - Grande Mosquée de Dakar", "description": "Minibus Tata reliant Colobane à la Grande Mosquée de Dakar via Médina.", "arrets": ["Colobane", "Médina", "Grande Mosquée de Dakar"]},
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
# Quatrième vague d'enrichissement, focalisée sur le réseau Tata
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
    {"numero_ligne": "Ligne 103", "nom_ligne": "Petersen - Technopole (via Cité Keur Gorgui)", "description": "Minibus Tata reliant Petersen à Technopole via Sacré-Cœur et Cité Keur Gorgui.", "arrets": ["Petersen", "Sacré-Cœur", "Cité Keur Gorgui", "Technopole"]},
    {"numero_ligne": "Ligne 104", "nom_ligne": "Sandaga - Parc Zoologique de Hann", "description": "Minibus Tata reliant Sandaga au Parc Zoologique de Hann via Colobane et Hann.", "arrets": ["Sandaga", "Colobane", "Hann", "Parc Zoologique de Hann"]},
    {"numero_ligne": "Ligne 105", "nom_ligne": "Pikine - Ouagou Niayes", "description": "Minibus Tata reliant Pikine à Ouagou Niayes via Guinaw Rail.", "arrets": ["Pikine", "Guinaw Rail", "Ouagou Niayes"]},
    {"numero_ligne": "Ligne 106", "nom_ligne": "Yoff - Terminus Yoff", "description": "Minibus Tata, liaison locale du village de Yoff.", "arrets": ["Yoff", "Terminus Yoff"]},
    {"numero_ligne": "Ligne 107", "nom_ligne": "UCAD - École Supérieure Polytechnique", "description": "Minibus Tata, navette du campus universitaire.", "arrets": ["UCAD", "École Supérieure Polytechnique"]},
    {"numero_ligne": "Ligne 108", "nom_ligne": "Guédiawaye - Marché Syndicat", "description": "Minibus Tata reliant Guédiawaye au Marché Syndicat.", "arrets": ["Guédiawaye", "Marché Syndicat"]},
    {"numero_ligne": "Ligne 109", "nom_ligne": "Rufisque - Terminus Rufisque", "description": "Minibus Tata, liaison locale de Rufisque.", "arrets": ["Rufisque", "Terminus Rufisque"]},
    {"numero_ligne": "Ligne 110", "nom_ligne": "Ngor - Ngor Plage", "description": "Minibus Tata, courte liaison vers la plage de Ngor.", "arrets": ["Ngor", "Ngor Plage"]},
    {"numero_ligne": "Ligne 111", "nom_ligne": "Médina - Fann (direct)", "description": "Minibus Tata reliant Médina à Fann via Fass.", "arrets": ["Médina", "Fass", "Fann"]},
    {"numero_ligne": "Ligne 112", "nom_ligne": "Colobane - Point E", "description": "Minibus Tata reliant Colobane à Point E via Fass.", "arrets": ["Colobane", "Fass", "Point E"]},
    {"numero_ligne": "Ligne 113", "nom_ligne": "HLM - Grand Médine", "description": "Minibus Tata reliant HLM à Grand Médine via Front de Terre.", "arrets": ["HLM", "Front de Terre", "Grand Médine"]},
    {"numero_ligne": "Ligne 114", "nom_ligne": "Sicap Baobab - Zone de Captage", "description": "Minibus Tata reliant Sicap Baobab à Zone de Captage.", "arrets": ["Sicap Baobab", "Zone de Captage"]},
    {"numero_ligne": "Ligne 115", "nom_ligne": "Liberté 1 - Amitié", "description": "Minibus Tata reliant Liberté 1 à Amitié.", "arrets": ["Liberté 1", "Amitié"]},
    {"numero_ligne": "Ligne 116", "nom_ligne": "Dieuppeul - Derklé", "description": "Minibus Tata reliant Dieuppeul à Derklé.", "arrets": ["Dieuppeul", "Derklé"]},
    {"numero_ligne": "Ligne 117", "nom_ligne": "Grand Dakar - Castors", "description": "Minibus Tata reliant Grand Dakar à Castors.", "arrets": ["Grand Dakar", "Castors"]},
    {"numero_ligne": "Ligne 118", "nom_ligne": "Parcelles Assainies - Cambérène (direct)", "description": "Minibus Tata reliant Parcelles Assainies à Cambérène via Grand Médine.", "arrets": ["Parcelles Assainies", "Grand Médine", "Cambérène"]},
    {"numero_ligne": "Ligne 119", "nom_ligne": "Golf - Wakhinane", "description": "Minibus Tata reliant Golf à Wakhinane.", "arrets": ["Golf", "Wakhinane"]},
    {"numero_ligne": "Ligne 120", "nom_ligne": "Thiaroye - Djidah Thiaroye Kao", "description": "Minibus Tata reliant Thiaroye à Djidah Thiaroye Kao.", "arrets": ["Thiaroye", "Djidah Thiaroye Kao"]},
    {"numero_ligne": "Ligne 121", "nom_ligne": "Yeumbeul - Malika", "description": "Minibus Tata reliant Yeumbeul à Malika.", "arrets": ["Yeumbeul", "Malika"]},
    {"numero_ligne": "Ligne 122", "nom_ligne": "Keur Massar - Diacksao", "description": "Minibus Tata reliant Keur Massar à Diacksao.", "arrets": ["Keur Massar", "Diacksao"]},
    {"numero_ligne": "Ligne 123", "nom_ligne": "Rufisque Est - Diokoul", "description": "Minibus Tata reliant Rufisque Est à Diokoul.", "arrets": ["Rufisque Est", "Diokoul"]},
    {"numero_ligne": "Ligne 124", "nom_ligne": "Arafat - Rufisque Nord", "description": "Minibus Tata reliant Arafat à Rufisque Nord.", "arrets": ["Arafat", "Rufisque Nord"]},
    {"numero_ligne": "Ligne 125", "nom_ligne": "Bargny - Sangalkam", "description": "Minibus Tata reliant Bargny à Sangalkam.", "arrets": ["Bargny", "Sangalkam"]},
    {"numero_ligne": "Ligne 126", "nom_ligne": "Sébikotane - Bambilor", "description": "Minibus Tata reliant Sébikotane à Bambilor.", "arrets": ["Sébikotane", "Bambilor"]},
    {"numero_ligne": "Ligne 127", "nom_ligne": "Almadies - Corniche Ouest", "description": "Minibus Tata reliant Almadies à la Corniche Ouest.", "arrets": ["Almadies", "Corniche Ouest"]},
    {"numero_ligne": "Ligne 128", "nom_ligne": "Mermoz - Fenêtre Mermoz", "description": "Minibus Tata, liaison locale du secteur Mermoz.", "arrets": ["Mermoz", "Fenêtre Mermoz"]},
    {"numero_ligne": "Ligne 129", "nom_ligne": "Point E - Amitié", "description": "Minibus Tata reliant Point E à Amitié.", "arrets": ["Point E", "Amitié"]},
    {"numero_ligne": "Ligne 130", "nom_ligne": "Sacré-Cœur 3 - Liberté 6 Extension", "description": "Minibus Tata reliant Sacré-Cœur 3 à Liberté 6 Extension.", "arrets": ["Sacré-Cœur 3", "Liberté 6 Extension"]},
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
    """Retourne l'intégralité des lignes du réseau Minibus Tata —
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
#
# Liste recalée sur les axes réellement les plus empruntés de l'agglomération
# dakaroise, d'après le réseau AFTU/Tata (64 lignes, desserte Pikine/
# Guédiawaye/Rufisque), le tracé du BRT Petersen-Guédiawaye (~18 km, l'un des
# axes les plus denses de la ville) et les grands corridors identifiés par le
# CETUD dans ses plans de déplacements urbains : Route des Niayes (Pikine -
# Guédiawaye - Malika - Keur Massar), Route de Rufisque (Thiaroye - Rufisque
# - Bargny), VDN/Corniche Ouest (Ouakam - Ngor - Almadies - Yoff) et l'axe
# autoroutier TER Dakar - Diamniadio - AIBD. Sources : cetud.sn (Réseaux de
# transport, Plan de Mobilité Urbaine Durable), demdikk.sn, aftu-senegal.org.
TRAJETS_POPULAIRES = [
    # Voyageurs et touristes : l'aéroport AIBD vers le centre-ville et le
    # pôle universitaire (le TER dessert déjà Diamniadio sur cet axe)
    ("Aéroport AIBD", "Plateau"), ("Aéroport AIBD", "UCAD"),

    # Pôle étudiant : UCAD et les hubs qui y mènent au quotidien
    ("UCAD", "Plateau"), ("UCAD", "Yoff"), ("Petersen", "UCAD"),

    # Dakarois au quotidien : Plateau, Sandaga, Parcelles, Liberté 6
    ("Plateau", "Sandaga"), ("Sandaga", "Parcelles Assainies"), ("Liberté 6", "Yoff"),

    # Touristes et visiteurs : corniche ouest, Ngor, Almadies
    ("Ouakam", "Almadies"), ("Yoff", "Ngor"), ("Sacré-Cœur", "Mermoz"),

    # Grands axes structurants : le TER vers Diamniadio (via le pôle gare
    # de Dakar, à deux pas de Petersen) et le nouveau campus universitaire
    # de Diamniadio (Université Amadou Mahtar Mbow), plus l'hôpital de
    # référence de la ville
    ("Gare de Dakar", "Diamniadio"), ("Colobane", "Université Amadou Mahtar Mbow"),
    ("Hôpital Principal de Dakar", "Plateau"),
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