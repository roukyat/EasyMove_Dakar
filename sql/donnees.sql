-- =====================================================================
-- EasyMoveDakar - Données (DML)
-- =====================================================================

-- ---------------------------------------------------------------------
-- LIEUX
-- ---------------------------------------------------------------------
INSERT INTO lieux (nom, type_lieu, latitude, longitude, description) VALUES
('Plateau',            'quartier',         14.6708, -17.4313, 'Centre administratif et économique de Dakar'),
('UCAD (Fann)',        'universite',       14.6928, -17.4610, 'Université Cheikh Anta Diop'),
('Almadies',           'quartier',         14.7472, -17.5136, 'Quartier résidentiel et zone de restaurants / vie nocturne'),
('Ouakam',             'quartier',         14.7167, -17.4833, 'Quartier proche de la Mosquée de la Divinité'),
('Médina',             'quartier',         14.6708, -17.4467, 'Quartier populaire et commerçant'),
('Pikine',             'quartier',         14.7547, -17.3900, 'Grande commune de la banlieue de Dakar'),
('Guédiawaye',         'quartier',         14.7692, -17.4036, 'Commune de la banlieue nord de Dakar'),
('Rufisque',           'ville',            14.7167, -17.2667, 'Ville historique à l''entrée de Dakar'),
('Aéroport AIBD',      'aeroport',         14.6704, -17.0730, 'Aéroport International Blaise Diagne'),
('Gare Routière Pompiers', 'gare',         14.7231, -17.4419, 'Principale gare routière pour les liaisons interurbaines'),
('Lac Rose (Retba)',   'site_touristique', 14.8402, -17.2306, 'Lac rose classé au patrimoine, site touristique majeur'),
('Diamniadio',         'ville',            14.7167, -17.1833, 'Nouvelle ville en développement, desservie par le TER'),
('Thiès',               'ville',            14.7910, -16.9359, 'Deuxième ville du pays'),
('Saly',               'ville',            14.4491, -17.0122, 'Station balnéaire touristique'),
('Mbour',              'ville',            14.4198, -16.9646, 'Ville côtière proche de Saly'),
('Saint-Louis',        'ville',            16.0179, -16.4896, 'Ancienne capitale coloniale, patrimoine UNESCO'),
('Ziguinchor',         'ville',            12.5833, -16.2719, 'Capitale de la Casamance');

-- ---------------------------------------------------------------------
-- MOYENS DE TRANSPORT
-- ---------------------------------------------------------------------
INSERT INTO moyens_transport (nom, icone, description, cout_min, cout_max, niveau_confort, disponibilite, avantages, inconvenients) VALUES
('Taxi clando',        '🚖', 'Taxi de ville jaune et noir, prix à négocier',                         500,  2000,  'Moyen',  '24h/24',
 'Rapide, disponible partout, porte-à-porte',
 'Prix à négocier, confort variable, pas de compteur'),
('Dakar Dem Dikk',     '🚌', 'Bus officiel de la ville de Dakar (DDD), tarif fixe',                   150,  300,   'Moyen',  '6h - 22h',
 'Prix fixe et abordable, réseau étendu',
 'Peut être bondé aux heures de pointe, moins flexible'),
('Car rapide',         '🎨', 'Minibus coloré, emblème populaire du transport à Dakar',                100,  200,   'Faible', 'Selon affluence',
 'Très bon marché, expérience authentique',
 'Confort limité, pas d''horaires fixes'),
('Jakarta (moto-taxi)','🏍️', 'Moto-taxi rapide pour se faufiler dans les embouteillages',             300,  1500,  'Faible', '24h/24',
 'Très rapide en cas d''embouteillages, économique',
 'Moins sécurisant, casque pas toujours fourni'),
('TER',                '🚂', 'Train Express Régional reliant Dakar à Diamniadio / AIBD / Thiès',      500,  2500,  'Élevé',  '5h30 - 22h30',
 'Rapide, climatisé, ponctuel, prix fixe',
 'Dessert un nombre limité de gares'),
('Sept-places',        '🚐', 'Véhicule interurbain partagé, part quand il est plein',                 3000, 6000,  'Moyen',  'Journée uniquement',
 'Bon marché pour les longs trajets',
 'Départ non garanti à heure fixe, confort limité'),
('Avion (Air Sénégal)','✈️', 'Vols intérieurs pour rejoindre rapidement les régions éloignées',       35000,50000, 'Élevé',  'Selon vols programmés',
 'Très rapide sur longue distance',
 'Coût élevé, aéroports parfois éloignés du centre-ville'),
