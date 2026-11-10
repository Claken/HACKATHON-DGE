"""
API FastAPI — Flux Touristiques CG38.

Endpoints :
  GET  /health              → état de l'API
  GET  /sites               → liste des sites disponibles
  GET  /predict/{site_id}   → projection J+7 pour un site
"""
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import MLFLOW as MLFLOW_CFG
from sites import SITES
from predict import run_prediction

log = logging.getLogger(__name__)

app = FastAPI(
    title="Flux Touristiques — API de prédiction",
    description="Projection de fréquentation J+7 avec indice de risque de sur-fréquentation.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sites")
def list_sites():
    return [
        {
            "id":      site_id,
            "nom":     cfg["nom"],
            "commune": cfg["commune"],
            "has_data": cfg["frequentation_csv"] is not None,
        }
        for site_id, cfg in SITES.items()
    ]


@app.get("/predict/{site_id}")
def predict(site_id: str):
    if site_id not in SITES:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' inconnu.")

    site_cfg = SITES[site_id]
    if site_cfg["frequentation_csv"] is None:
        raise HTTPException(status_code=503, detail=f"Données non disponibles pour '{site_id}'.")

    try:
        return run_prediction(
            site_id=site_id,
            site_cfg=site_cfg,
            mlflow_uri=MLFLOW_CFG["uri"],
            max_results=MLFLOW_CFG["max_results"],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
