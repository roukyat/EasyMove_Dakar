// Initialisation globale
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    initSearch();
});

// 1. Logique de Carte (Leaflet)
let map;
function initMap() {
    const mapElement = document.getElementById('map');
    if (!mapElement) return;

    map = L.map('map', { zoomControl: false }).setView([14.6937, -17.4441], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(map);
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

// 3. Fonction pour relancer un trajet (Appel API)
async function fetchRoute(idLigne) {
    try {
        const response = await fetch(`/api/minibus/arrets?id_ligne=${idLigne}`);
        const data = await response.json();
        
        // Ici, vous pourriez tracer la polyligne sur la carte
        console.log("Données ligne reçues :", data);
        // Exemple : drawPolyline(data); 
    } catch (error) {
        console.error("Erreur lors de la récupération :", error);
    }
}

// 4. Géolocalisation (Type "Où est mon chauffeur")
function geolocateUser() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(pos => {
            const { latitude, longitude } = pos.coords;
            map.setView([latitude, longitude], 15);
            // Ajouter un marqueur "utilisateur" ici
        });
    }
}

const themeToggle = document.getElementById('theme-toggle');
const body = document.body;

// Vérifier le choix précédent
if (localStorage.getItem('theme') === 'light') {
    body.classList.add('light-mode');
}

themeToggle.addEventListener('click', () => {
    body.classList.toggle('light-mode');
    
    // Sauvegarder le choix
    if (body.classList.contains('light-mode')) {
        localStorage.setItem('theme', 'light');
    } else {
        localStorage.setItem('theme', 'dark');
    }
});