#!/usr/bin/env python3
"""
Projection de fréquentation à J+7 avec indice de risque.

Charge le meilleur modèle depuis MLflow, récupère les prévisions météo
et le calendrier officiel, puis prédit les 7 prochains jours.

Usage CLI :
    python predict.py --site herretang
    python predict.py --site herretang --mlflow-uri https://mon-serveur-mlflow
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import requests
import mlflow
import mlflow.xgboost

from config import MLFLOW as MLFLOW_CFG, FEATURES
from sites import SITES, DEFAULT_SITE
from utils import charger_frequentation

log = logging.getLogger(__name__)

COULEURS = {
    "FAIBLE":  ("🟢", "steelblue",  "Faible"),
    "MODÉRÉ":  ("🟠", "darkorange", "Modéré"),
    "ÉLEVÉ":   ("🔴", "crimson",    "Élevé"),
}


def charger_meilleur_modele(site_cfg: dict, mlflow_uri: str, max_results: int):
    mlflow.set_tracking_uri(mlflow_uri)
    client     = mlflow.tracking.MlflowClient()
    experiment = client.get_experiment_by_name(site_cfg["mlflow_experiment"])
    if experiment is None:
        raise RuntimeError(
            f"Expérience '{site_cfg['mlflow_experiment']}' introuvable. "
            "Lancez d'abord train.py."
        )
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["start_time DESC"],
        max_results=max_results,
    )
    if not runs:
        raise RuntimeError("Aucun run trouvé. Lancez d'abord train.py.")

    best_run = min(runs, key=lambda r: r.data.metrics.get(MLFLOW_CFG["metric_best"], float("inf")))
    mae      = best_run.data.metrics.get(MLFLOW_CFG["metric_best"], "?")
    capacite = int(
        best_run.data.params.get("capacite_journaliere")
        or site_cfg.get("capacite_journaliere")
        or 300
    )
    log.info("Meilleur modèle : %s  (MAE = %s passages/j)", best_run.info.run_name, mae)
    log.info("Capacité du site : %d passages/jour", capacite)

    model = mlflow.xgboost.load_model(f"runs:/{best_run.info.run_id}/model")
    return model, capacite


def construire_lags(historique: pd.Series):
    today     = pd.Timestamp.today().normalize().tz_localize(None)
    last_date = historique.index.max()
    data_age  = (today - last_date).days

    if data_age > 30:
        fallback = historique.median()
        log.warning(
            "Données historiques antérieures de %d j → fallback médiane (%.0f passages/j)",
            data_age, fallback,
        )
    else:
        fallback = historique.mean()

    def lag(date: pd.Timestamp, n: int) -> float:
        cible = date - pd.Timedelta(days=n)
        return float(historique.get(cible, fallback))

    return lag


def fetch_meteo_prevision(site_cfg: dict) -> pd.DataFrame:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={site_cfg['latitude']}&longitude={site_cfg['longitude']}"
        f"&daily=temperature_2m_mean,precipitation_sum,precipitation_hours,snowfall_sum"
        f"&forecast_days=7&timezone=Europe%2FParis"
    )
    log.info("Prévisions 7 jours pour %s...", site_cfg["nom"])
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    w = resp.json()["daily"]
    return pd.DataFrame({
        "date":               pd.to_datetime(w["time"]),
        "temperature_moy":    w["temperature_2m_mean"],
        "precipitations_mm":  w["precipitation_sum"],
        "pluie_heures":       w["precipitation_hours"],
        "neige_oui_non_jour": [int(s > 0) if s else 0 for s in w["snowfall_sum"]],
    })


def fetch_calendrier(zone_vacances: str = "Grenoble") -> tuple[set, list]:
    log.info("Récupération du calendrier officiel (jours fériés + vacances)...")
    feries_resp = requests.get(
        "https://calendrier.api.gouv.fr/jours-feries/metropole.json", timeout=10
    )
    feries_resp.raise_for_status()
    feries = set(feries_resp.json().keys())

    vacances_periodes: list = []
    offset, limit = 0, 100
    while True:
        resp = requests.get(
            "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets"
            "/fr-en-calendrier-scolaire/records"
            f"?where=location%3D%22{zone_vacances}%22"
            "%20AND%20(population%3D%22-%22%20OR%20population%3D%22%C3%89l%C3%A8ves%22)"
            f"&limit={limit}&offset={offset}",
            timeout=10,
        )
        if not resp.ok:
            log.warning(
                "Impossible de récupérer les vacances scolaires (HTTP %s) — indicateur mis à 0",
                resp.status_code,
            )
            break
        data        = resp.json()
        results     = data.get("results", [])
        total_count = data.get("total_count", 0)
        for r in results:
            start = pd.to_datetime(r["start_date"]).date()
            end   = pd.to_datetime(r["end_date"]).date()
            vacances_periodes.append((start, end))
        offset += limit
        if offset >= total_count or not results:
            break

    return feries, vacances_periodes


def niveau_risque(passages: int, capacite: int, seuils: dict) -> tuple[str, float]:
    ratio = passages / capacite
    if ratio >= seuils["eleve"]:
        return "ÉLEVÉ",  ratio
    if ratio >= seuils["modere"]:
        return "MODÉRÉ", ratio
    return "FAIBLE", ratio


def run_prediction(site_id: str, site_cfg: dict, mlflow_uri: str, max_results: int) -> dict:
    """
    Orchestre la prédiction J+7 et retourne un dict JSON-sérialisable.
    Appelable depuis la CLI (main) ou depuis l'API FastAPI (main.py).
    """
    model, capacite = charger_meilleur_modele(site_cfg, mlflow_uri, max_results)

    freq       = charger_frequentation(site_cfg)
    historique = freq.groupby("date")["passages_entrants"].sum().sort_index()
    lag        = construire_lags(historique)

    df = fetch_meteo_prevision(site_cfg)
    feries, vacances_periodes = fetch_calendrier(site_cfg.get("zone_vacances", "Grenoble"))

    def est_vacances(date: pd.Timestamp) -> int:
        d = date.date()
        return int(any(s <= d < e for s, e in vacances_periodes))

    df["weekend"]                   = (df["date"].dt.dayofweek >= 5).astype(int)
    df["jour_ferie"]                = df["date"].dt.strftime("%Y-%m-%d").isin(feries).astype(int)
    df["vacances_scolaires_zone_a"] = df["date"].apply(est_vacances)
    df["mois"]                      = df["date"].dt.month
    df["jour_semaine"]              = df["date"].dt.dayofweek
    df["passages_j1"]               = df["date"].apply(lambda d: lag(d, 1))
    df["passages_j7"]               = df["date"].apply(lambda d: lag(d, 7))

    X = df[FEATURES].values
    df["passages_prevus"] = np.clip(model.predict(X), 0, None).round().astype(int)

    seuils = site_cfg["seuils_risque"]
    df[["risque", "charge"]] = df["passages_prevus"].apply(
        lambda p: pd.Series(niveau_risque(p, capacite, seuils))
    )

    return {
        "site": {
            "id":      site_id,
            "nom":     site_cfg["nom"],
            "commune": site_cfg["commune"],
        },
        "capacite": capacite,
        "seuils_abs": {
            "modere": int(capacite * seuils["modere"]),
            "eleve":  int(capacite * seuils["eleve"]),
        },
        "predictions": [
            {
                "date":              row["date"].strftime("%Y-%m-%d"),
                "passages_prevus":   int(row["passages_prevus"]),
                "risque":            row["risque"],
                "charge":            round(float(row["charge"]), 3),
                "temperature_moy":   round(float(row["temperature_moy"]), 1),
                "precipitations_mm": round(float(row["precipitations_mm"]), 1),
                "pluie_heures":      round(float(row["pluie_heures"]), 1),
                "neige":             bool(row["neige_oui_non_jour"]),
                "weekend":           bool(row["weekend"]),
                "jour_ferie":        bool(row["jour_ferie"]),
                "vacances":          bool(row["vacances_scolaires_zone_a"]),
            }
            for _, row in df.iterrows()
        ],
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Projette la fréquentation à J+7 (sortie JSON sur stdout).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--site",        default=DEFAULT_SITE, choices=list(SITES.keys()))
    p.add_argument("--mlflow-uri",  default=None)
    p.add_argument("--max-results", type=int, default=None)
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main() -> None:
    import json
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    mlflow_uri  = args.mlflow_uri or MLFLOW_CFG["uri"]
    max_results = args.max_results or MLFLOW_CFG["max_results"]
    result = run_prediction(args.site, SITES[args.site], mlflow_uri, max_results)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
