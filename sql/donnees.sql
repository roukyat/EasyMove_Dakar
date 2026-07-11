-- =====================================================================
-- EasyMoveDakar - Données (DML) - Version Professionnelle épurée
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
('Yoff',               'quartier',         14.7444, -17.4677, 'Quartier balnéaire et village lébou, terminus des lignes Tata 3 et 4'),
('Ngor',               'quartier',         14.7508, -17.5133, 'Village de pêcheurs à la pointe de la presqu''île, embarcadère pour l''île de Ngor'),
('Parcelles Assainies','quartier',         14.7565, -17.4360, 'Vaste zone résidentielle de la banlieue proche, carrefour de plusieurs lignes de minibus'),
('Grand Yoff',         'quartier',         14.7364, -17.4569, 'Quartier populaire densément peuplé, traversé par la ligne Tata 47'),
('Thiaroye',            'quartier',        14.7639, -17.3592, 'Commune de la banlieue est, terminus de la ligne Tata 43'),
('Petersen',           'gare',             14.6759, -17.4373, 'Gare routière historique du centre-ville, principal terminus du réseau Tata/AFTU et point de départ du BRT'),
('Sacré-Cœur',         'quartier',         14.7186, -17.4638, 'Quartier résidentiel desservi par le BRT, proche de la VDN'),
('Grand Mbao',         'quartier',         14.7492, -17.3178, 'Zone industrielle et résidentielle à l''est de Dakar, terminus des lignes Tata 40 et 44'),
('Nord Foire',         'quartier',         14.7461, -17.4826, 'Quartier proche du Centre International du Commerce Extérieur, terminus de la ligne Tata 34');

-- ---------------------------------------------------------------------
-- MOYENS DE TRANSPORT
-- Note : les images ne sont renseignees que lorsqu une photo reelle et
-- correctement identifiee est disponible dans /static/img. Les autres
-- restent vides (image_url vide) en attendant l ajout de vraies photos ;
-- le template affiche alors une icone de repli, jamais une image incorrecte.
-- ---------------------------------------------------------------------
INSERT INTO moyens_transport (nom, image_url, description, cout_min, cout_max, niveau_confort, disponibilite, avantages, inconvenients) VALUES
('Taxi clando',            '/static/img/taxi.jpg', 'Taxi de ville jaune et noir, prix à négocier',                         500,  2000,  'Moyen',  '24h/24',
 'Rapide, disponible partout, porte-à-porte',
 'Prix à négocier, confort variable, pas de compteur'),
('Dakar Dem Dikk',         '', 'Bus officiel de la ville de Dakar (DDD), lignes numérotées et tarif fixe — opérateur public, distinct du réseau Tata/AFTU',   150,  300,   'Moyen',  '6h - 22h',
 'Prix fixe et abordable, réseau étendu',
 'Peut être bondé aux heures de pointe, moins flexible'),
('Car rapide',             '/static/img/Car_rapide.jpg', 'Minibus artisanal coloré, emblème populaire du transport à Dakar',                100,  200,   'Faible', 'Selon affluence',
 'Très bon marché, expérience authentique',
 'Confort limité, pas d''horaires fixes'),
('Minibus Tata (AFTU)',    '/static/img/mini_bus.jpg', 'Réseau de minibus numérotés géré par l''AFTU, dessert la quasi-totalité des communes de Dakar (une soixantaine de lignes)', 100,  500,   'Faible', 'Tôt le matin - tard le soir, selon affluence',
 'Très bon marché, réseau très dense, dessert presque tous les quartiers',
 'Bondé aux heures de pointe, pas d''horaires fixes, numéros parfois difficiles à repérer'),
('Jakarta (moto-taxi)',    '', 'Moto-taxi rapide pour se faufiler dans les embouteillages',             300,  1500,  'Faible', '24h/24',
 'Très rapide en cas d''embouteillages, économique',
 'Moins sécurisant, casque pas toujours fourni'),
('TER',                    '', 'Train Express Régional reliant Dakar à Diamniadio et à l''aéroport AIBD (extension vers Thiès prévue pour 2027-2028)',      500,  2500,  'Élevé',  '5h30 - 22h30',
 'Rapide, climatisé, ponctuel, prix fixe',
 'Dessert un nombre limité de gares'),
