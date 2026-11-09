# Herretang — Tuilerie, données horaires 2023–2025

Deux fichiers à utiliser :

- `frequentation_herretang_2023_2025.csv` : passages piétons entrants et calendrier.
- `meteo_herretang_2023_2025.csv` : précipitations et neige tombée sur les mêmes créneaux.

Format : CSV UTF-8 avec BOM pour Excel, séparateur point-virgule, séparateur décimal point. Une ligne par heure. Les indicateurs valent 1 pour oui et 0 pour non. Les fichiers couvrent 1 096 jours et contiennent chacun 26 304 lignes de données.

## Fréquentation

Source : archives annuelles originales SSP Cloud, `Fréquentation/DONNEES brutes ecocompteurs ENS`, années 2023, 2024 et 2025. Site `100040825`, canal piéton IN `353347292`, compteur `X2I21055989`. Les sorties et les autres accès de l'Herretang ne sont pas inclus. Une mesure décrit des passages, pas des visiteurs uniques ou une occupation simultanée.

Les comptages valides sont conservés sans modification. Trois valeurs sources sont absentes aux changements d'heure d'automne : elles restent vides, avec `qualite_frequentation=manquante`. Ne pas les considérer comme des zéros. Les 26 301 autres valeurs sont non négatives et entières ; cela ne prouve pas l'absence d'anomalies de capteur sur le terrain. Les pics n'ont pas été supprimés arbitrairement.

Colonnes : `debut_utc`, `debut_local`, `date`, `heure`, `fin_local`, `jour_semaine`, `weekend`, `jour_ferie`, `nom_jour_ferie`, `vacances_scolaires_zone_a`, `nom_vacances`, `passages_entrants`, `qualite_frequentation`.

## Calendrier

Jours fériés métropolitains : https://calendrier.api.gouv.fr/jours-feries/metropole.json

Vacances scolaires : ministère de l'Éducation nationale, jeu `fr-en-calendrier-scolaire`, académie Grenoble, zone A, population élèves ou commune aux populations (`-`). Les périodes réservées aux enseignants sont exclues. Le pont de l'Ascension est inclus parmi les périodes sans classe signalées par cette source. API : https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-calendrier-scolaire/records

L'indicateur vacances est un attribut de la journée : date locale de début incluse, date de reprise exclue. Ce n'est pas une mesure des heures de cours du samedi de départ. Le calendrier officiel indique un départ après la classe ; les horaires précis de classe ne sont pas fournis. La zone A représente le calendrier local, pas les vacances de toutes les régions d'origine des visiteurs.

## Météo

Source : https://archive-api.open-meteo.com/v1/archive

Requête : latitude 45.38224, longitude 5.68871, du 2023-01-01 au 2025-12-31, variables horaires `precipitation,snowfall`, timezone UTC, timeformat unixtime, modèle par défaut best_match. Les coordonnées de grille retournées sont 45.377853, 5.633803. Ce sont des estimations de réanalyse pour la zone, pas une station installée au compteur. Réponse originale conservée dans `sources/meteo_horaire_openmeteo.json`.

- `precipitations_mm` : cumul de précipitations sur le créneau, incluant pluie et équivalent en eau de la neige.
- `precipitation_oui_non` : 1 si ce cumul est strictement supérieur à 0 mm, sinon 0. Ce seuil capte aussi les petites précipitations ; il ne constitue pas un seuil de gêne validé.
- `neige_tombee_cm` : quantité estimée de neige tombée pendant le créneau.
- `neige_oui_non` : 1 si la quantité de neige tombée est strictement supérieure à 0 cm, sinon 0. Ce n'est pas un indicateur de neige restant au sol.

La documentation Open-Meteo étiquette ces cumuls à la fin de l'heure précédente. Pour les passages entre 10 h et 11 h, on utilise donc le cumul météo étiqueté 11 h. Documentation : https://open-meteo.com/en/docs/historical-weather-api

## Association et contrôles

Joindre les deux fichiers avec `debut_utc`. Cette clé est unique et identique dans les deux fichiers. Ne pas joindre uniquement sur date et heure locales : lors du passage à l'heure d'hiver, 2 h apparaît deux fois avec des décalages UTC différents. Les dates et heures lisibles sont exprimées dans Europe/Paris ; les instants UTC servent à garantir l'alignement.

Les contrôles exécutés vérifient les créneaux horaires, l'absence de doublons UTC, la couverture des 1 096 jours, l'égalité des clés des deux fichiers, la conservation du total des passages valides (37 626), la couverture intégrale des variables météo et la pagination complète du calendrier scolaire. Voir `verification.json`.

Reproduction : `python3 preparer_donnees.py`, depuis n'importe quel répertoire, en conservant les sources et les archives SSP Cloud à leurs emplacements actuels.

Ces fichiers préparent l'entraînement, qui n'a pas été lancé. Pour évaluer une prévision réelle, utiliser seulement les informations disponibles au moment où elle est émise : la météo future provient de prévisions, pas d'observations connues à l'avance.