('Ferry',              '⛴️', 'Traversée maritime, notamment Dakar - Ziguinchor',                      8000, 15000, 'Moyen',  'Départs programmés (souvent de nuit)',
 'Confortable pour un long trajet, cabines disponibles',
 'Durée longue, dépend des conditions maritimes');

-- ---------------------------------------------------------------------
-- LIGNES DE BUS / TRAIN
-- ---------------------------------------------------------------------
INSERT INTO lignes_bus (numero_ligne, nom_ligne, id_transport, description) VALUES
('Ligne 14', 'Plateau - UCAD',        (SELECT id_transport FROM moyens_transport WHERE nom='Dakar Dem Dikk'), 'Liaison entre le Plateau et l''université'),
('Ligne 7',  'Plateau - Pikine',      (SELECT id_transport FROM moyens_transport WHERE nom='Dakar Dem Dikk'), 'Liaison entre le centre-ville et Pikine'),
('Ligne 9',  'Plateau - Guédiawaye',  (SELECT id_transport FROM moyens_transport WHERE nom='Dakar Dem Dikk'), 'Liaison vers la banlieue nord'),
('TER',      'Dakar - AIBD',          (SELECT id_transport FROM moyens_transport WHERE nom='TER'),           'Ligne ferroviaire Dakar - Diamniadio - AIBD');

-- ---------------------------------------------------------------------
-- ARRÊTS
-- ---------------------------------------------------------------------
INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES
('Place de l''Indépendance',   (SELECT id_lieu FROM lieux WHERE nom='Plateau'),       14.6714, -17.4348),
('UCAD Étudiants',             (SELECT id_lieu FROM lieux WHERE nom='UCAD (Fann)'),   14.6928, -17.4610),
('Gare TER Petersen',          (SELECT id_lieu FROM lieux WHERE nom='Plateau'),       14.6775, -17.4370),
('Gare TER AIBD',              (SELECT id_lieu FROM lieux WHERE nom='Aéroport AIBD'), 14.6704, -17.0730),
('Gare Routière Pompiers',     (SELECT id_lieu FROM lieux WHERE nom='Gare Routière Pompiers'), 14.7231, -17.4419);

-- ---------------------------------------------------------------------
-- TRAJETS + OPTIONS
-- ---------------------------------------------------------------------

-- Trajet 1 : Plateau -> UCAD
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='UCAD (Fann)'), 4.5, 'Facile',
 'Trajet fréquent pour les étudiants. Le bus DDD est la meilleure option aux heures de pointe.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Dakar Dem Dikk'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 14'), 150, 500, 20, 35, 'Aucune',
 'Prendre le bus DDD ligne 14 au Plateau (Place de l''Indépendance) | Descendre à l''arrêt "UCAD Étudiants"', 1);
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT id_trajet FROM trajets WHERE id_lieu_depart=(SELECT id_lieu FROM lieux WHERE nom='Plateau') AND id_lieu_arrivee=(SELECT id_lieu FROM lieux WHERE nom='UCAD (Fann)')),
 (SELECT id_transport FROM moyens_transport WHERE nom='Taxi clando'), NULL, 500, 500, 15, 25, 'Aucune',
 'Héler un taxi au Plateau | Dire "UCAD, Fann" — prix fixe ~500 FCFA', 0);

-- Trajet 2 : Aéroport AIBD -> Plateau
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Aéroport AIBD'), (SELECT id_lieu FROM lieux WHERE nom='Plateau'), 45, 'Facile',
 'Depuis l''aéroport Blaise Diagne. Le TER est fortement recommandé : rapide, climatisé, prix fixe.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='TER'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='TER'), 500, 2500, 45, 60, '1 (TER puis taxi/DDD)',
 'Prendre le TER à la gare AIBD (dans l''aéroport) | Direction "Dakar" — arrêt Petersen ou Gare de Dakar | Ensuite taxi ou DDD vers votre destination finale', 1);
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT id_trajet FROM trajets WHERE id_lieu_depart=(SELECT id_lieu FROM lieux WHERE nom='Aéroport AIBD') AND id_lieu_arrivee=(SELECT id_lieu FROM lieux WHERE nom='Plateau')),
 (SELECT id_transport FROM moyens_transport WHERE nom='Taxi clando'), NULL, 15000, 25000, 60, 90, 'Aucune',
 'Prendre un taxi directement à la sortie de l''aéroport | Négocier le prix avant de monter (trajet long)', 0);

-- Trajet 3 : Plateau -> Almadies
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Almadies'), 12, 'Moyen',
 'Zone des restaurants et boîtes de nuit. Le taxi est la solution la plus pratique.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Taxi clando'), NULL, 1000, 1500, 30, 50, 'Aucune',
 'Héler un taxi au Plateau | Dire "Almadies" ou préciser le nom du lieu | Négocier : ~1000-1500 FCFA selon l''heure', 1);

