# Fiche POC — Anticipation des flux touristiques en Isère

**Hackathon DGE — Gestion des flux touristiques | Équipe 2 | 9-10 novembre 2026**

---

## Problème

Les gestionnaires de sites touristiques (zones naturelles, sites culturels, équipements sportifs) sont aujourd'hui **réactifs** : ils constatent la sur-fréquentation quand elle est déjà là. À ce stade, les conséquences sont souvent engagées — accidents en montagne, végétation alpine piétinée, patrimoine dégradé. Ils n'ont aucun outil pour voir venir.

---

## Objectif

Fournir aux gestionnaires de sites un **outil générique d'anticipation des seuils de capacité de charge**, applicable à tout type de site touristique, pour leur permettre de passer de réactif à proactif et de déclencher des mesures de régulation **avant** que les seuils critiques soient atteints.

---

## Angle : la sécurité comme fil rouge

La sur-fréquentation produit des conséquences **irréversibles** sur trois dimensions :

| Dimension | Exemples concrets |
|---|---|
| **Sécurité des personnes** | Accidents en montagne, noyades, évacuations d'urgence |
| **Sécurité de l'environnement** | Végétation alpine piétinée (années de régénération), faune dérangée en période sensible |
| **Sécurité du patrimoine** | Usure accélérée de monuments, dégradations liées à la foule |

---

## Périmètre du POC

- **Sites couverts** : tout type de site touristique en Isère (zones naturelles, lacs, sentiers, sites culturels, équipements sportifs)
- **Utilisateur cible** : gestionnaire de site
- **Sortie** : indice de risque de sur-fréquentation à J+7, par site, avec niveau d'alerte (faible / modéré / élevé)
- **Horizon** : prévision à 7 jours
- **Territoire** : Isère (département 38)

---

## Architecture

```
Données d'entrée              Moteur                  Sortie
──────────────────            ──────────────           ─────────────────────
Météo prévisionnelle    ──►                            Indice de risque J+7
Calendrier              ──►   Modèle générique   ──►  par site
 (vacances, fériés)           (score ou ML)           (faible / modéré / élevé)
Type de site            ──►
Capacité de charge      ──►                            Carte Isère interactive
 (seuil par site)
                                    ▲
Historique fréquentation ─────── (si disponible)
(éco-compteurs ENS,                validation
 CC Oisans, Murmuration)
```

**Deux modes selon la disponibilité des données :**

- **Mode supervisé** (sites avec compteurs) : modèle entraîné sur historique → prédiction quantitative
- **Mode score proxy** (sites sans données) : combinaison pondérée météo + calendrier + type de site → applicable partout dès le départ

---

## Données disponibles

| Source | Contenu | Usage dans le POC |
|---|---|---|
| Éco-compteurs ENS | Comptages horaires 2009–2026 | Entraînement et validation du modèle supervisé |
| Éco-compteurs CC Oisans | Comptages 2026, 12 capteurs | Validation sur un 2e territoire |
| Murmuration (6 lacs) | Fréquentation + santé végétation 2019–2025 | Lien fréquentation → impact environnemental |
| Météo MeteoFrance | Historique 1950–2024 (stations Isère) | Features d'entraînement |
| Open-Meteo API | Prévisions J+7 gratuites | Input du modèle en production |
| Apidae (événements) | 6 052 fêtes et manifestations | Feature "événement local" |
| Biodivsports | Zones naturelles sensibles | Croisement zones fragiles × fréquentation prévue |

---

## Gaps identifiés

| Gap | Impact | Contournement POC |
|---|---|---|
| Absence de compteurs sur la majorité des sites | Impossible d'entraîner un modèle supervisé partout | Mode score proxy généralisable |
| Capacité de charge rarement formalisée | Pas de seuil d'alerte défini par défaut | Valeurs types par catégorie de site (à calibrer avec gestionnaires) |
| Pas de données de fréquentation temps-réel | Modèle ne se recale pas en continu | Recalage journalier sur compteurs disponibles |
| Événements locaux non exhaustifs et non structurés | Feature imprécise | Apidae couvre les principaux événements |

---

## Pistes d'évolution

| Version | Ajout | Valeur ajoutée |
|---|---|---|
| **V2** | Données temps-réel (compteurs, parkings) | Recalage du modèle en continu |
| **V2** | Calibrage par analogie entre sites similaires | Couverture universelle sans compteur |
| **V3** | Recommandations d'action automatiques (communication préventive, itinéraire alternatif, quota) | Outil décisionnel complet |
| **V3** | Couplage impact écologique (Murmuration) : fréquentation prévue → dégradation estimée | Argument environnemental quantifié |
| **V4** | API ouverte — les gestionnaires alimentent eux-mêmes leurs seuils et leurs données | Effet réseau, montée en échelle nationale |
