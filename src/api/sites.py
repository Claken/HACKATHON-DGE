"""
Catalogue des sites supportés par le pipeline ML.

Chaque entrée référence un site ENS (CG38 Environnement) avec les paramètres
nécessaires au pipeline : canal de comptage, coordonnées GPS, capacité,
seuils d'alerte, et chemins vers les données CSV.

Usage :
    from sites import SITES, DEFAULT_SITE
    site_cfg = SITES["herretang"]
"""

SITES = {
    "herretang": {
        "nom":                  "Herretang — Tuilerie",
        "commune":              "Saint-Joseph-de-Rivière",
        "site_id":              100040825,
        "channel_in":           "353347292",
        "latitude":             45.38224,
        "longitude":            5.68871,
        "capacite_journaliere": None,
        "seuils_risque":        {"modere": 0.60, "eleve": 0.85},
        "zone_vacances":        "Grenoble",
        "mlflow_experiment":    "flux-touristique-poc",
        "frequentation_csv":    "herretang_2023_2025/frequentation_herretang_2023_2025.csv",
        "meteo_csv":            "herretang_2023_2025/meteo_herretang_2023_2025.csv",
    },
    "col-du-coq": {
        "nom":                  "Col du Coq — Perquelin",
        "commune":              "Saint-Hilaire",
        "site_id":              100040826,
        "channel_in":           "101040826",
        "latitude":             45.31217,
        "longitude":            5.84108,
        "capacite_journaliere": None,
        "seuils_risque":        {"modere": 0.60, "eleve": 0.85},
        "zone_vacances":        "Grenoble",
        "mlflow_experiment":    "flux-touristique-poc",
        "frequentation_csv":    None,
        "meteo_csv":            None,
    },
    "etang-serre": {
        "nom":                  "Étang de la Serre — Observatoire",
        "commune":              "Sermerieu",
        "site_id":              100042163,
        "channel_in":           "101042163",
        "latitude":             45.72695,
        "longitude":            5.42480,
        "capacite_journaliere": None,
        "seuils_risque":        {"modere": 0.60, "eleve": 0.85},
        "zone_vacances":        "Grenoble",
        "mlflow_experiment":    "flux-touristique-poc",
        "frequentation_csv":    None,
        "meteo_csv":            None,
    },
    "etang-lemps": {
        "nom":                  "Étang de Lemps — Sentier",
        "commune":              "Bouvesse-Quirieu",
        "site_id":              100042379,
        "channel_in":           "101042379",
        "latitude":             45.75944,
        "longitude":            5.35870,
        "capacite_journaliere": None,
        "seuils_risque":        {"modere": 0.60, "eleve": 0.85},
        "zone_vacances":        "Grenoble",
        "mlflow_experiment":    "flux-touristique-poc",
        "frequentation_csv":    None,
        "meteo_csv":            None,
    },
}

DEFAULT_SITE = "herretang"
