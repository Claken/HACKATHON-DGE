# Flux touristique — POC prédiction fréquentation

Prédiction journalière de fréquentation et indice de risque de sur-fréquentation
à J+7, basé sur XGBoost + MLflow. Site pilote : Herretang — Tuilerie (Isère).

## Prérequis

- Python 3.10+
- Accès réseau (APIs Open-Meteo, calendrier.api.gouv.fr, data.education.gouv.fr)
- Un serveur MLflow (local SQLite par défaut, distant via `.env`)

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

```bash
cp .env.example .env
# Éditer .env pour renseigner MLFLOW_TRACKING_URI si nécessaire
```

Sans `.env`, un fichier `src/mlflow.db` est créé localement.

## Utilisation

Toutes les commandes s'exécutent **depuis la racine du dépôt**.

### 1. Entraînement

```bash
python src/train.py
```

Lance 3 runs XGBoost et les enregistre dans MLflow.

Options :

```
--mlflow-uri URI      Serveur MLflow (priorité sur MLFLOW_TRACKING_URI)
--start-date DATE     Début fenêtre météo historique  [défaut : 2023-01-01]
--end-date DATE       Fin fenêtre météo historique    [défaut : 2025-12-31]
--verbose, -v         Logs DEBUG
```

### 2. Projection J+7

```bash
python src/predict.py
```

Charge le meilleur modèle MLflow, récupère les prévisions météo et affiche
la projection dans la console. Le graphique est sauvegardé dans `src/outputs/`.

Options :

```
--mlflow-uri URI      Serveur MLflow
--output, -o PATH     Chemin du graphique PNG  [défaut : src/outputs/projection_7j.png]
--max-results N       Runs MLflow à considérer [défaut : 10]
--verbose, -v         Logs DEBUG
```

### 3. Interface MLflow

```bash
mlflow ui --backend-store-uri sqlite:///src/mlflow.db
# Ouvrir http://localhost:5000
```

## Structure

```
src/
├── config.py          Paramètres centralisés (site, chemins, MLflow)
├── utils.py           Fonctions partagées (chargement CSV, agrégation, météo archive)
├── train.py           Entraînement XGBoost + logging MLflow
├── predict.py         Projection J+7 + graphique
├── data/
│   └── herretang_2023_2025/
│       ├── frequentation_herretang_2023_2025.csv
│       ├── meteo_herretang_2023_2025.csv
│       └── README.md   Documentation des colonnes et sources
└── outputs/           Graphiques générés (gitignorés)
```

## Données

Voir [`src/data/herretang_2023_2025/README.md`](data/herretang_2023_2025/README.md)
pour la description des colonnes, des sources et des précautions d'usage.
