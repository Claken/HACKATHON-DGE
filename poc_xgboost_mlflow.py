"""
POC — Prédiction journalière de fréquentation
XGBoost + MLflow, données réelles éco-compteur Herretang 2023–2025.

Usage :
    MLFLOW_TRACKING_URI=http://<host>:<port> python3 poc_xgboost_mlflow.py
"""
import numpy as np
import pandas as pd
import requests
import mlflow
import mlflow.xgboost
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error

from config import SITE, DONNEES, MLFLOW as MLFLOW_CFG, FEATURES

# ─────────────────────────────────────────────
# 1. CHARGEMENT ET JOINTURE DES DONNÉES RÉELLES
# ─────────────────────────────────────────────
freq  = pd.read_csv(DONNEES["frequentation"], sep=";", encoding="utf-8-sig")
meteo = pd.read_csv(DONNEES["meteo"],         sep=";", encoding="utf-8-sig")

# Jointure sur la clé UTC — évite l'ambiguïté lors des changements d'heure
df = freq.merge(
    meteo[["debut_utc", "precipitations_mm", "precipitation_oui_non", "neige_oui_non"]],
    on="debut_utc",
)
df = df[df["qualite_frequentation"] == "valide"].copy()
df["date"] = pd.to_datetime(df["date"])

# ─────────────────────────────────────────────
# 2. AGRÉGATION JOURNALIÈRE
# ─────────────────────────────────────────────
# Les colonnes calendaires sont invariantes dans la journée : on prend la première valeur.
cal_cols = ["weekend", "jour_ferie", "vacances_scolaires_zone_a"]

daily = df.groupby("date").agg(
    passages_jour    = ("passages_entrants",   "sum"),
    precipitations_mm= ("precipitations_mm",   "sum"),
    pluie_heures     = ("precipitation_oui_non","sum"),
    neige_oui_non_jour=("neige_oui_non",        "max"),
    **{col: (col, "first") for col in cal_cols},
).reset_index()

daily["mois"]         = daily["date"].dt.month
daily["jour_semaine"] = daily["date"].dt.dayofweek  # 0 = lundi, 6 = dimanche

# ─────────────────────────────────────────────
# 3. TEMPÉRATURE JOURNALIÈRE (Open-Meteo historique)
# ─────────────────────────────────────────────
print("[Météo] Récupération de la température historique 2023–2025...")
url = (
    f"https://archive-api.open-meteo.com/v1/archive"
    f"?latitude={SITE['latitude']}&longitude={SITE['longitude']}"
    f"&daily=temperature_2m_mean"
    f"&start_date=2023-01-01&end_date=2025-12-31"
    f"&timezone=Europe%2FParis"
)
resp = requests.get(url, timeout=30)
resp.raise_for_status()
temp_df = pd.DataFrame({
    "date":            pd.to_datetime(resp.json()["daily"]["time"]),
    "temperature_moy": resp.json()["daily"]["temperature_2m_mean"],
})
daily = daily.merge(temp_df, on="date", how="left")

# ─────────────────────────────────────────────
# 4. FEATURES DE LAG
# ─────────────────────────────────────────────
daily = daily.sort_values("date").reset_index(drop=True)
daily["passages_j1"] = daily["passages_jour"].shift(1)
daily["passages_j7"] = daily["passages_jour"].shift(7)

# Les 7 premiers jours n'ont pas de lag complet → exclusion
daily = daily.dropna(subset=["passages_j1", "passages_j7", "temperature_moy"])

# ─────────────────────────────────────────────
# 5. SPLIT TRAIN (2023–2024) / HOLDOUT (2025)
# ─────────────────────────────────────────────
train   = daily[daily["date"].dt.year < 2025].copy()
holdout = daily[daily["date"].dt.year == 2025].copy()

print(f"[Split] Train : {len(train)} jours (2023–2024) | Holdout : {len(holdout)} jours (2025)")

X_train   = train[FEATURES].values
y_train   = train["passages_jour"].values
X_holdout = holdout[FEATURES].values
y_holdout = holdout["passages_jour"].values

# ─────────────────────────────────────────────
# 6. CAPACITÉ DE CHARGE
# ─────────────────────────────────────────────
capacite = SITE["capacite_journaliere"]
if capacite is None:
    # P90 du jeu d'entraînement = "jour chargé mais pas exceptionnel"
    capacite = int(np.percentile(y_train, 90))
    print(f"[Capacité] Estimée automatiquement : {capacite} passages/jour (P90 train)")
else:
    print(f"[Capacité] Définie dans config : {capacite} passages/jour")

# ─────────────────────────────────────────────
# 7. EXPÉRIENCES MLFLOW — 3 runs hyperparamètres
# ─────────────────────────────────────────────
mlflow.set_tracking_uri(MLFLOW_CFG["uri"])
mlflow.set_experiment(MLFLOW_CFG["experiment"])
print(f"[MLflow] connecté à : {MLFLOW_CFG['uri']}")

RUNS = [
    {"n_estimators": 100, "max_depth": 3, "learning_rate": 0.10, "subsample": 1.0},
    {"n_estimators": 300, "max_depth": 5, "learning_rate": 0.05, "subsample": 0.8},
    {"n_estimators": 500, "max_depth": 6, "learning_rate": 0.02, "subsample": 0.8},
]

seuils = SITE["seuils_risque"]

for i, params in enumerate(RUNS, 1):
    print(f"\n[Run {i}/3] {params}")
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
        rmse  = mean_squared_error(y_holdout, preds) ** 0.5
        mape  = float(np.mean(np.abs((y_holdout - preds) / np.clip(y_holdout, 1, None))) * 100)

        # Métriques sur le holdout
        mlflow.log_metric("mae_holdout",  round(mae,  2))
        mlflow.log_metric("rmse_holdout", round(rmse, 2))
        mlflow.log_metric("mape_holdout", round(mape, 2))

        # Jours où la prédiction aurait déclenché le bon niveau d'alerte
        vraie_charge  = y_holdout / capacite
        pred_charge   = preds     / capacite
        bonne_alerte  = np.mean(
            (vraie_charge >= seuils["eleve"]) == (pred_charge >= seuils["eleve"])
        )
        mlflow.log_metric("precision_alerte_elevee", round(bonne_alerte, 4))

        fi = dict(zip(FEATURES, model.feature_importances_.round(4)))
        mlflow.log_dict(fi, "feature_importance.json")
        mlflow.xgboost.log_model(model, "model")

        print(f"  MAE={mae:.1f} passages/j | RMSE={rmse:.1f} | MAPE={mape:.1f}%"
              f" | Alertes élevées correctes={bonne_alerte*100:.0f}%")

print("\n[OK] Ouvre MLflow UI > Experiments > flux-touristique-poc pour voir les 3 runs.")