-- Trajet 4 : Plateau -> Pikine
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Pikine'), 15, 'Moyen',
 'Grande commune de banlieue, bien desservie par les bus DDD.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Dakar Dem Dikk'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 7'), 200, 400, 35, 60, 'Aucune',
 'Prendre le bus DDD ligne 7 au Plateau | Descendre à l''arrêt principal de Pikine', 1);

-- Trajet 5 : Dakar (Plateau) -> Lac Rose
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Lac Rose (Retba)'), 35, 'Moyen',
 'Le Lac Retba (Lac Rose) est un site touristique majeur, classé UNESCO. À visiter absolument.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Taxi clando'), NULL, 1000, 3000, 45, 60, '1 (via Rufisque)',
 'Prendre un taxi depuis Dakar vers Rufisque | Puis minibus ou taxi vers le lac | Négocier un taxi aller-retour (meilleure option)', 1);

-- Trajet 6 : Dakar -> Diamniadio
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Diamniadio'), 30, 'Facile',
 'Nouvelle ville desservie directement par le TER.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='TER'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='TER'), 500, 1500, 30, 40, 'Aucune',
 'Prendre le TER à la gare Petersen | Descendre à la gare de Diamniadio', 1);

-- Trajet 7 : Dakar -> Thiès
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Thiès'), 70, 'Moyen',
 'Deuxième ville du pays, accessible en sept-places ou en car.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Sept-places'), NULL, 1500, 2500, 60, 90, 'Aucune',
 'Aller à la Gare Routière de Dakar (Pompiers) | Chercher les voitures "Thiès" | Le départ se fait quand la voiture est pleine', 1);

-- Trajet 8 : Dakar -> Saly / Mbour
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Saly'), 80, 'Moyen',
 'Station balnéaire prisée des touristes, à environ 1h30 de route.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Sept-places'), NULL, 2000, 3500, 90, 120, 'Aucune',
 'Gare Routière de Dakar (Pompiers) | Chercher les voitures "Saly / Mbour" | Départ quand la voiture est pleine', 1);

-- Trajet 9 : Dakar -> Saint-Louis
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Saint-Louis'), 265, 'Moyen',
 'Ancienne capitale coloniale, patrimoine UNESCO. Départ depuis la Gare Routière de Dakar.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Sept-places'), NULL, 3000, 6000, 180, 240, 'Aucune',
 'Aller à la Gare Routière de Dakar (Pompiers) | Chercher les voitures "Saint-Louis" (sept-places) | Le départ se fait quand la voiture est pleine', 1);

-- Trajet 10 : Dakar -> Ziguinchor
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Ziguinchor'), 450, 'Complexe',
 'Capitale de la Casamance. Long trajet routier — privilégier la traversée en ferry ou l''avion.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Ferry'), NULL, 8000, 15000, 660, 720, 'Aucune',
 'Ferry Dakar - Ziguinchor (traversée de nuit) | Réserver sa cabine à l''avance', 1);
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT id_trajet FROM trajets WHERE id_lieu_depart=(SELECT id_lieu FROM lieux WHERE nom='Plateau') AND id_lieu_arrivee=(SELECT id_lieu FROM lieux WHERE nom='Ziguinchor')),
 (SELECT id_transport FROM moyens_transport WHERE nom='Avion (Air Sénégal)'), NULL, 35000, 50000, 60, 75, 'Aucune',
 'Vol direct Air Sénégal Dakar - Ziguinchor', 0);

