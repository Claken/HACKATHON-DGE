# Pipeline ML — Anticipation de fréquentation touristique

**Hackathon DGE — Gestion des flux touristiques | Équipe 2 | 9–10 novembre 2026**

---

## Vue d'ensemble

Le pipeline prédit la fréquentation journalière d'un site touristique à horizon J+7 et dérive un **indice de risque de sur-fréquentation** (faible / modéré / élevé) permettant aux gestionnaires de passer d'une gestion réactive à proactive.

Le POC est instancié sur le site **Herretang — Tuilerie** (Isère) avec les données réelles de l'éco-compteur piéton 2023–2025.

```
Éco-compteurs (horaire)   ─┐
Météo historique           ├─► preparer_donnees.py ─► 2 CSV horaires
Calendrier officiel       ─┘

2 CSV horaires   ─► poc_xgboost_mlflow.py ─► 3 modèles XGBoost tracés dans MLflow

Meilleur modèle MLflow ─┐
Météo prévisionnelle    ├─► poc_projection.py ─► Indice de risque J+7 + graphique
Calendrier live        ─┘
```

---

## Données d'entrée

### Fréquentation — éco-compteur ENS (SSP Cloud)

| Propriété | Valeur |
|---|---|
| Site | `100040825` — Herretang |
| Canal | `353347292` — piéton IN (Tuilerie) |
| Compteur | `X2I21055989` |
| Couverture | 2023-01-01 → 2025-12-31 (1 096 jours) |
| Granularité | Horaire |
| Lignes | 26 304 |
| Passages valides | 37 626 |
| Anomalies | 3 créneaux manquants (changements d'heure d'automne) |

### Météo — Open-Meteo

- **Historique** : API `archive-api.open-meteo.com/v1/archive`
  - Variables : `precipitation`, `snowfall` (horaires), `temperature_2m_mean` (journalière)
  - Coordonnées de grille retournées : 45.3779 N, 5.6338 E
- **Prévisionnel** : API `api.open-meteo.com/v1/forecast`
  - Variables : `temperature_2m_mean`, `precipitation_sum`, `precipitation_hours`, `snowfall_sum`
  - Horizon : 7 jours

### Calendrier officiel

| Source | Contenu |
|---|---|
| `calendrier.api.gouv.fr` | Jours fériés métropolitains |
| `data.education.gouv.fr` — `fr-en-calendrier-scolaire` | Vacances scolaires Zone A (académie Grenoble), population élèves |

---

## Étape 1 — Préparation des données (`preparer_donnees.py`)

Produit deux fichiers CSV reproductibles à partir des archives brutes.

### Traitements

