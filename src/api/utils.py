"""
Fonctions partagées entre l'entraînement (train.py) et la projection (predict.py).
"""
import logging

import pandas as pd
import requests

from config import DATA_DIR

log = logging.getLogger(__name__)


def charger_frequentation(site_cfg: dict) -> pd.DataFrame:
    path = DATA_DIR / site_cfg["frequentation_csv"]
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    df = df[df["qualite_frequentation"] == "valide"].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def agreger_journalier(df: pd.DataFrame) -> pd.DataFrame:
    cal_cols = ["weekend", "jour_ferie", "vacances_scolaires_zone_a"]
    daily = df.groupby("date").agg(
        passages_jour      = ("passages_entrants",    "sum"),
        precipitations_mm  = ("precipitations_mm",    "sum"),
        pluie_heures       = ("precipitation_oui_non","sum"),
        neige_oui_non_jour = ("neige_oui_non",        "max"),
        **{col: (col, "first") for col in cal_cols},
    ).reset_index()
    daily["mois"]         = daily["date"].dt.month
    daily["jour_semaine"] = daily["date"].dt.dayofweek
    return daily


def fetch_temperature_historique(start_date: str, end_date: str, site_cfg: dict) -> pd.DataFrame:
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={site_cfg['latitude']}&longitude={site_cfg['longitude']}"
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
