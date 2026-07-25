<p align="center">
  <img src="images/logo.png" alt="Sentinelle Ecowitt" width="260">
</p>

<h1 align="center">Sentinelle Ecowitt</h1>

Intégration Home Assistant, installable via **HACS**, qui prédit les
risques de **gel** et de **maladies des plantes** (mildiou, oïdium...)
à partir des capteurs de votre station Ecowitt déjà intégrée à Home
Assistant, combinés aux prévisions météo.

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support%20the%20project-orange?logo=buy-me-a-coffee&logoColor=white)](https://buymeacoffee.com/sdavid66)
![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)
![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)

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
- en secours, les capteurs temps réel d'une station officielle comme
  **MeteoSwiss** (voir ci-dessous) ;
- les prévisions d'une entité météo Home Assistant (`weather.*`) pour
  anticiper sur plusieurs heures/jours ;
- des modèles agronomiques simplifiés pour calculer un niveau de
  risque : `none` / `watch` / `warning` / `severe`.

## Support MeteoSwiss

Si vous utilisez l'intégration [MeteoSwiss](https://github.com/Rudd-O/homeassistant-meteoswiss)
(installable via HACS), vous pouvez l'associer à Sentinelle Ecowitt de
deux manières complémentaires :

1. **Comme source de prévisions** — choisissez simplement son entité
   `weather.*` à l'étape de configuration. C'est elle qui alimente le
   modèle de gel avec les prévisions horaires officielles suisses.
2. **Comme source de secours** — à la deuxième étape du config flow,
   vous pouvez désigner les capteurs temps réel de votre station
   MeteoSwiss (température, humidité, vent, pluie).

Le principe de secours est simple : **votre station Ecowitt reste
toujours prioritaire**. Le capteur MeteoSwiss prend automatiquement le
relais dans deux cas :

- la mesure n'existe pas chez vous (par exemple si vous n'avez pas
  d'anémomètre) ;
- votre capteur Ecowitt tombe en panne, passe en `unavailable` ou
  renvoie une valeur illisible.

Les prédictions continuent donc de fonctionner même si votre station
personnelle est hors service. Une entité **Source des données**
(`ecowitt` / `meteoswiss` / `mixed` / `unavailable`) indique à tout
moment quelle station alimente réellement les calculs, avec le détail
mesure par mesure en attributs — pratique pour recevoir une
notification quand votre Ecowitt décroche.

Cette étape est entièrement facultative : si vous laissez les champs
vides, l'intégration fonctionne comme avant, uniquement avec votre
station Ecowitt. Et rien n'est spécifique à la Suisse — n'importe
quelle autre source de capteurs Home Assistant peut servir de secours.

## Prérequis

- Home Assistant 2024.6.0 ou supérieur.
- Une station Ecowitt déjà intégrée (intégration native `Ecowitt` ou
  équivalent) avec au minimum un capteur de température et d'humidité.
- Une entité météo (`weather.*`) configurée pour les prévisions —
  l'intégration MeteoSwiss convient parfaitement en Suisse.
- (Optionnel mais recommandé pour le mildiou) un capteur d'humectation
  foliaire (ex. Ecowitt WH55).
- (Optionnel) l'intégration MeteoSwiss, pour servir de source de
  secours si un capteur Ecowitt tombe en panne.

## Installation via HACS

1. HACS → Intégrations → menu (⋮) → **Dépôts personnalisés**.
2. Ajouter l'URL de ce dépôt, catégorie **Intégration**.
3. Rechercher "Sentinelle Ecowitt" et installer.
4. Redémarrer Home Assistant.
5. Paramètres → Appareils et services → Ajouter une intégration →
   "Sentinelle Ecowitt".

## Configuration

La configuration se fait en deux étapes.

**Étape 1 — votre station Ecowitt :**
- le capteur de température et d'humidité de votre station ;
- (optionnel) vent, pluie, humectation foliaire ;
- l'entité météo à utiliser pour les prévisions (ex. MeteoSwiss) ;
- les modèles de risque à activer.

**Étape 2 — sources de secours (facultatif) :**
- les capteurs temps réel MeteoSwiss (température, humidité, vent,
  pluie) qui prendront le relais en cas de panne.

Ces réglages sont modifiables à tout moment via **Options** sur
l'intégration.

## Modèles de risque

| Modèle | Principe | Statut |
|---|---|---|
| Gel / gelée | Température prévue + point de rosée + vent + couverture nuageuse (refroidissement radiatif) | ✅ |
| Mildiou | "Smith Period" simplifiée : 2 jours consécutifs avec ≥11h d'humidité ≥90 % et température min ≥10 °C | ✅ |
| Oïdium | Journées chaudes (21-30 °C) + nuits humides (≥90 % HR) | ✅ (indicatif, séparation jour/nuit à affiner) |

Ces modèles sont **indicatifs** : ils reproduisent des méthodes
agronomiques connues sous une forme simplifiée, mais ne remplacent pas
un avis phytosanitaire professionnel.

## Feuille de route

- **v0.2 (actuelle)** : support MeteoSwiss en prévisions et en secours
  automatique, entité « Source des données ».
- v0.3 : séparation jour/nuit correcte pour l'oïdium, ajout tavelure
  (pommier), historique de risque (graphique).
- v0.4 : prévisions multi-jours affinées (agrégation de plusieurs
  sources météo), notifications intégrées, blueprint d'automatisation
  prêt à l'emploi.
- v0.5 : profils "culture" (potager, verger, vigne...) avec seuils
  adaptés par plante.

Voir [ARCHITECTURE.md](ARCHITECTURE.md) pour le détail des choix de
conception.

## Icône dans HACS et Home Assistant

Les icônes officielles se trouvent dans `brands/sentinelle_ecowitt/`
(`icon.png` 256 px, `icon@2x.png` 512 px, plus la source `icon.svg`),
au format exigé par Home Assistant : PNG carré, fond transparent,
détouré sans marge.

Home Assistant et HACS ne lisent pas ces fichiers depuis ce dépôt :
ils les chargent depuis le dépôt central
[home-assistant/brands](https://github.com/home-assistant/brands).
Pour que l'icône apparaisse dans l'interface, il faut donc l'y
soumettre une fois :

1. Forker `home-assistant/brands`.
2. Copier `brands/sentinelle_ecowitt/` vers
   `custom_integrations/sentinelle_ecowitt/` dans le fork.
3. Ouvrir une pull request.

Tant que cette PR n'est pas fusionnée, HACS affiche une icône
générique — c'est normal et sans conséquence sur le fonctionnement de
l'intégration.

## Soutenir le projet

Si cette intégration vous fait gagner du temps (ou sauve vos plants de
tomates !), vous pouvez m'offrir un café :

👉 [Buy Me a Coffee](https://buymeacoffee.com/sdavid66)

## Licence

MIT — voir [LICENSE](LICENSE).
