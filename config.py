"""
Paramètres centralisés — modifier ici pour adapter à un autre site.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SITE = {
    "nom": "Herretang — Tuilerie",
    "latitude": 45.38224,
    "longitude": 5.68871,
    # Capacité journalière en passages.
    # None → estimée automatiquement au P90 de l'historique d'entraînement.
    # Pour surcharger : fixer un entier défini avec le gestionnaire du site.
    "capacite_journaliere": None,
    # Seuils de charge : modéré au-delà de 60 %, élevé au-delà de 85 %.
    "seuils_risque": {"modere": 0.60, "eleve": 0.85},
}

DONNEES = {
    "frequentation": ROOT / "data/equipe_2/herretang_2023_2025/frequentation_herretang_2023_2025.csv",
    "meteo":         ROOT / "data/equipe_2/herretang_2023_2025/meteo_herretang_2023_2025.csv",
}

MLFLOW = {
    "uri":        os.getenv("MLFLOW_TRACKING_URI", "https://user-nviricelexterne-mlflow.user.lab.sspcloud.fr/"),
    "experiment": "flux-touristique-poc",
    "metric_best": "mae_holdout",
}

# Liste de features identique à l'entraînement et à la projection.
FEATURES = [
    "mois", "jour_semaine", "weekend", "jour_ferie", "vacances_scolaires_zone_a",
    "temperature_moy", "precipitations_mm", "pluie_heures", "neige_oui_non_jour",
    "passages_j1", "passages_j7",
]
