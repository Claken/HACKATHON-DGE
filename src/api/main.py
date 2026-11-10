"""
API FastAPI — Flux Touristiques CG38.

Endpoints :
  GET  /health              → état de l'API
  GET  /sites               → liste des sites disponibles
  GET  /predict/{site_id}   → projection J+7 pour un site

Les modèles sont chargés depuis MLflow au démarrage et mis en cache mémoire.
Les requêtes /predict n'accèdent plus à MLflow.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import MLFLOW as MLFLOW_CFG
from sites import SITES
from predict import charger_meilleur_modele, run_prediction

log = logging.getLogger(__name__)

# { site_id: (model, capacite) }
MODEL_CACHE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Chargement des modèles MLflow...")
    for site_id, cfg in SITES.items():
        if cfg["frequentation_csv"] is None:
            log.info("  %s — pas de données, ignoré", site_id)
            continue
        try:
            MODEL_CACHE[site_id] = charger_meilleur_modele(
                cfg, MLFLOW_CFG["uri"], MLFLOW_CFG["max_results"]
            )
            log.info("  %s — modèle chargé ✓", site_id)
        except Exception as e:
            log.warning("  %s — échec chargement : %s", site_id, e)
    log.info("API prête. %d modèle(s) en cache.", len(MODEL_CACHE))
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
            "has_data": cfg["frequentation_csv"] is not None,
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

    model, capacite = MODEL_CACHE[site_id]
    try:
        return run_prediction(
            site_id=site_id,
            site_cfg=SITES[site_id],
            model=model,
            capacite=capacite,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