('BRT (Bus Rapid Transit)','/static/img/BRT.jpg', 'Bus électrique à haut niveau de service en site propre, reliant Petersen à la préfecture de Guédiawaye (lignes B1 et B2), mis en service en 2024', 400, 500, 'Élevé', '6h - 21h (7j/7)',
 'Ponctuel, climatisé, fréquence de 6 minutes, embarquement au niveau du quai',
 'Couvre pour l''instant un seul axe (Petersen - Guédiawaye)');

-- ---------------------------------------------------------------------
-- LIGNES DE BUS / TRAIN / MINIBUS (Séparation stricte via est_minibus)
-- Les lignes Tata ci-dessous sont basees sur la documentation publique la
-- plus complete disponible (AFTU/Tata route list, recensement communautaire).
-- Ce n est pas un registre officiel exhaustif : les numeros et grands axes
-- sont reels, mais l AFTU exploite pres de 60 lignes au total.
-- ---------------------------------------------------------------------
INSERT INTO lignes_bus (numero_ligne, nom_ligne, id_transport, est_minibus, description) VALUES
('Ligne 14', 'Plateau - UCAD',        (SELECT id_transport FROM moyens_transport WHERE nom='Dakar Dem Dikk'), 0, 'Liaison entre le Plateau et l''université'),
('Ligne 7',  'Plateau - Pikine',      (SELECT id_transport FROM moyens_transport WHERE nom='Dakar Dem Dikk'), 0, 'Liaison entre le centre-ville et Pikine'),
('Ligne 9',  'Plateau - Guédiawaye',  (SELECT id_transport FROM moyens_transport WHERE nom='Dakar Dem Dikk'), 0, 'Liaison vers la banlieue nord'),
('TER',      'Dakar - AIBD',          (SELECT id_transport FROM moyens_transport WHERE nom='TER'),           0, 'Ligne ferroviaire Dakar - Diamniadio - AIBD'),
('B1', 'Petersen - Préfecture de Guédiawaye (Omnibus)', (SELECT id_transport FROM moyens_transport WHERE nom='BRT (Bus Rapid Transit)'), 0, 'Ligne omnibus du BRT, 14 stations, dessert tous les arrêts entre Petersen et Guédiawaye'),
('B2', 'Petersen - Préfecture de Guédiawaye (Semi-express)', (SELECT id_transport FROM moyens_transport WHERE nom='BRT (Bus Rapid Transit)'), 0, 'Ligne semi-express du BRT, 7 stations, du lundi au samedi'),
('Ligne 3',  'Petersen - Yoff Village (via Ouakam, Mamelles)', (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata reliant le centre-ville à Yoff en passant par Ouakam et les Mamelles'),
('Ligne 4',  'Petersen - Yoff Village (via VDN)',              (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata reliant le centre-ville à Yoff par la Voie de Dégagement Nord'),
('Ligne 34', 'Petersen - Nord Foire (via Gueule Tapée, Rue 10)', (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata desservant Nord Foire depuis le centre-ville'),
('Ligne 36', 'Ngor - Guédiawaye (via Parcelles Assainies)',    (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata traversant la corniche nord jusqu''à Guédiawaye'),
('Ligne 40', 'Petersen - Grand Mbao (via Hann Maristes)',      (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata reliant le centre-ville à la zone industrielle de Mbao'),
('Ligne 43', 'Ouakam - Thiaroye (via Grand Dakar)',            (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata reliant Ouakam à Thiaroye'),
('Ligne 44', 'Ouakam - Grand Mbao (via VDN)',                  (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata reliant Ouakam à Grand Mbao par la VDN'),
('Ligne 46', 'Petersen - Guédiawaye (via Pikine, Liberté, Bourguiba)', (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata reliant le centre-ville à Guédiawaye via Pikine'),
('Ligne 47', 'Petersen - Almadies (via Grand Yoff)',           (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata reliant le centre-ville aux Almadies via Grand Yoff'),
('Ligne 67', 'Ouakam - Rufisque (via Bourguiba)',              (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), 1, 'Minibus Tata reliant Ouakam à Rufisque');

-- ---------------------------------------------------------------------
-- ARRÊTS
-- ---------------------------------------------------------------------
INSERT INTO arrets (nom, id_lieu, latitude, longitude) VALUES
('Place de l''Indépendance',   (SELECT id_lieu FROM lieux WHERE nom='Plateau'),       14.6714, -17.4348),
('UCAD Étudiants',             (SELECT id_lieu FROM lieux WHERE nom='UCAD (Fann)'),   14.6928, -17.4610),
('Gare TER Petersen',          (SELECT id_lieu FROM lieux WHERE nom='Plateau'),       14.6775, -17.4370),
('Gare TER AIBD',              (SELECT id_lieu FROM lieux WHERE nom='Aéroport AIBD'), 14.6704, -17.0730),
('Gare Routière Pompiers',     (SELECT id_lieu FROM lieux WHERE nom='Gare Routière Pompiers'), 14.7231, -17.4419),
('Rond-point Liberté 6',       (SELECT id_lieu FROM lieux WHERE nom='Ouakam'),        14.7251, -17.4690),
('Arrêt Marché Tilène',        (SELECT id_lieu FROM lieux WHERE nom='Médina'),        14.6782, -17.4491),
('Petersen - Gare Routière',   (SELECT id_lieu FROM lieux WHERE nom='Petersen'),      14.6759, -17.4373),
('Yoff Village',               (SELECT id_lieu FROM lieux WHERE nom='Yoff'),          14.7444, -17.4677),
('Ngor Village',               (SELECT id_lieu FROM lieux WHERE nom='Ngor'),          14.7508, -17.5133),
('Terminus Parcelles Assainies', (SELECT id_lieu FROM lieux WHERE nom='Parcelles Assainies'), 14.7565, -17.4360),
('Carrefour Grand Yoff',       (SELECT id_lieu FROM lieux WHERE nom='Grand Yoff'),    14.7364, -17.4569),
('Terminus Thiaroye',          (SELECT id_lieu FROM lieux WHERE nom='Thiaroye'),      14.7639, -17.3592),
('Terminus Grand Mbao',        (SELECT id_lieu FROM lieux WHERE nom='Grand Mbao'),    14.7492, -17.3178),
('Terminus Nord Foire',        (SELECT id_lieu FROM lieux WHERE nom='Nord Foire'),    14.7461, -17.4826),
('Gare Routière Rufisque',     (SELECT id_lieu FROM lieux WHERE nom='Rufisque'),      14.7167, -17.2667),
('Station Sacré-Cœur (BRT)',   (SELECT id_lieu FROM lieux WHERE nom='Sacré-Cœur'),    14.7186, -17.4638),
('Préfecture de Guédiawaye (BRT)', (SELECT id_lieu FROM lieux WHERE nom='Guédiawaye'), 14.7692, -17.4036);

-- ---------------------------------------------------------------------
-- TABLE D''ASSOCIATION LIGNE_ARRETS (Tracé des lignes sur carte)
-- ---------------------------------------------------------------------
INSERT INTO ligne_arrets (id_ligne, id_arret, ordre) VALUES
-- Ligne 3 : Petersen -> Yoff via Ouakam
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 3'),  (SELECT id_arret FROM arrets WHERE nom='Petersen - Gare Routière'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 3'),  (SELECT id_arret FROM arrets WHERE nom='Rond-point Liberté 6'), 2),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 3'),  (SELECT id_arret FROM arrets WHERE nom='Yoff Village'), 3),
-- Ligne 4 : Petersen -> Yoff via VDN
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 4'),  (SELECT id_arret FROM arrets WHERE nom='Petersen - Gare Routière'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 4'),  (SELECT id_arret FROM arrets WHERE nom='Yoff Village'), 2),
-- Ligne 34 : Petersen -> Nord Foire
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 34'), (SELECT id_arret FROM arrets WHERE nom='Petersen - Gare Routière'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 34'), (SELECT id_arret FROM arrets WHERE nom='Terminus Nord Foire'), 2),
-- Ligne 36 : Ngor -> Guédiawaye via Parcelles
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 36'), (SELECT id_arret FROM arrets WHERE nom='Ngor Village'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 36'), (SELECT id_arret FROM arrets WHERE nom='Terminus Parcelles Assainies'), 2),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 36'), (SELECT id_arret FROM arrets WHERE nom='Préfecture de Guédiawaye (BRT)'), 3),
-- Ligne 40 : Petersen -> Grand Mbao
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 40'), (SELECT id_arret FROM arrets WHERE nom='Petersen - Gare Routière'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 40'), (SELECT id_arret FROM arrets WHERE nom='Terminus Grand Mbao'), 2),
-- Ligne 43 : Ouakam -> Thiaroye
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 43'), (SELECT id_arret FROM arrets WHERE nom='Rond-point Liberté 6'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 43'), (SELECT id_arret FROM arrets WHERE nom='Terminus Thiaroye'), 2),
-- Ligne 44 : Ouakam -> Grand Mbao
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 44'), (SELECT id_arret FROM arrets WHERE nom='Rond-point Liberté 6'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 44'), (SELECT id_arret FROM arrets WHERE nom='Terminus Grand Mbao'), 2),
-- Ligne 46 : Petersen -> Guédiawaye via Pikine
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 46'), (SELECT id_arret FROM arrets WHERE nom='Petersen - Gare Routière'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 46'), (SELECT id_arret FROM arrets WHERE nom='Préfecture de Guédiawaye (BRT)'), 2),
-- Ligne 47 : Petersen -> Almadies via Grand Yoff
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 47'), (SELECT id_arret FROM arrets WHERE nom='Petersen - Gare Routière'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 47'), (SELECT id_arret FROM arrets WHERE nom='Carrefour Grand Yoff'), 2),
-- Ligne 67 : Ouakam -> Rufisque
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 67'), (SELECT id_arret FROM arrets WHERE nom='Rond-point Liberté 6'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 67'), (SELECT id_arret FROM arrets WHERE nom='Gare Routière Rufisque'), 2),
-- B1 (Omnibus) : Petersen -> Guédiawaye, via Sacré-Cœur
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='B1'), (SELECT id_arret FROM arrets WHERE nom='Petersen - Gare Routière'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='B1'), (SELECT id_arret FROM arrets WHERE nom='Station Sacré-Cœur (BRT)'), 2),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='B1'), (SELECT id_arret FROM arrets WHERE nom='Préfecture de Guédiawaye (BRT)'), 3),
-- B2 (Semi-express) : Petersen -> Guédiawaye direct
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='B2'), (SELECT id_arret FROM arrets WHERE nom='Petersen - Gare Routière'), 1),
((SELECT id_ligne FROM lignes_bus WHERE numero_ligne='B2'), (SELECT id_arret FROM arrets WHERE nom='Préfecture de Guédiawaye (BRT)'), 2);

