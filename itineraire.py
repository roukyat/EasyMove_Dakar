"""
itineraire.py
--------------
Moteur de calcul d'itinéraires : construit un graphe (arrêts + lignes +
correspondances à pied) à partir de la base, puis calcule le meilleur
chemin avec Dijkstra. Taxi et Jakarta restent toujours proposés en plus,
calculés à vol d'oiseau, même sans ligne de bus disponible.
"""

import math
import heapq
from collections import defaultdict

# Constantes du modèle (vitesses, tarifs...), approximatives pour Dakar.
VITESSE_BUS_KMH = 16.0        # vitesse commerciale moyenne (trafic dakarois)
VITESSE_MARCHE_KMH = 4.5
TEMPS_ARRET_MIN = 1.0         # temps perdu à chaque arrêt intermédiaire
TEMPS_CORRESPONDANCE_MIN = 5.0  # attente moyenne lors d'un changement de ligne
RAYON_CORRESPONDANCE_KM = 0.6   # distance max à pied considérée comme "même pôle"

# Taxi officiel (jaune et noir), prix négocié avec le chauffeur.
TAXI_BASE = 500
TAXI_PAR_KM_MIN = 120
TAXI_PAR_KM_MAX = 220
TAXI_VITESSE_KMH = 20.0

# Clando : voiture partagée, tarif par personne proche du car rapide.
CLANDO_BASE = 100
CLANDO_PAR_KM_MIN = 40
CLANDO_PAR_KM_MAX = 90
CLANDO_VITESSE_KMH = 18.0

JAKARTA_BASE = 300
JAKARTA_PAR_KM_MIN = 80
JAKARTA_PAR_KM_MAX = 150
JAKARTA_VITESSE_KMH = 26.0

# Ndiaga Ndiaye : pas de ligne fixe, mais un tarif estimable (100-350 FCFA en ville).
NDIAGA_NDIAYE_BASE = 100
NDIAGA_NDIAYE_PAR_KM_MIN = 30
NDIAGA_NDIAYE_PAR_KM_MAX = 70
NDIAGA_NDIAYE_VITESSE_KMH = 17.0

SEUIL_MARCHE_A_PIED_KM = 1.0  # en dessous, on propose aussi "à pied"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _arrondi_prix(x, base=50):
    return int(round(x / base) * base)


# Les tarifs de base (cout_min/cout_max) sont pour un trajet court (~3 km),
# donc on les fait grimper avec la distance, jusqu'à un plafond réaliste.
MINIBUS_REF_KM = 3.0
MINIBUS_RATE_MIN_PAR_KM = 12
MINIBUS_RATE_MAX_PAR_KM = 22
MINIBUS_PLAFOND_MIN = 450
MINIBUS_PLAFOND_MAX = 700


def _tarif_echelle_minibus(cout_min, cout_max, distance_km):
    supplement_km = max(0.0, distance_km - MINIBUS_REF_KM)
    tarif_min = min(MINIBUS_PLAFOND_MIN, _arrondi_prix(cout_min + supplement_km * MINIBUS_RATE_MIN_PAR_KM))
    tarif_max = min(MINIBUS_PLAFOND_MAX, _arrondi_prix(cout_max + supplement_km * MINIBUS_RATE_MAX_PAR_KM))
    return max(tarif_min, cout_min), max(tarif_max, cout_max)


# Construction du graphe

