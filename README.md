# Sentinelle Ecowitt

Intégration Home Assistant, installable via **HACS**, qui prédit les
risques de **gel** et de **maladies des plantes** (mildiou, oïdium...)
à partir des capteurs de votre station Ecowitt déjà intégrée à Home
Assistant, combinés aux prévisions météo.

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support%20the%20project-orange?logo=buy-me-a-coffee&logoColor=white)](https://buymeacoffee.com/sdavid66)
![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)
![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)

## Pourquoi

Une station Ecowitt donne des mesures brutes (température, humidité,
pluie, humectation foliaire...). Ce plugin les transforme en **alertes
actionnables** : "gel probable cette nuit", "conditions favorables au
mildiou depuis 2 jours", etc., directement utilisables dans vos
automatisations (notification, mise en route d'un voile d'hivernage,
arrosage préventif...).

## Fonctionnement

Le plugin **ne communique pas directement** avec votre passerelle
Ecowitt : il réutilise les entités déjà créées par l'intégration
Ecowitt native de Home Assistant (ou toute autre source compatible),
ce qui le rend plus simple, plus robuste, et indépendant du modèle de
passerelle (GW1000, GW2000, WS90...).

Il combine :
- vos capteurs Ecowitt (température, humidité, vent, humectation
  foliaire si disponible) ;
- les prévisions d'une entité météo Home Assistant (`weather.*`) pour
  anticiper sur plusieurs heures/jours ;
- des modèles agronomiques simplifiés pour calculer un niveau de
  risque : `none` / `watch` / `warning` / `severe`.

## Prérequis

- Home Assistant 2024.6.0 ou supérieur.
- Une station Ecowitt déjà intégrée (intégration native `Ecowitt` ou
  équivalent) avec au minimum un capteur de température et d'humidité.
- Une entité météo (`weather.*`) configurée pour les prévisions.
- (Optionnel mais recommandé pour le mildiou) un capteur d'humectation
  foliaire (ex. Ecowitt WH55).

## Installation via HACS

1. HACS → Intégrations → menu (⋮) → **Dépôts personnalisés**.
2. Ajouter l'URL de ce dépôt, catégorie **Intégration**.
3. Rechercher "Sentinelle Ecowitt" et installer.
4. Redémarrer Home Assistant.
5. Paramètres → Appareils et services → Ajouter une intégration →
   "Sentinelle Ecowitt".

## Configuration

Lors de l'ajout de l'intégration, sélectionnez :
- le capteur de température et d'humidité de votre station ;
- (optionnel) vent, pluie, humectation foliaire ;
- l'entité météo à utiliser pour les prévisions ;
- les modèles de risque à activer.

Ces réglages sont modifiables à tout moment via **Options** sur
l'intégration.

## Modèles de risque (v0.1)

| Modèle | Principe | Statut |
|---|---|---|
| Gel / gelée | Température prévue + point de rosée + vent + couverture nuageuse (refroidissement radiatif) | ✅ |
| Mildiou | "Smith Period" simplifiée : 2 jours consécutifs avec ≥11h d'humidité ≥90 % et température min ≥10 °C | ✅ |
| Oïdium | Journées chaudes (21-30 °C) + nuits humides (≥90 % HR) | ✅ (indicatif, séparation jour/nuit à affiner) |

Ces modèles sont **indicatifs** : ils reproduisent des méthodes
agronomiques connues sous une forme simplifiée, mais ne remplacent pas
un avis phytosanitaire professionnel.

## Feuille de route

- v0.2 : séparation jour/nuit correcte pour l'oïdium, ajout tavelure
  (pommier), historique de risque (graphique).
- v0.3 : prévisions multi-jours affinées (agrégation de plusieurs
  sources météo), notifications intégrées, blueprint d'automatisation
  prêt à l'emploi.
- v0.4 : profils "culture" (potager, verger, vigne...) avec seuils
  adaptés par plante.

Voir [ARCHITECTURE.md](ARCHITECTURE.md) pour le détail des choix de
conception.

## Soutenir le projet

Si cette intégration vous fait gagner du temps (ou sauve vos plants de
tomates !), vous pouvez m'offrir un café :

👉 [Buy Me a Coffee](https://buymeacoffee.com/sdavid66)

## Licence

MIT — voir [LICENSE](LICENSE).