-- ---------------------------------------------------------------------
-- TRAJETS + OPTIONS
-- ---------------------------------------------------------------------

-- Trajet 1 : Plateau -> UCAD
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='UCAD (Fann)'), 4.5, 'Facile',
 'Trajet fréquent pour les étudiants. Le bus DDD ligne 14 reste la meilleure option.');
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

-- Trajet 3 : Plateau -> Almadies
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Almadies'), 12, 'Moyen',
 'Zone des restaurants et boîtes de nuit. Le taxi reste le plus pratique, la ligne Tata 47 est la moins chère.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Taxi clando'), NULL, 1000, 1500, 30, 50, 'Aucune',
 'Héler un taxi au Plateau | Dire "Almadies" ou préciser le nom du lieu | Négocier : ~1000-1500 FCFA selon l''heure', 1);
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT id_trajet FROM trajets WHERE id_lieu_depart=(SELECT id_lieu FROM lieux WHERE nom='Plateau') AND id_lieu_arrivee=(SELECT id_lieu FROM lieux WHERE nom='Almadies')),
 (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 47'), 150, 300, 45, 70, 'Aucune',
 'Prendre la ligne Tata 47 à Petersen | Direction Almadies via Grand Yoff', 0);

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
 'Le Lac Retba (Lac Rose) est un site touristique majeur.');
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