1. **Lecture des archives ZIP annuelles** (2023, 2024, 2025) depuis SSP Cloud ; extraction du canal `353347292` uniquement.
2. **Alignement UTC** : toutes les horodatations sont converties en UTC pour éviter l'ambiguïté lors des changements d'heure.
3. **Qualification** : chaque créneau est marqué `valide`, `manquante` (valeur absente) ou `invalide` (valeur non entière / négative / infinie).
4. **Enrichissement calendrier** : chaque créneau reçoit `weekend`, `jour_ferie`, `vacances_scolaires_zone_a` et les libellés associés.
5. **Jointure météo** : précipitations et neige sont alignées sur le même `debut_utc` (Open-Meteo étiquette les cumuls à la fin de l'heure suivante, ce qui est corrigé).

### Contrôles d'intégrité

```
✓ 26 304 créneaux horaires (2 × 8 760 h pour 2023 et 2025 + 8 784 h pour 2024 bissextile)
✓ Clé debut_utc unique dans les deux fichiers et identique entre eux
✓ Couverture intégrale de 1 096 jours
✓ Total des passages valides : 37 626
✓ Correspondance météo complète (zéro créneau sans données météo)
✓ Pagination complète du calendrier scolaire
```

### Sorties

| Fichier | Colonnes clés |
|---|---|
| `frequentation_herretang_2023_2025.csv` | `debut_utc`, `date`, `heure`, `passages_entrants`, `qualite_frequentation`, `weekend`, `jour_ferie`, `vacances_scolaires_zone_a` |
| `meteo_herretang_2023_2025.csv` | `debut_utc`, `precipitations_mm`, `precipitation_oui_non`, `neige_tombee_cm`, `neige_oui_non` |

---

## Étape 2 — Entraînement (`poc_xgboost_mlflow.py`)

### Préprocessing

```
Données horaires
      │
      ▼
Filtre qualite_frequentation == "valide"
      │
      ▼
Agrégation journalière
  passages_jour    = sum(passages_entrants)
  precipitations_mm = sum(precipitations_mm)
  pluie_heures     = sum(precipitation_oui_non)
  neige_oui_non_jour = max(neige_oui_non)
  weekend / jour_ferie / vacances = first()
      │
      ▼
Ajout température journalière (API Open-Meteo historique)
      │
      ▼
Features de lag
  passages_j1 = passages_jour décalé de 1 jour
  passages_j7 = passages_jour décalé de 7 jours
      │
      ▼
Suppression des 7 premiers jours (lags incomplets)
```

### Split temporel

| Jeu | Période | Usage |
|---|---|---|
| Train | 2023–2024 | Entraînement du modèle |
| Holdout | 2025 | Évaluation hors-échantillon |

### Features (11 variables)

| Feature | Type | Source |
|---|---|---|
| `mois` | calendaire | date |
| `jour_semaine` | calendaire | date (0 = lundi) |
| `weekend` | calendaire | CSV fréquentation |
| `jour_ferie` | calendaire | CSV fréquentation |
| `vacances_scolaires_zone_a` | calendaire | CSV fréquentation |
| `temperature_moy` | météo | Open-Meteo historique |
| `precipitations_mm` | météo | CSV météo agrégé jour |
| `pluie_heures` | météo | CSV météo agrégé jour |
| `neige_oui_non_jour` | météo | CSV météo agrégé jour |
| `passages_j1` | lag | passages J-1 |
| `passages_j7` | lag | passages J-7 (même jour de semaine) |

### Capacité de charge

La capacité journalière sert de référence pour le calcul du taux de charge :

- **Si définie** dans `config.py` : valeur fixée avec le gestionnaire du site.
- **Sinon** : estimée automatiquement au **percentile 90** du jeu d'entraînement ("jour chargé mais pas exceptionnel").

### Hyperparamètres explorés (3 runs)

| Run | n_estimators | max_depth | learning_rate | subsample |
|-----|-------------|-----------|---------------|-----------|
| xgb-run-1 | 100 | 3 | 0.10 | 1.0 |
| xgb-run-2 | 300 | 5 | 0.05 | 0.8 |
| xgb-run-3 | 500 | 6 | 0.02 | 0.8 |

Tous les runs utilisent `random_state=42`. Les prédictions sont clampées à 0 (`np.clip(..., 0, None)`).

### Métriques

| Métrique | Description |
|---|---|
| `mae_holdout` | Erreur absolue moyenne (passages/jour) — **critère de sélection du meilleur modèle** |
| `rmse_holdout` | Racine de l'erreur quadratique moyenne |
| `mape_holdout` | Erreur relative moyenne (%) |
| `precision_alerte_elevee` | % des jours où le niveau d'alerte élevé est correctement prédit |

### Suivi MLflow

- **Experiment** : `flux-touristique-poc`
- **URI** : configurable via `MLFLOW_TRACKING_URI` (défaut : instance SSP Cloud)
- **Artefacts loggués** : paramètres, métriques, `feature_importance.json`, modèle XGBoost

### Importance des features (par run)

Les valeurs ci-dessous sont lues depuis les artefacts MLflow (`feature_importance.json`). La correspondance entre le numéro de run et l'ID de run MLflow est approximative — les IDs ne sont pas triés dans l'ordre de création.

| Feature | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| `pluie_heures` | **16.4 %** | **17.2 %** | 13.9 % |
| `temperature_moy` | 13.6 % | 14.4 % | **19.8 %** |
| `passages_j1` | 11.7 % | 11.9 % | 12.0 % |
| `precipitations_mm` | 11.1 % | 11.4 % | 8.0 % |
| `passages_j7` | 10.2 % | 10.6 % | 11.5 % |
| `jour_semaine` | 10.5 % | 10.4 % | 14.8 % |
| `vacances_scolaires_zone_a` | 13.0 % | 11.8 % | 9.0 % |
| `mois` | 9.4 % | 8.3 % | 9.7 % |
| `jour_ferie` | 3.6 % | 3.5 % | 1.0 % |
| `neige_oui_non_jour` | 0.5 % | 0.6 % | 0.3 % |
| `weekend` | 0.0 % | 0.0 % | 0.0 % |

> `weekend` est redondant avec `jour_semaine` : XGBoost lui attribue systématiquement une importance nulle.

---

## Étape 3 — Projection J+7 (`poc_projection.py`)

### Chargement du modèle

Le script sélectionne parmi les **3 runs les plus récents** de l'expérience MLflow celui qui minimise `mae_holdout`. Les runs plus anciens ne sont pas considérés.

### Construction des features pour les 7 prochains jours

```
Pour chaque jour J dans [aujourd'hui, aujourd'hui+6] :

  Météo         ← Open-Meteo forecast (temperature, precipitation, pluie_heures, neige)
  Calendrier    ← API jours fériés + API vacances scolaires (live)
  passages_j1   ← historique réel si disponible, sinon médiane de l'historique
  passages_j7   ← idem (fallback médiane si données > 30 jours anciennes)
```

### Calcul de l'indice de risque

```
taux_charge = passages_prévus / capacité_journalière

ÉLEVÉ   si taux_charge ≥ 85 %
MODÉRÉ  si taux_charge ≥ 60 %
FAIBLE  sinon
```

### Sorties

**Console :**

```
── Projection 7 jours — Herretang — Tuilerie ──
   Capacité de référence : XXX passages/jour
   Seuils : modéré ≥ 60% | élevé ≥ 85%

Jour          Passages   Charge   Risque     Temp.  Météo
──────────────────────────────────────────────────────────────
Mar 11/11          142      47%   🟢 FAIBLE    8.3°C  🌧️
...
```

**Graphique** : `projection_7j.png` — barres colorées par niveau de risque avec lignes de seuil de capacité.

---

## Configuration (`config.py`)

Tous les paramètres à adapter pour un nouveau site sont centralisés ici :

```python
SITE = {
    "nom": "Herretang — Tuilerie",
    "latitude": 45.38224,
    "longitude": 5.68871,
    "capacite_journaliere": None,         # None → P90 auto
    "seuils_risque": {"modere": 0.60, "eleve": 0.85},
}

DONNEES = {
    "frequentation": "...",
    "meteo":         "...",
}

MLFLOW = {
    "uri":         "...",
    "experiment":  "flux-touristique-poc",
    "metric_best": "mae_holdout",
}

FEATURES = [
    "mois", "jour_semaine", "weekend", "jour_ferie", "vacances_scolaires_zone_a",
    "temperature_moy", "precipitations_mm", "pluie_heures", "neige_oui_non_jour",
    "passages_j1", "passages_j7",
]
```

Pour brancher un autre site : modifier `SITE`, `DONNEES`, et optionnellement `capacite_journaliere`.

---

## Lancer le pipeline

### Prérequis

Python 3.9+ requis (`zoneinfo` est dans la stdlib depuis 3.9).

```bash
pip install xgboost scikit-learn mlflow pandas numpy requests matplotlib
```

### 1. Préparer les données

```bash
cd data/equipe_2/herretang_2023_2025
python3 preparer_donnees.py
```

Nécessite les archives SSP Cloud dans `../donnees_sspcloud/`.

### 2. Entraîner les modèles

```bash
MLFLOW_TRACKING_URI=http://<host>:<port> python3 poc_xgboost_mlflow.py
```

Lance 3 runs XGBoost et les trace dans MLflow.

### 3. Projeter à J+7

```bash
MLFLOW_TRACKING_URI=http://<host>:<port> python3 poc_projection.py
```

Affiche le tableau de risque dans le terminal et génère `projection_7j.png`.

---

## Limites connues et pistes d'évolution

| Limite | Impact | Évolution envisagée |
|---|---|---|
| Lag J-1 et J-7 non disponibles en temps réel | Fallback médiane imprécis | Recalage journalier automatique sur compteurs |
| Capacité de charge non formalisée pour la plupart des sites | Seuil d'alerte arbitraire | Calibrage par type de site avec gestionnaires |
| `weekend` redondant avec `jour_semaine` | Feature inutile | Supprimer ou remplacer par une interaction |
| Météo prévisionnelle dégradée au-delà de J+5 | Incertitude croissante | Afficher un intervalle de confiance |
| Un seul site de validation | Généralisation non prouvée | Étendre à CC Oisans (12 capteurs disponibles) |
| Pas d'événements locaux dans les features | Pics imprévus non capturés | Intégrer Apidae (6 052 événements Isère) |
