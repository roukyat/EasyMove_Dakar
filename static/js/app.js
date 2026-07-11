// Initialisation globale
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    initSearch();
});

// 1. Logique de Carte (Leaflet)
let map;
let routingControl = null; // Variable critique pour stocker et réinitialiser l'itinéraire actuel comme Google Maps

function initMap() {
    const mapElement = document.getElementById('map');
    if (!mapElement) return;

    map = L.map('map', { zoomControl: false }).setView([14.6937, -17.4441], 13);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(map);

    // Repositionner le contrôle du zoom de Leaflet proprement
    L.control.zoom({ position: 'topright' }).addTo(map);
}

// 2. Logique de recherche (Uber-like : filtrage instantané)
function initSearch() {
    const searchInput = document.getElementById('searchNetwork');
    if (!searchInput) return;

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const items = document.querySelectorAll('.line-item-row');
        
        items.forEach(item => {
            const text = item.textContent.toLowerCase();
            item.style.display = text.includes(query) ? 'flex' : 'none';
        });
    });
}

/**
 * 3. FONCTION DE GUIDAGE (STYLE GOOGLE MAPS)
 * Appelée automatiquement par le clic sur le bouton "Cartographie" de vos itinéraires predefinis.
 */
function tracerMonItineraire(latDep, lngDep, nomDep, latArr, lngArr, nomArr) {
    if (!map) {
        console.error("La carte n'est pas initialisée.");
        return;
    }

    // Si un itinéraire ou des flèches Google Maps existent déjà, on les supprime pour faire place au nouveau
    if (routingControl) {
        map.removeControl(routingControl);
    }

    // Configuration du moteur de routage Leaflet (Moteur OSRM public)
    routingControl = L.Routing.control({
        waypoints: [
            L.latLng(latDep, lngDep), // Point A (Départ)
            L.latLng(latArr, lngArr)  // Point B (Arrivée)
        ],
        router: L.Routing.osrmv1({
            language: 'fr',             // Instructions de guidage textuelles en Français
            profile: 'car'              // Routage pour voiture/transport ('foot' ou 'bike' si piéton)
        }),
        lineOptions: {
            styles: [{ color: '#1a73e8', weight: 6, opacity: 0.85 }] // Ligne bleue style Google Maps
        },
        createMarker: function(i, waypoint, n) {
            // Personnalisation des bulles d'informations au-dessus des épingles
            const label = i === 0 ? `<b>Départ :</b> ${nomDep}` : `<b>Arrivée :</b> ${nomArr}`;
            return L.marker(waypoint.latLng).bindPopup(label);
        },
        // Active le panneau des étapes détaillées à suivre "Tourner à gauche, prendre l'avenue..."
        show: true, 
        collapsible: true // Permet à l'utilisateur de plier/déplier le guidage
    }).addTo(map);

    // Centrer et ajuster automatiquement la caméra sur le trajet global tracé
    routingControl.on('routesfound', function(e) {
        const routes = e.routes;
        const bounds = L.latLngBounds(routes[0].coordinates);
        map.fitBounds(bounds, { padding: [50, 50] });
    });
}

// 4. Fonction pour relancer un trajet (Appel API de lignes prédéfinies)
async function fetchRoute(idLigne) {
    try {
        const response = await fetch(`/api/minibus/arrets?id_ligne=${idLigne}`);
        const data = await response.json();
        console.log("Données ligne reçues :", data);
        
        if (data && data.length > 1) {
            // Optionnel : Si vous voulez tracer tous les arrêts consécutifs d'une ligne de bus entière
            const waypoints = data.map(arret => L.latLng(arret.latitude, arret.longitude));
            
            if (routingControl) map.removeControl(routingControl);
            
            routingControl = L.Routing.control({
                waypoints: waypoints,
                router: L.Routing.osrmv1({ language: 'fr', profile: 'car' }),
                lineOptions: { styles: [{ color: '#34a853', weight: 5 }] } // Ligne verte pour le bus
            }).addTo(map);
        }
    } catch (error) {
        console.error("Erreur lors de la récupération :", error);
    }
}

// 5. Géolocalisation (Type "Où est mon chauffeur / Où suis-je")
function geolocateUser() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(pos => {
            const { latitude, longitude } = pos.coords;
            map.setView([latitude, longitude], 15);
            
            // Ajout d'une épingle bleue distinctive pour la position de l'utilisateur
            L.marker([latitude, longitude], {
                icon: L.divIcon({
                    className: 'user-location-pulse',
                    html: '<div class="pulse-dot"></div>',
                    iconSize: [20, 20]
                })
            }).addTo(map).bindPopup("Vous êtes ici").openPopup();
        });
    }
}

// 6. Gestion du Thème (Sombre / Clair)
const themeToggle = document.getElementById('theme-toggle');
const body = document.body;

if (localStorage.getItem('theme') === 'light') {
    body.classList.add('light-mode');
}

if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        body.classList.toggle('light-mode');
        if (body.classList.contains('light-mode')) {
            localStorage.setItem('theme', 'light');
        } else {
            localStorage.setItem('theme', 'dark');
        }
    });
}