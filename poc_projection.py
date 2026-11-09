"""
POC — Projection de fréquentation à J+7 avec indice de risque
Charge le meilleur modèle depuis MLflow et prédit les 7 prochains jours.

Usage :
    MLFLOW_TRACKING_URI=http://<host>:<port> python3 poc_projection.py
"""
import numpy as np
import pandas as pd
import requests
import mlflow
import mlflow.xgboost
import matplotlib
matplotlib.use("Agg")  # pas de fenêtre graphique, compatible serveur sans display
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
from pathlib import Path

from config import SITE, DONNEES, MLFLOW as MLFLOW_CFG, FEATURES

# ─────────────────────────────────────────────
# 1. CHARGEMENT DU MEILLEUR MODÈLE MLFLOW
# ─────────────────────────────────────────────
mlflow.set_tracking_uri(MLFLOW_CFG["uri"])
client     = mlflow.tracking.MlflowClient()
experiment = client.get_experiment_by_name(MLFLOW_CFG["experiment"])
if experiment is None:
    raise RuntimeError(
        f"Expérience '{MLFLOW_CFG['experiment']}' introuvable. "
        "Lancez d'abord poc_xgboost_mlflow.py."
    )

runs = client.search_runs(
    experiment_ids=[experiment.experiment_id],
    order_by=["start_time DESC"],
    max_results=3,
)
if not runs:
    raise RuntimeError("Aucun run trouvé. Lancez d'abord poc_xgboost_mlflow.py.")

best_run = min(runs, key=lambda r: r.data.metrics.get(MLFLOW_CFG["metric_best"], float("inf")))
mae      = best_run.data.metrics.get(MLFLOW_CFG["metric_best"], "?")
# Capacité enregistrée lors de l'entraînement (ou fallback config)
capacite = int(best_run.data.params.get("capacite_journaliere") or SITE["capacite_journaliere"] or 300)
print(f"[MLflow] Meilleur modèle : {best_run.info.run_name}  (MAE = {mae} passages/j)")
print(f"[MLflow] Capacité du site : {capacite} passages/jour")

model = mlflow.xgboost.load_model(f"runs:/{best_run.info.run_id}/model")

# ─────────────────────────────────────────────
# 2. DONNÉES RÉCENTES POUR LES FEATURES DE LAG
# ─────────────────────────────────────────────
# On reconstruit le total journalier des derniers jours connus
# pour alimenter passages_j1 et passages_j7.
freq = pd.read_csv(DONNEES["frequentation"], sep=";", encoding="utf-8-sig")
freq = freq[freq["qualite_frequentation"] == "valide"].copy()
freq["date"] = pd.to_datetime(freq["date"])

historique = (
    freq.groupby("date")["passages_entrants"]
    .sum()
    .sort_index()
)

last_date  = historique.index.max()
today      = pd.Timestamp.today().normalize().tz_localize(None)
data_age   = (today - last_date).days

if data_age > 30:
    # Le dataset est antérieur à "aujourd'hui" : on utilise la médiane
    # des mêmes jours de l'année passée comme approximation des lags.
    fallback = historique.median()
    print(f"[Lag] Données historiques antérieures de {data_age} j → fallback médiane ({fallback:.0f} passages/j)")
else:
    fallback = historique.mean()

def lag(date, n):
    cible = date - pd.Timedelta(days=n)
    return float(historique.get(cible, fallback))

# ─────────────────────────────────────────────
# 3. MÉTÉO PRÉVISIONNELLE J+7 (Open-Meteo)
# ─────────────────────────────────────────────
print(f"\n[Météo] Prévisions 7 jours pour {SITE['nom']}...")
url = (
    f"https://api.open-meteo.com/v1/forecast"
    f"?latitude={SITE['latitude']}&longitude={SITE['longitude']}"
    f"&daily=temperature_2m_mean,precipitation_sum,precipitation_hours,snowfall_sum"
    f"&forecast_days=7&timezone=Europe%2FParis"
)
resp = requests.get(url, timeout=15)
resp.raise_for_status()
w = resp.json()["daily"]

df = pd.DataFrame({
    "date":             pd.to_datetime(w["time"]),
    "temperature_moy":  w["temperature_2m_mean"],
    "precipitations_mm":w["precipitation_sum"],
    "pluie_heures":     w["precipitation_hours"],
    "neige_oui_non_jour":[int(s > 0) if s else 0 for s in w["snowfall_sum"]],
})

# ─────────────────────────────────────────────
# 4. CALENDRIER OFFICIEL J+7
# ─────────────────────────────────────────────
print("[Calendrier] Jours fériés et vacances scolaires...")

