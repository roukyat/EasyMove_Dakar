"""
app.py
-------
Application Flask (Python) d'EasyMoveDakar.
Fait le pont entre la base SQLite (database.py) et les templates Jinja2.
"""

from flask import Flask, render_template, request, jsonify
from collections import OrderedDict
import math
import database

app = Flask(__name__)

# Initialise la base de données au démarrage 
database.init_db()


def get_stats():
    """Chiffres clés affichés sur l'interface d'administration, l'accueil et à propos."""
    lignes = database.get_toutes_les_lignes_bus()
    return {
        "transports": len(database.get_tous_les_transports()),
        "trajets": len(database.get_tous_les_trajets()),
        "phrases": len(database.get_toutes_les_phrases()),
        "conseils": len(database.get_tous_les_conseils()),
        "lignes": len(lignes),
        "lignes_tata": len([l for l in lignes if l["est_minibus"]]),
        "arrets": database.get_nombre_arrets(),
        "lieux": database.get_nombre_lieux(),
    }


def grouper_par(liste, cle):
    """Regroupe une liste d'éléments par clé en conservant l'ordre."""
    groupes = OrderedDict()
    for item in liste:
        valeur = item[cle]
        groupes.setdefault(valeur, []).append(item)
    return groupes


def calculer_haversine(lat1, lon1, lat2, lon2):
    """Calcule la distance en kilomètres entre deux coordonnées géographiques."""
    R = 6371.0  # Rayon de la Terre en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_niveau_prix(cout_min, cout_max):
    """Classe un moyen de transport en Économique / Moyen / Cher à partir de
    son prix moyen estimé (plutôt que du seul prix plancher, qui écraserait
    des transports au tarif très variable comme le Taxi). Seuils calibrés
    sur les tarifs réels du site : Tata/BRT/DDD/Car rapide/Clando restent
    "Économique", le TER est "Moyen", Taxi et Jakarta sont "Cher"."""
    moyenne = (cout_min + cout_max) / 2
    if moyenne <= 500:
        return {"label": "Économique", "classe": "badge-vert"}
    elif moyenne <= 2000:
        return {"label": "Moyen", "classe": "badge-jaune"}
    return {"label": "Cher", "classe": "badge-rouge"}


# ---------------------------------------------------------------------
# ROUTES 
# ---------------------------------------------------------------------

# Les 3 moyens de transport mis en avant sur l'accueil : les plus utilisés
# au quotidien par les Dakarois (flexibilité porte-à-porte du taxi et du
# clando, densité du réseau Tata), plutôt qu'une liste exhaustive qui
# n'aiderait pas à se décider rapidement.
TRANSPORTS_POPULAIRES = ["Taxi", "Clando", "Minibus Tata (AFTU)"]


@app.route("/")
def accueil():
    transports = database.get_tous_les_transports()
    transports_par_nom = {t["nom"]: t for t in transports}
    top_transports = [transports_par_nom[nom] for nom in TRANSPORTS_POPULAIRES if nom in transports_par_nom]

    phrases = database.get_toutes_les_phrases()
    lieux = database.get_tous_les_lieux()
    historique = database.get_historique_recent(limite=3)

    # Prise en compte du nom réel de votre index ('index.html' ou 'accueil.html')
    return render_template(
        "index.html",
        top_transports=top_transports,
        phrases_apercu=phrases[:3],
        lieux=lieux,
        historique_apercu=historique,
        stats=get_stats(),
        active_page="accueil",
    )


@app.route("/transports")
def transports():
    return render_template(
        "transports.html",
        transports=database.get_tous_les_transports(),
        active_page="transports",
    )


@app.route("/trajets")
def trajets():
    return render_template(
        "trajets.html",
        lieux=database.get_tous_les_lieux(),
        favoris=database.get_tous_les_favoris(),
        active_page="trajets",
    )


