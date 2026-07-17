"""
import_tata.py
---------------
Script autonome d'import du réseau de lignes Minibus Tata (AFTU) dans la
base existante d'EasyMoveDakar.

Ne crée AUCUNE nouvelle base ni nouvelle table : il réutilise exactement le
schéma déjà en place (`lignes_bus`, `arrets`, `ligne_arrets`, `lieux`), le
même que celui que `database.py` alimente au démarrage de l'application.

Source des données (data/tata_lignes_import.json) : lignes réelles du
réseau AFTU sourcées via Moovit (moovitapp.com/index/en/public_transit-
lines-Dakar-5996-1618038), qui agrège des données réelles d'usage/tracé
pour 64 lignes AFTU à Dakar — vérifié le 16/07/2026. Contrairement aux
lignes déjà en dur dans database.py (best-effort, plausibles mais non
vérifiées), chaque ligne de ce fichier a été confirmée sur sa page Moovit
dédiée (numéro réel, terminus réels). Voir les commentaires "_a_lire" du
JSON pour le détail des lignes réelles volontairement exclues faute de
coordonnées vérifiées pour certains de leurs arrêts.

Utilisation :
    python import_tata.py [--fichier chemin/vers/lignes.json]
"""

import argparse
import json
import os
import sys

import database


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FICHIER_PAR_DEFAUT = os.path.join(BASE_DIR, "data", "tata_lignes_import.json")


def charger_lignes(chemin_fichier):
    """Charge et nettoie la liste de lignes à importer depuis le JSON.

    Nettoyage appliqué : suppression des espaces superflus, rejet des
    entrées sans numero_ligne ou avec moins de 2 arrêts, et dédoublonnage
    *au sein même du fichier* (si le même numero_ligne apparaît deux fois,
    seule la première occurrence est conservée)."""
    if not os.path.exists(chemin_fichier):
        print(f"Fichier introuvable : {chemin_fichier}")
        return []

    with open(chemin_fichier, "r", encoding="utf-8") as f:
        data = json.load(f)

    lignes_brutes = data.get("lignes", [])
    lignes_propres = []
    numeros_vus = set()

    for ligne in lignes_brutes:
        numero = (ligne.get("numero_ligne") or "").strip()
        if not numero:
            print("  ! Ligne ignorée (numero_ligne manquant)")
            continue
        if numero in numeros_vus:
            print(f"  ! Doublon ignoré dans le fichier source : {numero}")
            continue

        arrets = ligne.get("arrets") or []
        if len(arrets) < 2:
            print(f"  ! Ligne {numero} ignorée (moins de 2 arrêts)")
            continue

        numeros_vus.add(numero)
        lignes_propres.append({
            "numero_ligne": numero,
            "nom_ligne": (ligne.get("nom_ligne") or numero).strip(),
            "description": (ligne.get("description") or "").strip(),
            "arrets": arrets,
        })

    return lignes_propres


def _resoudre_ou_creer_lieu(cursor, arret):
    """Retourne (id_lieu, latitude, longitude) pour un arrêt donné.

    `arret` est soit une chaîne (nom d'un lieu déjà en base), soit un objet
    {"nom", "latitude", "longitude", "type_lieu"} : dans ce second cas, le
    lieu est créé s'il n'existe pas déjà — c'est ce qui permet au script
    d'intégrer une ligne réelle desservant un quartier pas encore
    référencé, sans avoir à passer par une autre partie du code."""
    if isinstance(arret, str):
        nom = arret.strip()
        lieu_row = cursor.execute(
            "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom,)
        ).fetchone()
        if not lieu_row:
            return None
        return lieu_row[0], lieu_row[1], lieu_row[2]

    nom = (arret.get("nom") or "").strip()
    if not nom:
        return None

    lieu_row = cursor.execute(
        "SELECT id_lieu, latitude, longitude FROM lieux WHERE nom = ?", (nom,)
    ).fetchone()
    if lieu_row:
        return lieu_row[0], lieu_row[1], lieu_row[2]

    latitude = arret.get("latitude")
    longitude = arret.get("longitude")
    if latitude is None or longitude is None:
        print(f"  ! Lieu '{nom}' introuvable et sans coordonnées fournies : arrêt ignoré")
        return None

    type_lieu = arret.get("type_lieu", "quartier")
    cursor.execute(
        "INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES (?, ?, ?, ?, ?)",
        (nom, type_lieu, latitude, longitude, arret.get("description", ""))
    )
    return cursor.lastrowid, latitude, longitude