# Jours fériés métropolitains
feries_resp = requests.get(
    "https://calendrier.api.gouv.fr/jours-feries/metropole.json", timeout=10
)
feries_resp.raise_for_status()
feries = set(feries_resp.json().keys())

# Vacances scolaires Zone A (académie Grenoble)
vac_resp = requests.get(
    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets"
    "/fr-en-calendrier-scolaire/records"
    "?where=location%3D%22Grenoble%22"
    "%20AND%20(population%3D%22-%22%20OR%20population%3D%22%C3%89l%C3%A8ves%22)"
    "&limit=100",
    timeout=10,
)
vacances_periodes = []
if vac_resp.ok:
    for r in vac_resp.json().get("results", []):
        start = pd.to_datetime(r["start_date"]).date()
        end   = pd.to_datetime(r["end_date"]).date()
        vacances_periodes.append((start, end))

def est_vacances(date):
    d = date.date()
    return int(any(s <= d < e for s, e in vacances_periodes))

df["weekend"]                   = (df["date"].dt.dayofweek >= 5).astype(int)
df["jour_ferie"]                = df["date"].dt.strftime("%Y-%m-%d").isin(feries).astype(int)
df["vacances_scolaires_zone_a"] = df["date"].apply(est_vacances)
df["mois"]                      = df["date"].dt.month
df["jour_semaine"]              = df["date"].dt.dayofweek

# ─────────────────────────────────────────────
# 5. FEATURES DE LAG (depuis l'historique réel)
# ─────────────────────────────────────────────
df["passages_j1"] = df["date"].apply(lambda d: lag(d, 1))
df["passages_j7"] = df["date"].apply(lambda d: lag(d, 7))

# ─────────────────────────────────────────────
# 6. PRÉDICTION
# ─────────────────────────────────────────────
X = df[FEATURES].values
df["passages_prevus"] = np.clip(model.predict(X), 0, None).round().astype(int)

# ─────────────────────────────────────────────
# 7. INDICE DE RISQUE
# ─────────────────────────────────────────────
# Ratio passages_prévus / capacité → trois niveaux de charge.
seuils = SITE["seuils_risque"]

COULEURS = {
    "FAIBLE":  ("🟢", "steelblue",  "faible"),
    "MODÉRÉ":  ("🟠", "darkorange", "modéré"),
    "ÉLEVÉ":   ("🔴", "crimson",    "élevé"),
}

def niveau_risque(passages):
    ratio = passages / capacite
    if ratio >= seuils["eleve"]:
        return "ÉLEVÉ",   ratio
    if ratio >= seuils["modere"]:
        return "MODÉRÉ",  ratio
    return "FAIBLE", ratio

df[["risque", "charge"]] = df["passages_prevus"].apply(
    lambda p: pd.Series(niveau_risque(p))
)

# ─────────────────────────────────────────────
# 8. RÉSUMÉ CONSOLE
# ─────────────────────────────────────────────
print(f"\n── Projection 7 jours — {SITE['nom']} ──")
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

# ─────────────────────────────────────────────
# 9. GRAPHIQUE
# ─────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 5))

for _, row in df.iterrows():
    _, couleur, _ = COULEURS[row["risque"]]
    ax.bar(row["date"], row["passages_prevus"], color=couleur, alpha=0.80, width=0.75)

# Lignes de seuil
ax.axhline(capacite,
           color="black",      linestyle="--", linewidth=1.2,
           label=f"Capacité ({capacite} passages/j)")
ax.axhline(capacite * seuils["eleve"],
           color="crimson",    linestyle=":",  linewidth=1,
           label=f"Seuil élevé  ≥ {int(seuils['eleve']*100)}%", alpha=0.7)
ax.axhline(capacite * seuils["modere"],
           color="darkorange", linestyle=":",  linewidth=1,
           label=f"Seuil modéré ≥ {int(seuils['modere']*100)}%", alpha=0.7)

# Légende couleur risque
patches = [
    mpatches.Patch(color="steelblue",  label="Faible"),
    mpatches.Patch(color="darkorange", label="Modéré"),
    mpatches.Patch(color="crimson",    label="Élevé"),
]
legend1 = ax.legend(handles=patches, title="Risque", loc="upper left",  fontsize=9)
ax.legend(loc="upper right", fontsize=9)
ax.add_artist(legend1)

ax.xaxis.set_major_formatter(mdates.DateFormatter("%a\n%d/%m"))
ax.set_ylabel("Passages prévus / jour")
ax.set_title(f"Indice de risque de sur-fréquentation — {SITE['nom']} — J+7")
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()

output = Path(__file__).parent / "projection_7j.png"
plt.savefig(output, dpi=150)
print(f"\n[OK] Graphique sauvegardé → {output}")