@app.route("/trajets/resultat")
def resultat_trajet():
    id_depart = request.args.get("depart", type=int)
    id_arrivee = request.args.get("arrivee", type=int)

    resultat = None
    if id_depart and id_arrivee:
        # Le moteur d'itinéraire (itineraire.py) calcule désormais la route à la
        # volée pour n'importe quelle paire de lieux : bus/Tata/BRT/TER avec
        # correspondances plus Taxi/Jakarta toujours disponibles en secours.
        data = database.rechercher_trajet(id_depart, id_arrivee)
        if data and data["trouve"]:
            t = data["trajet"]
            resultat = {
                "id_lieu_depart": t["id_lieu_depart"],
                "id_lieu_arrivee": t["id_lieu_arrivee"],
                "depart_nom": t["nom_depart"],
                "depart_lat": t["lat_depart"],
                "depart_lng": t["lng_depart"],
                "arrivee_nom": t["nom_arrivee"],
                "arrivee_lat": t["lat_arrivee"],
                "arrivee_lng": t["lng_arrivee"],
                "distance_km": t["distance_km"],
                "niveau_difficulte": t["niveau_difficulte"],
                "options": data["options"],
                "est_favori": database.favori_existe(t["id_lieu_depart"], t["id_lieu_arrivee"]),
            }

    return render_template(
        "resultat_trajet.html",
        resultat=resultat,
        active_page="trajets",
    )


@app.route("/minibus")
def minibus():
    """Page de référence du réseau Tata (AFTU) : l'ensemble des lignes
    disponibles à Dakar, quartier par quartier."""
    lignes = database.get_toutes_les_lignes_tata()

    lignes_avec_arrets = []
    tous_les_arrets = []

    for ligne in lignes:
        arrets = database.get_arrets_par_ligne(ligne["id_ligne"])
        arrets_dicts = [dict(a) for a in arrets]

        # Envoi des arrêts identifiés à la collection globale pour traitement cartographique
        for a in arrets_dicts:
            a["numero_ligne"] = ligne["numero_ligne"]
            tous_les_arrets.append(a)

        lignes_avec_arrets.append({"info": ligne, "arrets": arrets})

    return render_template(
        "minibus.html",
        lignes_minibus=lignes_avec_arrets,
        tous_les_arrets=tous_les_arrets,
        active_page="minibus"
    )


@app.route("/historique")
def historique():
    """Page dédiée affichant l'historique complet des requêtes de l'utilisateur."""
    return render_template(
        "historique.html",
        historique=database.get_historique_recent(limite=50),
        active_page="historique"
    )


@app.route("/prix")
def prix():
    # Conversion en dict pour pouvoir greffer le badge de niveau de prix
    # (Économique/Moyen/Cher) sans modifier le schéma de la base.
    transports = [dict(t) for t in database.get_tous_les_transports()]
    for t in transports:
        t["niveau_prix"] = get_niveau_prix(t["cout_min"], t["cout_max"])

    return render_template(
        "prix.html",
        transports=transports,
        trajets=database.get_tous_les_trajets(),
        active_page="prix",
    )


@app.route("/conseils")
def conseils():
    tous_conseils = database.get_tous_les_conseils()
    infos = database.get_infos_utiles()

    return render_template(
        "conseils.html",
        conseils_par_categorie=grouper_par(tous_conseils, "categorie"),
        infos_urgence=[dict(i) for i in infos if i["categorie"] == "Urgence"],
        active_page="conseils",
    )


@app.route("/wolof")
def wolof():
    phrases = database.get_toutes_les_phrases()
    return render_template(
        "wolof.html",
        phrases=phrases,
        phrases_par_situation=grouper_par(phrases, "situation"),
        active_page="wolof",
    )


@app.route("/contact")
def contact():
    return render_template(
        "contact.html",
        stats=get_stats(),
        active_page="contact",
    )


@app.route("/apropos")
def apropos():
    return render_template(
        "apropos.html",
        stats=get_stats(),
        active_page="apropos",
    )


# ---------------------------------------------------------------------
# ROUTES - API (JSON)
# ---------------------------------------------------------------------

