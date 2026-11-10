#!/usr/bin/env python3
"""
Projection de fréquentation à J+7 avec indice de risque.

Charge le meilleur modèle depuis MLflow, récupère les prévisions météo
et le calendrier officiel, puis prédit les 7 prochains jours.

Usage :
    python src/predict.py
    python src/predict.py --mlflow-uri https://mon-serveur-mlflow
    python src/predict.py --output outputs/ma_projection.png
    python src/predict.py --help
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import matplotlib
matplotlib.use("Agg")  # rendu hors display, compatible serveur
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import requests
import mlflow
import mlflow.xgboost

from config import SITE, MLFLOW as MLFLOW_CFG, FEATURES
from utils import charger_frequentation

log = logging.getLogger(__name__)

COULEURS = {
    "FAIBLE":  ("🟢", "steelblue",  "Faible"),
    "MODÉRÉ":  ("🟠", "darkorange", "Modéré"),
    "ÉLEVÉ":   ("🔴", "crimson",    "Élevé"),
}


def charger_meilleur_modele(mlflow_uri: str, max_results: int):
    """
    Se connecte à MLflow et retourne le modèle avec la meilleure MAE
    ainsi que la capacité journalière enregistrée lors de l'entraînement.
    """
    mlflow.set_tracking_uri(mlflow_uri)
    client     = mlflow.tracking.MlflowClient()
    experiment = client.get_experiment_by_name(MLFLOW_CFG["experiment"])
    if experiment is None:
        raise RuntimeError(
            f"Expérience '{MLFLOW_CFG['experiment']}' introuvable. "
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
        or SITE["capacite_journaliere"]
        or SITE["capacite_fallback"]
    )
    log.info("Meilleur modèle : %s  (MAE = %s passages/j)", best_run.info.run_name, mae)
    log.info("Capacité du site : %d passages/jour", capacite)

    model = mlflow.xgboost.load_model(f"runs:/{best_run.info.run_id}/model")
    return model, capacite


def construire_lags(historique: pd.Series):
    """
    Retourne une fonction lag(date, n) qui cherche la fréquentation réelle
    à date - n jours, avec un fallback si la date est hors historique.
    """
    today     = pd.Timestamp.today().normalize().tz_localize(None)
    last_date = historique.index.max()
    data_age  = (today - last_date).days

    if data_age > 30:
        # Données trop anciennes → médiane des mêmes jours comme approximation
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


def fetch_meteo_prevision() -> pd.DataFrame:
    """Récupère les prévisions météo 7 jours depuis l'API Open-Meteo forecast."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={SITE['latitude']}&longitude={SITE['longitude']}"
        f"&daily=temperature_2m_mean,precipitation_sum,precipitation_hours,snowfall_sum"
        f"&forecast_days=7&timezone=Europe%2FParis"
    )
    log.info("Prévisions 7 jours pour %s...", SITE["nom"])
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


def fetch_calendrier() -> tuple[set, list]:
    """
    Récupère les jours fériés métropolitains et les périodes de vacances
    scolaires Zone A (académie Grenoble) en paginant l'API si nécessaire.
    """
    log.info("Récupération du calendrier officiel (jours fériés + vacances)...")

    feries_resp = requests.get(
        "https://calendrier.api.gouv.fr/jours-feries/metropole.json", timeout=10
    )
    feries_resp.raise_for_status()
    feries = set(feries_resp.json().keys())

    # Pagination : l'API renvoie total_count, on boucle jusqu'à tout récupérer.
    vacances_periodes: list = []
    offset, limit = 0, 100
    while True:
        resp = requests.get(
            "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets"
            "/fr-en-calendrier-scolaire/records"
            "?where=location%3D%22Grenoble%22"
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
    """Retourne le label de risque et le ratio de charge pour un nombre de passages."""
    ratio = passages / capacite
    if ratio >= seuils["eleve"]:
        return "ÉLEVÉ",  ratio
    if ratio >= seuils["modere"]:
        return "MODÉRÉ", ratio
    return "FAIBLE", ratio


def afficher_console(df: pd.DataFrame, capacite: int, seuils: dict, site_nom: str) -> None:
    """Affiche le tableau de projection J+7 dans la console (stdout)."""
    print(f"\n── Projection 7 jours — {site_nom} ──")
    print(f"   Capacité de référence : {capacite} passages/jour")
    print(f"   Seuils : modéré ≥ {int(seuils['modere']*100)}% | élevé ≥ {int(seuils['eleve']*100)}%")
    print()
    print(f"{'Jour':<13} {'Passages':>10} {'Charge':>8}   {'Risque':<10} {'Temp.':>7}  Météo")
    print("─" * 62)
    for _, row in df.iterrows():
        ico, _, _ = COULEURS[row["risque"]]
        meteo_ico = (
            "❄️ " if row["neige_oui_non_jour"]
            else ("🌧️ " if row["pluie_heures"] > 4
            else ("🌦️ " if row["pluie_heures"] > 0
            else "☀️ "))
        )
        print(
            f"{row['date'].strftime('%a %d/%m'):<13}"
            f"{row['passages_prevus']:>10}"
            f"{row['charge']*100:>7.0f}%"
            f"   {ico} {row['risque']:<10}"
            f"{row['temperature_moy']:>6.1f}°C"
            f"  {meteo_ico}"
        )


def generer_graphique(
    df: pd.DataFrame,
    capacite: int,
    seuils: dict,
    site_nom: str,
    output: Path,
) -> None:
    """Génère et sauvegarde le graphique de projection en PNG."""
    fig, ax = plt.subplots(figsize=(14, 5))

    for _, row in df.iterrows():
        _, couleur, _ = COULEURS[row["risque"]]
        ax.bar(row["date"], row["passages_prevus"], color=couleur, alpha=0.80, width=0.75)

    ax.axhline(
        capacite,
        color="black", linestyle="--", linewidth=1.2,
        label=f"Capacité ({capacite} passages/j)",
    )
    ax.axhline(
        capacite * seuils["eleve"],
        color="crimson", linestyle=":", linewidth=1,
        label=f"Seuil élevé  ≥ {int(seuils['eleve']*100)}%", alpha=0.7,
    )
    ax.axhline(
        capacite * seuils["modere"],
        color="darkorange", linestyle=":", linewidth=1,
        label=f"Seuil modéré ≥ {int(seuils['modere']*100)}%", alpha=0.7,
    )

    patches = [
        mpatches.Patch(color="steelblue",  label="Faible"),
        mpatches.Patch(color="darkorange", label="Modéré"),
        mpatches.Patch(color="crimson",    label="Élevé"),
    ]
    legend1 = ax.legend(handles=patches, title="Risque", loc="upper left", fontsize=9)
    ax.legend(loc="upper right", fontsize=9)
    ax.add_artist(legend1)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a\n%d/%m"))
    ax.set_ylabel("Passages prévus / jour")
    ax.set_title(f"Indice de risque de sur-fréquentation — {site_nom} — J+7")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150)
    plt.close(fig)
    log.info("Graphique sauvegardé → %s", output)


