"""
API FastAPI — Flux Touristiques CG38.

Endpoints :
  GET  /health              → état de l'API
  GET  /sites               → liste des sites disponibles
  GET  /predict/{site_id}   → projection J+7 pour un site

Au démarrage : modèle XGBoost + historique CSV + calendrier chargés en cache par site.
Les requêtes /predict n'accèdent ni à MLflow ni aux APIs calendrier.
Seul Open-Meteo (météo J+7) est appelé à chaque prédiction.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import pandas as pd

from config import MLFLOW as MLFLOW_CFG, DATA_DIR
from sites import SITES
from predict import charger_meilleur_modele, charger_calendrier_local, run_prediction

log = logging.getLogger(__name__)

# { site_id: (model, capacite, historique, feries, vacances_periodes) }
MODEL_CACHE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Chargement des modèles et données statiques...")
    for site_id, cfg in SITES.items():
        if cfg.get("journalier_csv") is None:
            log.info("  %s — pas de données, ignoré", site_id)
            continue
        try:
            model, capacite = charger_meilleur_modele(
                cfg, MLFLOW_CFG["uri"], MLFLOW_CFG["max_results"]
            )
            df_j = pd.read_csv(DATA_DIR / cfg["journalier_csv"], sep=";", encoding="utf-8-sig")
            df_j["date"] = pd.to_datetime(df_j["date"])
            df_j = df_j[df_j["jour_complet"] == 1]
            historique = df_j.set_index("date")["passages_jour"].sort_index()
            feries, vacances_periodes = charger_calendrier_local()
            MODEL_CACHE[site_id] = (model, capacite, historique, feries, vacances_periodes)
            log.info("  %s — prêt ✓", site_id)
        except Exception as e:
            log.warning("  %s — échec chargement : %s", site_id, e)
    log.info("API prête. %d site(s) en cache.", len(MODEL_CACHE))
    yield
    MODEL_CACHE.clear()


app = FastAPI(
    title="Flux Touristiques — API de prédiction",
    description="Projection de fréquentation J+7 avec indice de risque de sur-fréquentation.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "modeles_en_cache": list(MODEL_CACHE.keys()),
    }


@app.get("/sites")
def list_sites():
    return [
        {
            "id":       site_id,
            "nom":      cfg["nom"],
            "commune":  cfg["commune"],
            "has_data": cfg.get("journalier_csv") is not None,
            "ready":    site_id in MODEL_CACHE,
        }
        for site_id, cfg in SITES.items()
    ]


@app.get("/predict/{site_id}")
def predict(site_id: str):
    if site_id not in SITES:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' inconnu.")

    if site_id not in MODEL_CACHE:
        raise HTTPException(status_code=503, detail=f"Modèle non disponible pour '{site_id}'.")

    model, capacite, historique, feries, vacances_periodes = MODEL_CACHE[site_id]
    try:
        return run_prediction(
            site_id=site_id,
            site_cfg=SITES[site_id],
            model=model,
            capacite=capacite,
            historique=historique,
            feries=feries,
            vacances_periodes=vacances_periodes,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