-- Trajet 7 : Ouakam -> Yoff
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Ouakam'), (SELECT id_lieu FROM lieux WHERE nom='Yoff'), 5, 'Facile',
 'Trajet court le long de la corniche nord, bien desservi par les Tata 3 et 4.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 3'), 100, 200, 15, 30, 'Aucune',
 'Prendre la ligne Tata 3 direction Yoff Village via les Mamelles', 1);

-- Trajet 8 : Plateau -> Guédiawaye (BRT)
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Plateau'), (SELECT id_lieu FROM lieux WHERE nom='Guédiawaye'), 18.3, 'Facile',
 'Depuis 2024, le BRT relie directement Petersen à la préfecture de Guédiawaye en site propre.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='BRT (Bus Rapid Transit)'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='B1'), 400, 500, 45, 55, 'Aucune',
 'Prendre le BRT ligne B1 (omnibus) à la station Petersen | Descendre à la Préfecture de Guédiawaye', 1);

-- Trajet 9 : Ngor -> Guédiawaye
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Ngor'), (SELECT id_lieu FROM lieux WHERE nom='Guédiawaye'), 16, 'Moyen',
 'Traversée nord-est de l''agglomération via Parcelles Assainies, desservie par la ligne Tata 36.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 36'), 150, 350, 50, 80, 'Aucune',
 'Prendre la ligne Tata 36 à Ngor Village | Direction Guédiawaye via Parcelles Assainies', 1);