def importer(lignes, connexion=None):
    """Insère les lignes dans la base existante (idempotent : une ligne
    dont le numero_ligne existe déjà est ignorée, jamais dupliquée).

    Retourne un résumé {lignes_importees, lignes_deja_presentes,
    arrets_ajoutes, trajets_crees, lignes_incompletes}."""
    conn = connexion or database.get_connection()
    cursor = conn.cursor()

    ligne_transport = cursor.execute(
        "SELECT id_transport FROM moyens_transport WHERE nom LIKE 'Minibus Tata%'"
    ).fetchone()
    if not ligne_transport:
        print("Transport 'Minibus Tata (AFTU)' introuvable en base — import annulé.")
        if not connexion:
            conn.close()
        return {"lignes_importees": 0, "lignes_deja_presentes": 0, "arrets_ajoutes": 0, "trajets_crees": 0, "lignes_incompletes": 0}
    id_transport_tata = ligne_transport[0]

    lignes_importees = 0
    lignes_deja_presentes = 0
    lignes_incompletes = 0
    arrets_ajoutes = 0
    trajets_crees = 0

    for ligne in lignes:
        existe = cursor.execute(
            "SELECT 1 FROM lignes_bus WHERE numero_ligne = ?", (ligne["numero_ligne"],)
        ).fetchone()
        if existe:
            lignes_deja_presentes += 1
            print(f"  = {ligne['numero_ligne']} déjà présente en base, ignorée")
            continue

        cursor.execute(
            "INSERT INTO lignes_bus (numero_ligne, nom_ligne, id_transport, est_minibus, description) "
            "VALUES (?, ?, ?, 1, ?)",
            (ligne["numero_ligne"], ligne["nom_ligne"], id_transport_tata, ligne["description"])
        )
        id_ligne = cursor.lastrowid

        arrets_ok = 0
        for ordre, arret in enumerate(ligne["arrets"], start=1):
            resultat = _resoudre_ou_creer_lieu(cursor, arret)
            if not resultat:
                continue
            id_lieu, lat, lng = resultat
            nom_affiche = arret if isinstance(arret, str) else arret.get("nom", "")

            cursor.execute(
                "INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES (?, ?, ?, ?)",
                (f"Arrêt {nom_affiche} ({ligne['numero_ligne']})", id_lieu, lat, lng)
            )
            id_arret = cursor.lastrowid
            cursor.execute(
                "INSERT INTO ligne_arrets (id_ligne, id_arret, ordre) VALUES (?, ?, ?)",
                (id_ligne, id_arret, ordre)
            )
            arrets_ajoutes += 1
            trajets_crees += 1
            arrets_ok += 1

        if arrets_ok < 2:
            # Moins de 2 arrêts résolus : la ligne est inexploitable pour le
            # calcul d'itinéraire. On la retire plutôt que de la laisser
            # traîner en base à moitié vide.
            cursor.execute("DELETE FROM ligne_arrets WHERE id_ligne = ?", (id_ligne,))
            cursor.execute("DELETE FROM lignes_bus WHERE id_ligne = ?", (id_ligne,))
            lignes_incompletes += 1
            print(f"  ! {ligne['numero_ligne']} retirée (moins de 2 arrêts résolus en base)")
            continue

        lignes_importees += 1
        print(f"  + {ligne['numero_ligne']} importée ({arrets_ok} arrêts)")

    conn.commit()
    if not connexion:
        conn.close()

    return {
        "lignes_importees": lignes_importees,
        "lignes_deja_presentes": lignes_deja_presentes,
        "arrets_ajoutes": arrets_ajoutes,
        "trajets_crees": trajets_crees,
        "lignes_incompletes": lignes_incompletes,
    }


def compter_lignes_tata_en_base():
    conn = database.get_connection()
    n = conn.execute("""
        SELECT COUNT(*) AS n FROM lignes_bus lb
        JOIN moyens_transport mt ON mt.id_transport = lb.id_transport
        WHERE mt.nom LIKE 'Minibus Tata%'
    """).fetchone()["n"]
    conn.close()
    return n


def main():
    parser = argparse.ArgumentParser(description="Importe des lignes Minibus Tata (AFTU) dans la base EasyMoveDakar existante.")
    parser.add_argument("--fichier", default=FICHIER_PAR_DEFAUT, help="Chemin du fichier JSON source (voir data/tata_lignes_import.json)")
    args = parser.parse_args()

    # S'assure que le schéma existe déjà (ne recrée rien s'il est déjà là :
    # CREATE TABLE IF NOT EXISTS partout dans database.init_db()).
    database.init_db()

    print(f"Lecture de {args.fichier}...")
    lignes = charger_lignes(args.fichier)
    print(f"{len(lignes)} ligne(s) valide(s) trouvée(s) dans le fichier source.\n")

    resultat = importer(lignes)

    print("\n--- Résumé de l'import ---")
    print(f"{resultat['lignes_importees']} lignes Tata importées")
    print(f"Nombre d'arrêts ajoutés : {resultat['arrets_ajoutes']}")
    print(f"Nombre de trajets créés : {resultat['trajets_crees']}")
    if resultat["lignes_deja_presentes"]:
        print(f"({resultat['lignes_deja_presentes']} ligne(s) déjà en base, ignorée(s) — pas de doublon créé)")
    if resultat["lignes_incompletes"]:
        print(f"({resultat['lignes_incompletes']} ligne(s) écartée(s), arrêts non résolus)")

    print(f"\nRéseau Tata total en base après import : {compter_lignes_tata_en_base()} lignes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
