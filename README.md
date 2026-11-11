# antaudiro

**Hackathon DGE — Gestion des flux touristiques (9–10 novembre 2026) · Équipe 2**

Outil d’anticipation de la fréquentation pour les espaces naturels sensibles de l’Isère.
Chaque matin (ou à la demande), **antaudiro** prévoit l’affluence des **7 prochains jours**
sur un site équipé d’un éco-compteur, puis la traduit en **niveaux de vigilance**
(faible / modérée / élevée) pour aider les gestionnaires à agir avant le pic.

## Contenu du dépôt

| Dossier | Contenu |
|---|---|
| [`src/`](src/) | Application complète : API FastAPI, frontend Nuxt 4, données, Docker, docs |
| [`livrable/`](livrable/) | Livrables de présentation (slides équipe 2, document de cadrage) |
| Scripts `.R` à la racine | Aides fournies par les organisateurs (Apidae, DATAtourisme, OSM, IGN, etc.) |

La documentation technique et les commandes de lancement sont dans
[`src/README.md`](src/README.md).

## Démarrage rapide

```bash
cd src
cp .env.example .env   # optionnel : MLflow distant
docker compose up --build
```

Puis ouvrir **http://localhost** (reverse proxy Caddy : UI + API sous `/api`).

## Sites couverts

Sept accès ENS (CG38 Environnement), séries journalières **2020–2025** :

- Herretang — Tuilerie
- Marais de la Véronnière
- Écouges — Pont Chabert
- Étang de la Serre — observatoire
- Étang de Lemps — sentier / observatoire
- Lac de Save — ouest

## Pipeline (résumé)

1. **Apprentissage** — un modèle XGBoost par site, entraîné sur **2022–2024**
   (météo, calendrier, lags J-1 / J-7 / J-365 ; années COVID exclues).
2. **Vérification** — holdout **2025** ; 3 réglages comparés, meilleur run retenu.
3. **Prévision** — météo Open-Meteo + calendrier → API JSON à J+7.
4. **Tableau de bord** — vigilance, seuils réglables, historique, page de performance.

Détails : [`src/docs/pipeline_ml.md`](src/docs/pipeline_ml.md),
[`src/docs/architecture.md`](src/docs/architecture.md),
[`src/docs/validation_modele.md`](src/docs/validation_modele.md).

## Livrable

- [`livrable/Equipe 2 - Slides.pptx`](livrable/Equipe%202%20-%20Slides.pptx) — présentation jury
- [`livrable/Hackathon_DGE.docx`](livrable/Hackathon_DGE.docx) — document associé