class Graphe:
    def __init__(self, conn):
        self.conn = conn
        self.arrets = {}       # id_arret -> dict(nom, id_lieu, lat, lon)
        self.arrets_par_lieu = defaultdict(list)  # id_lieu -> [id_arret,...]
        # adjacence : id_arret -> liste de (id_voisin, poids_min, type, meta)
        #   type = 'ligne'  -> meta = dict(id_ligne, numero_ligne, nom_ligne, id_transport)
        #   type = 'marche' -> meta = dict(distance_km)
        self.adj = defaultdict(list)
        self._charger()

    def _charger(self):
        conn = self.conn
        for a in conn.execute("SELECT id_arret, nom, id_lieu, latitude, longitude FROM arrets"):
            self.arrets[a["id_arret"]] = {
                "nom": a["nom"], "id_lieu": a["id_lieu"],
                "lat": a["latitude"], "lon": a["longitude"],
            }
            if a["id_lieu"] is not None:
                self.arrets_par_lieu[a["id_lieu"]].append(a["id_arret"])

        # --- arêtes "ligne" : arrêts consécutifs d'une même ligne, dans les 2 sens ---
        lignes_info = {
            l["id_ligne"]: dict(l)
            for l in conn.execute("""
                SELECT lb.id_ligne, lb.numero_ligne, lb.nom_ligne, lb.id_transport, lb.est_minibus,
                       mt.nom AS nom_transport, mt.image_url, mt.cout_min, mt.cout_max
                FROM lignes_bus lb JOIN moyens_transport mt ON lb.id_transport = mt.id_transport
            """)
        }

        # Infos des transports sans ligne fixe (Taxi, Clando, Jakarta...).
        self.transports_meta = {
            row["nom"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM moyens_transport WHERE nom IN "
                "('Taxi', 'Clando', 'Jakarta (moto-taxi)', 'Ndiaga Ndiaye')"
            )
        }

        # Transports qui ont au moins une ligne dans le graphe (pour
        # calculer une alternative par mode, voir calculer_itineraire).
        self.transports_routables = {
            info["id_transport"]: info["nom_transport"]
            for info in lignes_info.values()
        }

        par_ligne = defaultdict(list)
        for la in conn.execute("SELECT id_ligne, id_arret, ordre FROM ligne_arrets ORDER BY id_ligne, ordre"):
            par_ligne[la["id_ligne"]].append(la["id_arret"])

        for id_ligne, sequence in par_ligne.items():
            info = lignes_info.get(id_ligne)
            if not info:
                continue
            for i in range(len(sequence) - 1):
                a1, a2 = sequence[i], sequence[i + 1]
                if a1 not in self.arrets or a2 not in self.arrets:
                    continue
                d = haversine_km(self.arrets[a1]["lat"], self.arrets[a1]["lon"],
                                  self.arrets[a2]["lat"], self.arrets[a2]["lon"])
                poids = (d / VITESSE_BUS_KMH) * 60 + TEMPS_ARRET_MIN
                meta = {
                    "id_ligne": id_ligne, "numero_ligne": info["numero_ligne"],
                    "nom_ligne": info["nom_ligne"], "id_transport": info["id_transport"],
                    "nom_transport": info["nom_transport"], "image_url": info["image_url"],
                    "cout_min": info["cout_min"], "cout_max": info["cout_max"],
                    "distance_km": d, "est_minibus": bool(info["est_minibus"]),
                }
                self.adj[a1].append((a2, poids, "ligne", meta))
                self.adj[a2].append((a1, poids, "ligne", meta))

        # --- arêtes "marche" : arrêts proches (correspondance à pied) ---
        ids = list(self.arrets.keys())
        for i, a1 in enumerate(ids):
            for a2 in ids[i + 1:]:
                p1, p2 = self.arrets[a1], self.arrets[a2]
                d = haversine_km(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
                if d <= RAYON_CORRESPONDANCE_KM:
                    poids = (d / VITESSE_MARCHE_KMH) * 60 + (TEMPS_CORRESPONDANCE_MIN if d > 0.05 else 0.5)
                    meta = {"distance_km": d}
                    self.adj[a1].append((a2, poids, "marche", meta))
                    self.adj[a2].append((a1, poids, "marche", meta))

    def arrets_du_lieu(self, id_lieu):
        return self.arrets_par_lieu.get(id_lieu, [])


# Dijkstra multi-source / multi-destination

def _dijkstra(graphe, sources, cibles):
    """Chemin le plus court entre plusieurs départs et arrivées possibles."""
    dist = {s: 0.0 for s in sources}
    pred = {}
    visited = set()
    heap = [(0.0, s) for s in sources]
    heapq.heapify(heap)
    cibles_set = set(cibles)
    meilleure_cible, meilleure_dist = None, math.inf

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u in cibles_set and d < meilleure_dist:
            meilleure_cible, meilleure_dist = u, d
            break  # Dijkstra: la première cible dépilée est optimale
        for v, poids, typ, meta in graphe.adj[u]:
            nd = d + poids
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                pred[v] = (u, typ, meta)
                heapq.heappush(heap, (nd, v))

    return meilleure_cible, meilleure_dist, pred


def _dijkstra_filtre(graphe, sources, cibles, filtre_ligne):
    """Même chose que _dijkstra, mais limité aux lignes qui passent le filtre."""
    dist = {s: 0.0 for s in sources}
    pred = {}
    visited = set()
    heap = [(0.0, s) for s in sources]
    heapq.heapify(heap)
    cibles_set = set(cibles)
    meilleure_cible, meilleure_dist = None, math.inf

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u in cibles_set and d < meilleure_dist:
            meilleure_cible, meilleure_dist = u, d
            break
        for v, poids, typ, meta in graphe.adj[u]:
            if typ == "ligne" and not filtre_ligne(meta):
                continue
            nd = d + poids
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                pred[v] = (u, typ, meta)
                heapq.heappush(heap, (nd, v))

    return meilleure_cible, meilleure_dist, pred


def _reconstruire_chemin(pred, sources, cible):
    if cible in sources:
        return []
    chemin = []
    cur = cible
    while cur in pred:
        prev, typ, meta = pred[cur]
        chemin.append((prev, cur, typ, meta))
        cur = prev
    chemin.reverse()
    return chemin


def _grouper_en_etapes(graphe, chemin):
    """Regroupe le chemin en étapes : une ligne prise en continu = 1 étape."""
    legs = []
    cur = None
    for (a1, a2, typ, meta) in chemin:
        if typ == "ligne":
            if cur and cur["type"] == "ligne" and cur["id_ligne"] == meta["id_ligne"]:
                cur["arrivee"] = a2
                cur["distance_km"] += meta["distance_km"]
                cur["duree_min"] += (meta["distance_km"] / VITESSE_BUS_KMH) * 60 + TEMPS_ARRET_MIN
            else:
                if cur:
                    legs.append(cur)
                cur = {
                    "type": "ligne", "id_ligne": meta["id_ligne"],
                    "numero_ligne": meta["numero_ligne"], "nom_ligne": meta["nom_ligne"],
                    "id_transport": meta["id_transport"], "nom_transport": meta["nom_transport"],
                    "image_url": meta["image_url"], "cout_min": meta["cout_min"], "cout_max": meta["cout_max"],
                    "est_minibus": bool(meta.get("est_minibus")),
                    "depart": a1, "arrivee": a2,
                    "distance_km": meta["distance_km"],
                    "duree_min": (meta["distance_km"] / VITESSE_BUS_KMH) * 60 + TEMPS_ARRET_MIN,
                }
        else:  # marche
            if cur and cur["type"] == "marche":
                cur["arrivee"] = a2
                cur["distance_km"] += meta["distance_km"]
                cur["duree_min"] += (meta["distance_km"] / VITESSE_MARCHE_KMH) * 60
            else:
                if cur:
                    legs.append(cur)
                cur = {
                    "type": "marche", "depart": a1, "arrivee": a2,
                    "distance_km": meta["distance_km"],
                    "duree_min": (meta["distance_km"] / VITESSE_MARCHE_KMH) * 60,
                }
    if cur:
        legs.append(cur)
    return legs


def _formatter_option_transit(graphe, legs, cible_finale_nom=None):
    """Transforme les étapes en une option de trajet prête à afficher."""
    etapes = []
    prix_min = prix_max = 0
    duree_min = duree_max = 0
    lignes_utilisees = []
    transports_utilises = []
    nb_correspondances = 0
    premiere_ligne_meta = None
    derniere_id_ligne = None

    legs_lignes = [l for l in legs if l["type"] == "ligne"]

    for i, leg in enumerate(legs):
        arret_dep = graphe.arrets[leg["depart"]]["nom"]
        arret_arr = graphe.arrets[leg["arrivee"]]["nom"]
        if leg["type"] == "marche":
            dist_m = int(round(leg["distance_km"] * 1000))
            if dist_m <= 50:
                continue
            etapes.append(f"Marcher jusqu'à « {arret_arr} » (~{dist_m} m)")
            duree_min += leg["duree_min"] * 0.85
            duree_max += leg["duree_min"] * 1.3
        else:
            if premiere_ligne_meta is None:
                premiere_ligne_meta = leg
            lignes_utilisees.append(leg["numero_ligne"])
            if leg["nom_transport"] not in transports_utilises:
                transports_utilises.append(leg["nom_transport"])
            verbe = "Prendre" if not etapes or "Prendre" not in etapes[-1] else "Continuer avec"
            etapes.append(
                f"{verbe} la {leg['numero_ligne']} ({leg['nom_transport']}) à « {arret_dep} » "
                f"et descendre à « {arret_arr} »"
            )
            if leg.get("est_minibus"):
                leg_cout_min, leg_cout_max = _tarif_echelle_minibus(leg["cout_min"], leg["cout_max"], leg["distance_km"])
            else:
                leg_cout_min, leg_cout_max = leg["cout_min"], leg["cout_max"]
            prix_min += leg_cout_min
            prix_max += leg_cout_max
            duree_min += leg["duree_min"] * 0.85
            duree_max += leg["duree_min"] * 1.35
            # Compte une correspondance dès que la ligne change, même si le
            # petit bout de marche entre les deux n'était pas affiché.
            if derniere_id_ligne is not None and derniere_id_ligne != leg["id_ligne"]:
                nb_correspondances += 1
            derniere_id_ligne = leg["id_ligne"]

    if not legs_lignes:
        return None

    if nb_correspondances == 0:
        correspondances_txt = "Aucune"
    else:
        correspondances_txt = f"{nb_correspondances} correspondance" + ("s" if nb_correspondances > 1 else "")

    nom_transport = " + ".join(transports_utilises)
    numero_ligne = " puis ".join(dict.fromkeys(lignes_utilisees))

    # Arrêt de départ de la 1ère ligne, utile pour situer l'embarquement sur la carte.
    embarquement_nom = embarquement_lat = embarquement_lng = None
    if premiere_ligne_meta:
        arret_embarquement = graphe.arrets[premiere_ligne_meta["depart"]]
        embarquement_nom = arret_embarquement["nom"]
        embarquement_lat = arret_embarquement["lat"]
        embarquement_lng = arret_embarquement["lon"]

    return {
        "nom_transport": nom_transport,
        "image_url": premiere_ligne_meta["image_url"] if premiere_ligne_meta else "",
        "id_transport": premiere_ligne_meta["id_transport"] if premiere_ligne_meta else None,
        "numero_ligne": numero_ligne,
        "nom_ligne": premiere_ligne_meta["nom_ligne"] if premiere_ligne_meta else "",
        "prix_min": prix_min, "prix_max": prix_max,
        "duree_min_minutes": max(1, int(round(duree_min))),
        "duree_max_minutes": max(1, int(round(duree_max))),
        "correspondances": correspondances_txt,
        "etapes": " | ".join(etapes),
        "recommande": 0,
        "nb_correspondances": nb_correspondances,
        "embarquement_nom": embarquement_nom,
        "embarquement_lat": embarquement_lat,
        "embarquement_lng": embarquement_lng,
    }


def _option_taxi(distance_km, meta=None):
    """Course privée, prix négocié avec le chauffeur pour tout le véhicule."""
    meta = meta or {}
    duree = distance_km / TAXI_VITESSE_KMH * 60 + 6
    prix_min = _arrondi_prix(TAXI_BASE + distance_km * TAXI_PAR_KM_MIN)
    prix_max = _arrondi_prix(TAXI_BASE + distance_km * TAXI_PAR_KM_MAX)
    return {
        "nom_transport": "Taxi",
        "image_url": meta.get("image_url") or "/static/img/taxi.jpg",
        "id_transport": meta.get("id_transport"),
        "numero_ligne": "", "nom_ligne": "",
        "prix_min": prix_min, "prix_max": max(prix_max, prix_min + 200),
        "duree_min_minutes": max(3, int(round(duree * 0.8))),
        "duree_max_minutes": max(5, int(round(duree * 1.3))),
        "correspondances": "Aucune",
        "etapes": f"Héler un taxi officiel (jaune et noir) et négocier le prix de la course avant de monter | Trajet direct de {distance_km:.1f} km",
        "recommande": 0,
    }


def _option_clando(distance_km, meta=None):
    """Clando : pas de tarif fixe, le prix se négocie sur place avec le
    chauffeur. On garde quand même un ordre de prix (_prix_score) en
    interne pour le classement, sans jamais l'afficher à l'utilisateur."""
    meta = meta or {}
    duree = distance_km / CLANDO_VITESSE_KMH * 60 + 5
    prix_score_min = _arrondi_prix(CLANDO_BASE + distance_km * CLANDO_PAR_KM_MIN)
    prix_score_max = _arrondi_prix(CLANDO_BASE + distance_km * CLANDO_PAR_KM_MAX)
    return {
        "nom_transport": "Clando",
        "image_url": meta.get("image_url") or "/static/img/clando.jpg",
        "id_transport": meta.get("id_transport"),
        "numero_ligne": "", "nom_ligne": "",
        "prix_min": None, "prix_max": None,
        "prix_libre": True,
        "_prix_score": (prix_score_min + prix_score_max) / 2,
        "duree_min_minutes": max(3, int(round(duree * 0.85))),
        "duree_max_minutes": max(5, int(round(duree * 1.35))),
        "correspondances": "Aucune",
        "etapes": "Héler un clando à un point de rassemblement informel | Prix fixé directement avec le chauffeur",
        "recommande": 0,
    }


def _option_jakarta(distance_km, meta=None):
    meta = meta or {}
    duree = distance_km / JAKARTA_VITESSE_KMH * 60 + 3
    prix_min = _arrondi_prix(JAKARTA_BASE + distance_km * JAKARTA_PAR_KM_MIN)
    prix_max = _arrondi_prix(JAKARTA_BASE + distance_km * JAKARTA_PAR_KM_MAX)
    return {
        "nom_transport": "Jakarta (moto-taxi)",
        "image_url": meta.get("image_url") or "",
        "id_transport": meta.get("id_transport"),
        "numero_ligne": "", "nom_ligne": "",
        "prix_min": prix_min, "prix_max": max(prix_max, prix_min + 100),
        "duree_min_minutes": max(2, int(round(duree * 0.75))),
        "duree_max_minutes": max(4, int(round(duree * 1.2))),
        "correspondances": "Aucune",
        "etapes": f"Héler un Jakarta (moto-taxi) et négocier le prix | Idéal en cas d'embouteillages ({distance_km:.1f} km)",
        "recommande": 0,
    }


def _option_ndiaga_ndiaye(distance_km, meta=None):
    """Ndiaga Ndiaye : pas de ligne fixe en base, toujours proposé en option,
    comme Taxi/Clando/Jakarta."""
    meta = meta or {}
    duree = distance_km / NDIAGA_NDIAYE_VITESSE_KMH * 60 + 5
    prix_min = _arrondi_prix(NDIAGA_NDIAYE_BASE + distance_km * NDIAGA_NDIAYE_PAR_KM_MIN)
    prix_max = _arrondi_prix(NDIAGA_NDIAYE_BASE + distance_km * NDIAGA_NDIAYE_PAR_KM_MAX)
    return {
        "nom_transport": "Ndiaga Ndiaye",
        "image_url": meta.get("image_url") or "",
        "id_transport": meta.get("id_transport"),
        "numero_ligne": "", "nom_ligne": "",
        "prix_min": prix_min, "prix_max": max(prix_max, prix_min + 100),
        "duree_min_minutes": max(3, int(round(duree * 0.85))),
        "duree_max_minutes": max(5, int(round(duree * 1.35))),
        "correspondances": "Aucune",
        "etapes": f"Héler un Ndiaga Ndiaye sur son axe habituel et confirmer la destination avec le receveur | Trajet direct de {distance_km:.1f} km",
        "recommande": 0,
    }


def _option_a_pied(distance_km):
    duree = distance_km / VITESSE_MARCHE_KMH * 60
    return {
        "nom_transport": "À pied", "image_url": "", "id_transport": None,
        "numero_ligne": "", "nom_ligne": "",
        "prix_min": 0, "prix_max": 0,
        "duree_min_minutes": max(1, int(round(duree * 0.9))),
        "duree_max_minutes": max(2, int(round(duree * 1.2))),
        "correspondances": "Aucune",
        "etapes": f"Ces deux lieux sont très proches (~{distance_km*1000:.0f} m) : trajet possible à pied",
        "recommande": 0,
    }


# Fonction principale, appelée par database.py

def calculer_itineraire(conn, lieu_depart, lieu_arrivee, graphe=None):
    """Calcule toutes les options entre deux lieux et renvoie
    (options, distance_km), la meilleure option étant marquée recommande=1."""
    if graphe is None:
        graphe = Graphe(conn)

    id_ld, id_la = lieu_depart["id_lieu"], lieu_arrivee["id_lieu"]
    sources = graphe.arrets_du_lieu(id_ld)
    cibles = graphe.arrets_du_lieu(id_la)

    distance_directe = haversine_km(
        lieu_depart["latitude"], lieu_depart["longitude"],
        lieu_arrivee["latitude"], lieu_arrivee["longitude"]
    )

    options = []

    if sources and cibles and id_ld != id_la:
        opt_transit = None
        cible_atteinte, _dist, pred = _dijkstra(graphe, sources, cibles)
        if cible_atteinte is not None:
            chemin = _reconstruire_chemin(pred, sources, cible_atteinte)
            legs = _grouper_en_etapes(graphe, chemin)
            opt_transit = _formatter_option_transit(graphe, legs)
            if opt_transit:
                options.append(opt_transit)

        # Alternative minibus (Tata + Car rapide), le moins cher : calculée
        # à part pour apparaître même si un autre mode est plus rapide.
        cible_mini, _dist_mini, pred_mini = _dijkstra_filtre(
            graphe, sources, cibles, lambda m: m.get("est_minibus")
        )
        if cible_mini is not None:
            chemin_mini = _reconstruire_chemin(pred_mini, sources, cible_mini)
            legs_mini = _grouper_en_etapes(graphe, chemin_mini)
            opt_mini = _formatter_option_transit(graphe, legs_mini)
            if opt_mini and not any(o["etapes"] == opt_mini["etapes"] for o in options):
                options.append(opt_mini)

        # Une alternative par mode de transport (DDD, Car rapide, Tata,
        # BRT, TER...), pour ne pas se limiter au chemin le plus rapide.
        for id_transport, nom_transport in graphe.transports_routables.items():
            cible_mode, _dist_mode, pred_mode = _dijkstra_filtre(
                graphe, sources, cibles, lambda m, tid=id_transport: m["id_transport"] == tid
            )
            if cible_mode is None:
                continue
            chemin_mode = _reconstruire_chemin(pred_mode, sources, cible_mode)
            legs_mode = _grouper_en_etapes(graphe, chemin_mode)
            opt_mode = _formatter_option_transit(graphe, legs_mode)
            if opt_mode and not any(o["etapes"] == opt_mode["etapes"] for o in options):
                options.append(opt_mode)

    if id_ld != id_la:
        transports_meta = getattr(graphe, "transports_meta", {})
        options.append(_option_taxi(distance_directe, transports_meta.get("Taxi")))
        options.append(_option_clando(distance_directe, transports_meta.get("Clando")))
        options.append(_option_jakarta(distance_directe, transports_meta.get("Jakarta (moto-taxi)")))
        options.append(_option_ndiaga_ndiaye(distance_directe, transports_meta.get("Ndiaga Ndiaye")))
        if distance_directe <= SEUIL_MARCHE_A_PIED_KM:
            options.append(_option_a_pied(distance_directe))

    # --- Choix de l'option recommandée ---
    if options:
        def score(o):
            correspondances_penalite = o.get("nb_correspondances", 0) * 12
            # Le Clando n'a pas de prix affiché, on utilise son estimation interne.
            if o["prix_min"] is not None:
                prix_moyen = (o["prix_min"] + o["prix_max"]) / 2
            else:
                prix_moyen = o.get("_prix_score", 0)
            duree_moyenne = (o["duree_min_minutes"] + o["duree_max_minutes"]) / 2
            return duree_moyenne + correspondances_penalite + prix_moyen / 40

        meilleure = min(options, key=score)
        meilleure["recommande"] = 1
        # tri : recommandé d'abord, puis par durée moyenne croissante
        options.sort(key=lambda o: (0 if o.get("recommande") else 1,
                                     (o["duree_min_minutes"] + o["duree_max_minutes"]) / 2))

    for o in options:
        o.pop("nb_correspondances", None)
        o.pop("_prix_score", None)

    return options, distance_directe