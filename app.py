"""
app.py
-------
Application Flask (Python) d'EasyMoveDakar.
Ce fichier fait le lien entre :
 - la base de données SQL (via database.py)
 - les pages HTML (templates Jinja2 dans /templates)

Pour lancer le site en local :
    pip install flask
    python app.py
Puis ouvrir http://127.0.0.1:5000 dans un navigateur.
"""

from flask import Flask, render_template, request, jsonify
from collections import OrderedDict
import database

app = Flask(__name__)

# Initialise la base de données au démarrage (crée le fichier .db si besoin)
database.init_db()


def get_stats():
    """Petits chiffres affichés sur la page d'accueil / à propos."""
    return {
        "transports": len(database.get_tous_les_transports()),
        "trajets": len(database.get_tous_les_trajets()),
        "phrases": len(database.get_toutes_les_phrases()),
        "conseils": len(database.get_tous_les_conseils()),
    }


def grouper_par(liste, cle):
    """Regroupe une liste de sqlite3.Row par une colonne donnée, en gardant l'ordre."""
    groupes = OrderedDict()
    for item in liste:
        valeur = item[cle]
        groupes.setdefault(valeur, []).append(item)
    return groupes


# ---------------------------------------------------------------------
# ROUTES - PAGES
# ---------------------------------------------------------------------

@app.route("/")
def accueil():
    transports = database.get_tous_les_transports()
    phrases = database.get_toutes_les_phrases()
    lieux = database.get_tous_les_lieux()
    return render_template(
        "index.html",
        transports_apercu=transports[:3],
        phrases_apercu=phrases[:3],
        lieux=lieux,
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
        trajets=database.get_tous_les_trajets(),
        lieux=database.get_tous_les_lieux(),
        active_page="trajets",
    )


@app.route("/trajets/resultat")
def resultat_trajet():
    id_depart = request.args.get("depart", type=int)
    id_arrivee = request.args.get("arrivee", type=int)

    resultat = None
    if id_depart and id_arrivee:
        data = database.rechercher_trajet(id_depart, id_arrivee)
        if data:
            if data["trouve"]:
                t = data["trajet"]
                resultat = {
                    "depart_nom": t["nom_depart"],
                    "depart_lat": t["lat_depart"],
                    "depart_lng": t["lng_depart"],
                    "arrivee_nom": t["nom_arrivee"],
                    "arrivee_lat": t["lat_arrivee"],
                    "arrivee_lng": t["lng_arrivee"],
                    "options": data["options"],
                }
            else:
                resultat = {
                    "depart_nom": data["depart"]["nom"],
                    "depart_lat": data["depart"]["latitude"],
                    "depart_lng": data["depart"]["longitude"],
                    "arrivee_nom": data["arrivee"]["nom"],
                    "arrivee_lat": data["arrivee"]["latitude"],
                    "arrivee_lng": data["arrivee"]["longitude"],
                    "options": [],
                }

    return render_template(
        "resultat_trajet.html",
        resultat=resultat,
        active_page="trajets",
    )


@app.route("/prix")
def prix():
    return render_template(
        "prix.html",
        transports=database.get_tous_les_transports(),
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
        infos_urgence=[i for i in infos if i["categorie"] == "Urgence"],
        infos_emporter=[i for i in infos if i["categorie"] == "À emporter"],
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


# ---------------------------------------------------------------------
# ROUTES - API (JSON) — utile pour aller plus loin (JS dynamique, mobile...)
# ---------------------------------------------------------------------

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


if __name__ == "__main__":
    app.run(debug=True)