-- Trajet 10 : Ouakam -> Rufisque
INSERT INTO trajets (id_lieu_depart, id_lieu_arrivee, distance_km, niveau_difficulte, description) VALUES
((SELECT id_lieu FROM lieux WHERE nom='Ouakam'), (SELECT id_lieu FROM lieux WHERE nom='Rufisque'), 25, 'Moyen',
 'Liaison assurée par la ligne Tata 67 via le boulevard Bourguiba.');
INSERT INTO trajet_options (id_trajet, id_transport, id_ligne, prix_min, prix_max, duree_min_minutes, duree_max_minutes, correspondances, etapes, recommande) VALUES
((SELECT last_insert_rowid()), (SELECT id_transport FROM moyens_transport WHERE nom='Minibus Tata (AFTU)'), (SELECT id_ligne FROM lignes_bus WHERE numero_ligne='Ligne 67'), 200, 400, 50, 90, 'Aucune',
 'Prendre la ligne Tata 67 à Ouakam | Direction Rufisque via le boulevard Bourguiba', 1);

-- ---------------------------------------------------------------------
-- PHRASES EN WOLOF
-- ---------------------------------------------------------------------
INSERT INTO phrases_wolof (wolof, francais, phonetique, situation) VALUES
('Salaam aleekum',        'Bonjour / La paix soit avec vous',            'sa-lam a-lé-koum',   'Salutations'),
('Maleekum salaam',       'Réponse à la salutation (paix sur vous aussi)', 'ma-lé-koum sa-lam', 'Salutations'),
('Nanga def ?',           'Comment vas-tu ?',                             'na-nga déf',         'Salutations'),
('Maa ngi fi',            'Je suis ici / Ça va bien (réponse)',           'ma-ngi-fi',          'Salutations'),
('Ana yow ?',             'Et toi, comment ça va ?',                      'a-na yow',           'Salutations'),
('Ba beneen yoon',        'À la prochaine fois',                          'ba bé-nén yoon',     'Salutations'),
('Ballago',               'Au revoir (forme familière)',                  'ba-la-go',           'Salutations'),
('Jërejëf',               'Merci',                                        'djé-ré-djef',        'Politesse'),
('Waaw',                  'Oui',                                          'waaw',               'Politesse'),
('Déedéet',               'Non',                                          'dé-dét',             'Politesse'),
('Baal ma',               'Excusez-moi / Pardon',                         'ba-al ma',           'Politesse'),
('Amul solo',             'Ce n''est rien / Pas de problème',             'a-moul so-lo',       'Politesse'),
('Ndank ndank',           'Doucement, doucement (expression de patience)', 'ndank ndank',       'Politesse'),
('Ma mangi dem',          'Je m''en vais / Au revoir',                    'ma man-gi dem',      'Salutations'),
('Nak bu baax ?',         'C''est combien ?',                             'nak boo baax',       'Négociation'),
('Ñaata la ?',            'Combien ça coûte ? (variante)',                'nya-ta la',          'Négociation'),
('Dafa seer',             'C''est trop cher',                             'da-fa sèr',          'Négociation'),
('Dafa seer lool',        'C''est vraiment trop cher',                    'da-fa sèr lool',     'Négociation'),
('Baax na',               'C''est bon, d''accord',                        'baax na',            'Négociation'),
('Dina dem',              'Je vais partir (si le prix n''est pas accepté)', 'di-na dem',        'Négociation'),
('Dem ci [lieu]',         'Aller à [lieu]',                               'dem si [lieu]',      'Transport'),
('Taxawal fii !',         'Arrêtez-vous ici !',                           'ta-xa-wal fi',       'Transport'),
('Yëgël ma ci...',        'Déposez-moi à...',                             'yé-guél ma si...',   'Transport'),
('Kañ nga dem ?',         'Quand pars-tu ?',                              'kagn nga dem',       'Transport'),
('Bus bi dafa fees',      'Le bus est plein',                             'bous bi da-fa fès',  'Transport'),
('Ana taxi yi ?',         'Où sont les taxis ?',                          'a-na tak-si yi',     'Transport'),
('Fan la [lieu] nekk ?',  'Où se trouve [lieu] ?',                        'fan la [lieu] nèk',  'Direction'),
('Jëm ci kanam',          'Aller tout droit',                             'djèm si ka-nam',     'Direction'),
('Jëm ci ndey',           'Tourner à gauche',                             'djèm si ndèy',       'Direction'),
('Jëm ci kaw',            'Tourner à droite',                             'djèm si kaw',        'Direction'),
('Yagg na ?',             'C''est loin ?',                                'yagg na',            'Direction'),
('Foofu la',              'C''est là-bas',                                'fo-fu la',           'Direction'),
('Fii la',                'C''est ici',                                   'fi la',              'Direction'),
('Benn, ñaar, ñett',      'Un, deux, trois',                              'bèn, nyar, nyèt',    'Nombres'),
('Ñeent, juróom',         'Quatre, cinq',                                 'nyènt, dju-rom',     'Nombres'),
('Juróom-benn',           'Six',                                          'dju-rom-bèn',        'Nombres'),
('Fukk',                  'Dix',                                          'fouk',               'Nombres'),
('Dama metti',            'J''ai mal / Je souffre',                       'da-ma mét-ti',       'Urgence'),
('Wóoy !',                'Au secours ! (exclamation de détresse)',       'wooy',               'Urgence'),
('Sama xel dafa tang',    'Je suis stressé(e) / inquiet(ète)',            'sa-ma xèl da-fa tang', 'Urgence');

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
('Argent et paiement',  'Montant fixe pour le DDD et le BRT', 'Le bus Dakar Dem Dikk et le BRT appliquent un tarif fixe, pas de négociation nécessaire.', 'Toute l''année'),
('Argent et paiement',  'Éviter de montrer trop d''argent',  'Sortez uniquement la somme nécessaire au moment de payer.', 'Toute l''année'),
('Saisons et météo',    'Prévoir du temps en saison des pluies', 'Les jours de pluie (juillet à octobre), prévoyez le double du temps de trajet habituel.', 'Météo'),
('Saisons et météo',    'Circulation dense le vendredi',    'La circulation peut être très dense le vendredi après-midi, lors du retour du travail et de la prière.', 'Heures de pointe'),
('Saisons et météo',    'Éviter les heures de pointe',      'Les heures de pointe sont 7h-9h le matin et 17h-20h le soir : prévoir une marge.', 'Heures de pointe'),
('Pour les femmes',     'Privilégier les transports connus', 'Privilégier le TER, le BRT ou le DDD en soirée plutôt qu''un taxi inconnu.', 'Toute l''année'),
('Périodes',            'Affluence pendant les vacances',    'Pendant les vacances scolaires et les grands événements religieux (Magal, Tabaski), les gares routières sont bondées : réserver ou partir tôt.', 'Vacances');

-- ---------------------------------------------------------------------
-- INFOS UTILES
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
