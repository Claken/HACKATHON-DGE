"""
Fonctions partagées entre l'entraînement (train.py) et la projection (predict.py).
"""
import logging

import pandas as pd
import requests

from config import DONNEES, SITE

log = logging.getLogger(__name__)


def charger_frequentation() -> pd.DataFrame:
    """Charge le CSV de fréquentation et ne conserve que les lignes valides."""
    df = pd.read_csv(DONNEES["frequentation"], sep=";", encoding="utf-8-sig")
    df = df[df["qualite_frequentation"] == "valide"].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def agreger_journalier(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrège les données horaires freq+météo en un DataFrame journalier.

    Le DataFrame en entrée doit être issu de la jointure freq ⋈ météo sur debut_utc
    et ne contenir que les lignes de qualité valide.
    """
    cal_cols = ["weekend", "jour_ferie", "vacances_scolaires_zone_a"]
    daily = df.groupby("date").agg(
        passages_jour      = ("passages_entrants",    "sum"),
        precipitations_mm  = ("precipitations_mm",    "sum"),
        pluie_heures       = ("precipitation_oui_non","sum"),
        neige_oui_non_jour = ("neige_oui_non",        "max"),
        **{col: (col, "first") for col in cal_cols},
    ).reset_index()
    daily["mois"]         = daily["date"].dt.month
    daily["jour_semaine"] = daily["date"].dt.dayofweek  # 0 = lundi, 6 = dimanche
    return daily


def fetch_temperature_historique(start_date: str, end_date: str) -> pd.DataFrame:
    """Récupère la température journalière moyenne via l'API Open-Meteo archive."""
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={SITE['latitude']}&longitude={SITE['longitude']}"
        f"&daily=temperature_2m_mean"
        f"&start_date={start_date}&end_date={end_date}"
        f"&timezone=Europe%2FParis"
    )
    log.info("Récupération température historique %s → %s", start_date, end_date)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return pd.DataFrame({
        "date":            pd.to_datetime(resp.json()["daily"]["time"]),
        "temperature_moy": resp.json()["daily"]["temperature_2m_mean"],
    })