@app.route("/api/arrets_proches")
def api_arrets_proches():
    """Retourne les 5 arrêts les plus proches parmi l'ensemble du réseau
    Tata, selon une latitude et longitude données."""
    try:
        user_lat = request.args.get("lat", type=float)
        user_lng = request.args.get("lng", type=float)
    except (TypeError, ValueError):
        return jsonify({"erreur": "Coordonnées GPS manquantes ou invalides"}), 400

    if user_lat is None or user_lng is None:
        return jsonify({"erreur": "Paramètres 'lat' et 'lng' requis"}), 400

    lignes_minibus = database.get_toutes_les_lignes_tata()
    tous_arrets = []

    for ligne in lignes_minibus:
        arrets = database.get_arrets_par_ligne(ligne["id_ligne"])
        for a in arrets:
            dist = calculer_haversine(user_lat, user_lng, a["latitude"], a["longitude"])
            tous_arrets.append({
                "id_arret": a["id_arret"],
                "nom": a["nom"],
                "latitude": a["latitude"],
                "longitude": a["longitude"],
                "numero_ligne": ligne["numero_ligne"],
                "distance": round(dist, 2)
            })

    # Trier par distance  et renvoyer les 5 premiers
    tous_arrets.sort(key=lambda x: x["distance"])
    return jsonify(tous_arrets[:5])


@app.route("/api/lieux")
def api_lieux():
    lieux = database.get_tous_les_lieux()
    return jsonify([dict(l) for l in lieux])


@app.route("/api/rechercher-trajet")
def api_rechercher_trajet():
    id_depart = request.args.get("depart", type=int)
    id_arrivee = request.args.get("arrivee", type=int)
    if not id_depart or not id_arrivee:
        return jsonify({"erreur": "Paramètres 'depart' et 'arrivee' requis"}), 400

    resultat = database.rechercher_trajet(id_depart, id_arrivee)
    if resultat is None:
        return jsonify({"erreur": "Lieu introuvable"}), 404

    return jsonify(resultat)


@app.route("/api/minibus/arrets")
def api_minibus_arrets():
    id_ligne = request.args.get("id_ligne", type=int)
    if not id_ligne:
        return jsonify({"erreur": "Le paramètre id_ligne est requis"}), 400
    arrets = database.get_arrets_par_ligne(id_ligne)
    return jsonify([dict(a) for a in arrets])


@app.route("/api/favoris", methods=["POST"])
def api_ajouter_favori():
    data = request.get_json()
    if not data:
        return jsonify({"erreur": "Aucune donnée reçue"}), 400

    nom_trajet = data.get("nom_trajet")

    # On accepte indifféremment id_lieu_depart ou id_depart
    id_depart = data.get("id_lieu_depart") or data.get("id_depart")
    id_arrivee = data.get("id_lieu_arrivee") or data.get("id_arrivee")

    # Vérification stricte
    if not nom_trajet or not id_depart or not id_arrivee:
        return jsonify({"erreur": "Données incomplètes"}), 400

    if database.favori_existe(id_depart, id_arrivee):
        return jsonify({"statut": "existe_deja", "message": "Ce trajet est déjà dans vos favoris."})

    database.ajouter_favori(nom_trajet, id_depart, id_arrivee)

    return jsonify({"statut": "success", "message": "Favori ajouté !"})


@app.route("/api/favoris/<int:id_favori>", methods=["DELETE"])
def api_supprimer_favori(id_favori):
    database.supprimer_favori(id_favori)
    return jsonify({"statut": "success", "message": "Favori supprimé."})


@app.route("/api/historique", methods=["DELETE"])
def api_vider_historique():
    """Vide entièrement l'historique de recherches (bouton "Vider
    l'historique", avec confirmation côté client avant l'appel)."""
    database.vider_historique()
    return jsonify({"statut": "success", "message": "Historique vidé."})


if __name__ == "__main__":
    app.run(debug=True)