#!/usr/bin/env python3
"""
Entraînement XGBoost + logging MLflow.

Lance 3 runs avec des hyperparamètres différents (définis dans config.py)
et enregistre les métriques, paramètres et modèles dans MLflow.

Usage :
    python src/train.py
    python src/train.py --mlflow-uri https://mon-serveur-mlflow
    python src/train.py --start-date 2023-01-01 --end-date 2024-12-31
    python src/train.py --help
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import mlflow
import mlflow.xgboost
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from config import SITE, DONNEES, MLFLOW as MLFLOW_CFG, FEATURES, HYPERPARAMETRES
from utils import charger_frequentation, agreger_journalier, fetch_temperature_historique

log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Entraîne les modèles XGBoost et les enregistre dans MLflow.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--mlflow-uri",
        default=None,
        help="URI du serveur MLflow (priorité sur la variable MLFLOW_TRACKING_URI)",
    )
    p.add_argument(
        "--start-date",
        default="2023-01-01",
        help="Début de la fenêtre météo historique (YYYY-MM-DD)",
    )
    p.add_argument(
        "--end-date",
        default="2025-12-31",
        help="Fin de la fenêtre météo historique (YYYY-MM-DD)",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Niveau de log DEBUG")
    return p.parse_args()


def run_training(mlflow_uri: str, start_date: str, end_date: str) -> None:
    """Charge les données, entraîne les runs XGBoost et les logge dans MLflow."""
    # 1. Chargement et jointure freq + météo
    freq  = charger_frequentation()
    meteo = pd.read_csv(DONNEES["meteo"], sep=";", encoding="utf-8-sig")
    df = freq.merge(
        meteo[["debut_utc", "precipitations_mm", "precipitation_oui_non", "neige_oui_non"]],
        on="debut_utc",
    )

    # 2. Agrégation journalière
    daily = agreger_journalier(df)

    # 3. Température historique (Open-Meteo archive)
    temp_df = fetch_temperature_historique(start_date, end_date)
    daily = daily.merge(temp_df, on="date", how="left")

    # 4. Features de lag
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["passages_j1"] = daily["passages_jour"].shift(1)
    daily["passages_j7"] = daily["passages_jour"].shift(7)
    # Les 7 premiers jours n'ont pas de lag complet → exclusion
    daily = daily.dropna(subset=["passages_j1", "passages_j7", "temperature_moy"])

    # 5. Split train (2023–2024) / holdout (2025)
    train   = daily[daily["date"].dt.year < 2025].copy()
    holdout = daily[daily["date"].dt.year == 2025].copy()
    log.info("Split : %d jours train (2023-2024) | %d jours holdout (2025)", len(train), len(holdout))

    X_train   = train[FEATURES].values
    y_train   = train["passages_jour"].values
    X_holdout = holdout[FEATURES].values
    y_holdout = holdout["passages_jour"].values

    # 6. Capacité journalière de référence
    capacite = SITE["capacite_journaliere"]
    if capacite is None:
        # P90 du jeu d'entraînement = "jour chargé mais pas exceptionnel"
        capacite = int(np.percentile(y_train, 90))
        log.info("Capacité estimée automatiquement : %d passages/jour (P90 train)", capacite)
    else:
        log.info("Capacité définie dans config : %d passages/jour", capacite)

    # 7. Runs MLflow
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment(MLFLOW_CFG["experiment"])
    log.info("MLflow connecté à : %s", mlflow_uri)

    seuils = SITE["seuils_risque"]

    for i, params in enumerate(HYPERPARAMETRES, 1):
        log.info("[Run %d/%d] %s", i, len(HYPERPARAMETRES), params)
        with mlflow.start_run(run_name=f"xgb-run-{i}"):
            mlflow.log_params(params)
            mlflow.log_param("features",             FEATURES)
            mlflow.log_param("site",                 SITE["nom"])
            mlflow.log_param("train_jours",          len(train))
            mlflow.log_param("holdout_jours",        len(holdout))
            mlflow.log_param("capacite_journaliere", capacite)
            mlflow.log_param("seuil_modere",         seuils["modere"])
            mlflow.log_param("seuil_eleve",          seuils["eleve"])

            model = xgb.XGBRegressor(**params, random_state=42)
            model.fit(X_train, y_train)

            preds = np.clip(model.predict(X_holdout), 0, None)
            mae   = mean_absolute_error(y_holdout, preds)
            rmse  = root_mean_squared_error(y_holdout, preds)
            # Clip y_true à 1 pour éviter une explosion du MAPE sur les jours à 0 passage.
            mape  = float(np.mean(np.abs((y_holdout - preds) / np.clip(y_holdout, 1, None))) * 100)

            mlflow.log_metric("mae_holdout",  round(mae,  2))
            mlflow.log_metric("rmse_holdout", round(rmse, 2))
            mlflow.log_metric("mape_holdout", round(mape, 2))

            # Taux de jours où la prédiction aurait déclenché le bon niveau d'alerte élevée
            vraie_charge = y_holdout / capacite
            pred_charge  = preds     / capacite
            bonne_alerte = float(np.mean(
                (vraie_charge >= seuils["eleve"]) == (pred_charge >= seuils["eleve"])
            ))
            mlflow.log_metric("precision_alerte_elevee", round(bonne_alerte, 4))

            fi = dict(zip(FEATURES, model.feature_importances_.round(4)))
            mlflow.log_dict(fi, "feature_importance.json")
            mlflow.xgboost.log_model(model, "model")

            log.info(
                "  MAE=%.1f passages/j | RMSE=%.1f | MAPE=%.1f%% | Alertes élevées correctes=%.0f%%",
                mae, rmse, mape, bonne_alerte * 100,
            )

    log.info("Terminé — ouvre MLflow UI > Experiments > %s", MLFLOW_CFG["experiment"])


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    mlflow_uri = args.mlflow_uri or MLFLOW_CFG["uri"]
    run_training(mlflow_uri=mlflow_uri, start_date=args.start_date, end_date=args.end_date)


if __name__ == "__main__":
    main()
