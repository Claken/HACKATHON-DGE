"""
Paramètres centralisés — modifier ici pour adapter à un autre site.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent

SITE = {
    "nom": "Herretang — Tuilerie",
    "latitude": 45.38224,
    "longitude": 5.68871,
    # None → estimée automatiquement au P90 de l'historique d'entraînement.
    # Pour surcharger : fixer un entier défini avec le gestionnaire du site.
    "capacite_journaliere": None,
    # Valeur de secours si aucune capacité n'est disponible (ni config ni run MLflow).
    "capacite_fallback": 300,
    # Seuils de charge : modéré au-delà de 60 %, élevé au-delà de 85 %.
    "seuils_risque": {"modere": 0.60, "eleve": 0.85},
}

DONNEES = {
    "frequentation": ROOT / "data/herretang_2023_2025/frequentation_herretang_2023_2025.csv",
    "meteo":         ROOT / "data/herretang_2023_2025/meteo_herretang_2023_2025.csv",
}

MLFLOW = {
    "uri":         os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{ROOT / 'mlflow.db'}"),
    "experiment":  "flux-touristique-poc",
    "metric_best": "mae_holdout",
    # Nombre de runs récents à considérer pour sélectionner le meilleur modèle.
    "max_results": 10,
}

# Liste de features identique à l'entraînement et à la projection.
FEATURES = [
    "mois", "jour_semaine", "weekend", "jour_ferie", "vacances_scolaires_zone_a",
    "temperature_moy", "precipitations_mm", "pluie_heures", "neige_oui_non_jour",
    "passages_j1", "passages_j7",
]

# Hyperparamètres des 3 runs XGBoost lancés à chaque entraînement.
HYPERPARAMETRES = [
    {"n_estimators": 100, "max_depth": 3, "learning_rate": 0.10, "subsample": 1.0},
    {"n_estimators": 300, "max_depth": 5, "learning_rate": 0.05, "subsample": 0.8},
    {"n_estimators": 500, "max_depth": 6, "learning_rate": 0.02, "subsample": 0.8},
]