def run_prediction(mlflow_uri: str, output: Path, max_results: int) -> None:
    """Orchestre le chargement du modèle, la prédiction J+7 et les sorties."""
    # 1. Modèle MLflow
    model, capacite = charger_meilleur_modele(mlflow_uri, max_results)

    # 2. Lags depuis l'historique réel
    freq       = charger_frequentation()
    historique = freq.groupby("date")["passages_entrants"].sum().sort_index()
    lag        = construire_lags(historique)

    # 3. Météo prévisionnelle J+7
    df = fetch_meteo_prevision()

    # 4. Calendrier officiel
    feries, vacances_periodes = fetch_calendrier()

    def est_vacances(date: pd.Timestamp) -> int:
        d = date.date()
        return int(any(s <= d < e for s, e in vacances_periodes))

    df["weekend"]                   = (df["date"].dt.dayofweek >= 5).astype(int)
    df["jour_ferie"]                = df["date"].dt.strftime("%Y-%m-%d").isin(feries).astype(int)
    df["vacances_scolaires_zone_a"] = df["date"].apply(est_vacances)
    df["mois"]                      = df["date"].dt.month
    df["jour_semaine"]              = df["date"].dt.dayofweek

    # 5. Features de lag (depuis l'historique réel)
    df["passages_j1"] = df["date"].apply(lambda d: lag(d, 1))
    df["passages_j7"] = df["date"].apply(lambda d: lag(d, 7))

    # 6. Prédiction
    X = df[FEATURES].values
    df["passages_prevus"] = np.clip(model.predict(X), 0, None).round().astype(int)

    # 7. Indice de risque
    seuils = SITE["seuils_risque"]
    df[["risque", "charge"]] = df["passages_prevus"].apply(
        lambda p: pd.Series(niveau_risque(p, capacite, seuils))
    )

    # 8. Sorties
    afficher_console(df, capacite, seuils, SITE["nom"])
    generer_graphique(df, capacite, seuils, SITE["nom"], output)


def parse_args() -> argparse.Namespace:
    default_output = Path(__file__).parent / "outputs" / "projection_7j.png"
    p = argparse.ArgumentParser(
        description="Projette la fréquentation à J+7 à partir du meilleur modèle MLflow.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--mlflow-uri",
        default=None,
        help="URI du serveur MLflow (priorité sur MLFLOW_TRACKING_URI)",
    )
    p.add_argument(
        "--output", "-o",
        default=str(default_output),
        help="Chemin de sortie du graphique PNG",
    )
    p.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Nombre de runs MLflow à considérer pour sélectionner le meilleur modèle",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Niveau de log DEBUG")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    mlflow_uri  = args.mlflow_uri or MLFLOW_CFG["uri"]
    output      = Path(args.output)
    max_results = args.max_results or MLFLOW_CFG["max_results"]
    run_prediction(mlflow_uri=mlflow_uri, output=output, max_results=max_results)


if __name__ == "__main__":
    main()