-- ---------------------------------------------------------------------
-- PHRASES EN WOLOF
-- ---------------------------------------------------------------------
INSERT INTO phrases_wolof (wolof, francais, phonetique, situation) VALUES
('Salaam aleekum',        'Bonjour / La paix soit avec vous',            'sa-lam a-lé-koum',   'Salutations'),
('Nanga def ?',           'Comment vas-tu ?',                             'na-nga déf',         'Salutations'),
('Maa ngi fi',            'Je suis ici / Ça va bien (réponse)',           'ma-ngi-fi',          'Salutations'),
('Jërejëf',               'Merci',                                        'djé-ré-djef',        'Politesse'),
('Waaw',                  'Oui',                                          'waaw',               'Politesse'),
('Déedéet',               'Non',                                          'dé-dét',             'Politesse'),
('Ma mangi dem',          'Je m''en vais / Au revoir',                    'ma man-gi dem',      'Salutations'),
('Nak bu baax ?',         'C''est combien ?',                             'nak boo baax',       'Négociation'),
('Dafa seer',             'C''est trop cher',                             'da-fa sèr',          'Négociation'),
('Dafa seer lool',        'C''est vraiment trop cher',                    'da-fa sèr lool',     'Négociation'),
('Baax na',               'C''est bon, d''accord',                        'baax na',            'Négociation'),
('Dina dem',              'Je vais partir (si le prix n''est pas accepté)', 'di-na dem',        'Négociation'),
('Dem ci [lieu]',         'Aller à [lieu]',                               'dem si [lieu]',      'Transport'),
('Taxawal fii !',         'Arrêtez-vous ici !',                           'ta-xa-wal fi',       'Transport'),
('Yëgël ma ci...',        'Déposez-moi à...',                             'yé-guél ma si...',   'Transport'),
('Fan la [lieu] nekk ?',  'Où se trouve [lieu] ?',                        'fan la [lieu] nèk',  'Direction'),
('Ma dem [lieu] lañu jëf ?', 'Comment aller à [lieu] ?',                  'ma dem... la-ñoo jef', 'Direction'),
('Jëm ci kanam',          'Aller tout droit',                             'djèm si ka-nam',     'Direction'),
('Jëm ci ndey',           'Tourner à gauche',                             'djèm si ndèy',       'Direction'),
('Jëm ci kaw',            'Tourner à droite',                             'djèm si kaw',        'Direction'),
('Yagg na ?',             'C''est loin ?',                                'yagg na',            'Direction'),
('Dama metti',            'J''ai mal / Je souffre',                       'da-ma mét-ti',       'Urgence');

-- ---------------------------------------------------------------------
-- CONSEILS
-- ---------------------------------------------------------------------
INSERT INTO conseils (categorie, titre, contenu, periode) VALUES
('Avant de partir',     'Prévoir de la monnaie',            'Ayez toujours des petites coupures : les chauffeurs n''ont pas toujours la monnaie sur un gros billet.', 'Toute l''année'),
('Avant de partir',     'Vêtements adaptés',                'Porter des vêtements légers mais couvrants, par respect culturel.', 'Toute l''année'),
('Dans le transport',   'Négocier avant de monter',         'Pour les taxis clando, toujours fixer le prix avant de monter, jamais après.', 'Toute l''année'),
('Dans le transport',   'Vérifier la destination',          'Confirmer la destination avec le chauffeur avant de partir pour éviter tout malentendu.', 'Toute l''année'),
('Confort et bien-être','Climatisation non garantie',       'La climatisation n''est pas garantie dans tous les taxis ni dans les cars rapides.', 'Toute l''année'),
('Confort et bien-être','Se protéger du soleil',            'Utiliser un chapeau ou un parasol en cas de fort ensoleillement.', 'Toute l''année'),
('Argent et paiement',  'Montant fixe pour le DDD',          'Le bus Dakar Dem Dikk applique un tarif fixe, pas de négociation nécessaire.', 'Toute l''année'),
('Argent et paiement',  'Éviter de montrer trop d''argent',  'Sortez uniquement la somme nécessaire au moment de payer.', 'Toute l''année'),
('Saisons et météo',    'Prévoir du temps en saison des pluies', 'Les jours de pluie (juillet à octobre), prévoyez le double du temps de trajet habituel.', 'Météo'),
('Saisons et météo',    'Circulation dense le vendredi',    'La circulation peut être très dense le vendredi après-midi, lors du retour du travail et de la prière.', 'Heures de pointe'),
('Saisons et météo',    'Éviter les heures de pointe',      'Les heures de pointe sont 7h-9h le matin et 17h-20h le soir : prévoir une marge.', 'Heures de pointe'),
('Pour les femmes',     'Privilégier les transports connus', 'Privilégier le TER ou le DDD en soirée plutôt qu''un taxi inconnu.', 'Toute l''année'),
('Périodes',            'Affluence pendant les vacances',    'Pendant les vacances scolaires et les grands événements religieux (Magal, Tabaski), les gares routières sont bondées : réserver ou partir tôt.', 'Vacances');

-- ---------------------------------------------------------------------
-- INFOS UTILES (numéros d'urgence etc.)
-- ---------------------------------------------------------------------
INSERT INTO infos_utiles (categorie, libelle, valeur) VALUES
('Urgence', 'Police nationale',       '17'),
('Urgence', 'SAMU (urgences médicales)', '15'),
('Urgence', 'Sapeurs-pompiers',       '18'),
('Urgence', 'Gendarmerie nationale',  '800 00 20 20'),
('À emporter', 'Objet recommandé',    'Petite monnaie en FCFA'),
('À emporter', 'Objet recommandé',    'Chapeau ou casquette'),
('À emporter', 'Objet recommandé',    'Bouteille d''eau'),
('À emporter', 'Objet recommandé',    'Copie de vos papiers d''identité');
