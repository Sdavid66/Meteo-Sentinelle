# Architecture — Sentinelle Ecowitt

Document de planification. Décrit les choix de conception retenus et
les prochaines étapes.

## Objectif du projet

Intégration Home Assistant packagée pour HACS qui transforme les
données d'une station Ecowitt en **alertes de risque exploitables** :
gel/gelée et maladies fongiques des plantes (mildiou, oïdium...).
Distribution gratuite, avec un lien de don (Buy Me a Coffee) pour
soutenir le développement.

## Décisions de conception

### 1. Source de données : entités HA existantes (pas de communication directe)

Le plugin ne réimplémente pas le protocole Ecowitt (local API GW1000/
GW2000 ou cloud). Il consomme les entités déjà exposées par
l'intégration Ecowitt native (ou toute source équivalente : un autre
plugin météo, un capteur générique...).

Avantages :
- pas de duplication avec le travail déjà fait par l'intégration core ;
- fonctionne avec n'importe quel modèle de passerelle Ecowitt, présent
  ou futur, sans maintenance du protocole ;
- le config flow se résume à un `EntitySelector`, donc une UX HACS
  standard et légère.

Inconvénient assumé : dépend de la présence préalable d'une
intégration Ecowitt (ou compatible) configurée par l'utilisateur — ce
qui est documenté comme prérequis dans le README.

### 2. Portée v0.1 : gel + maladies + prévisions météo externes

Trois modèles de risque livrés dès la v0.1 :
1. **Gel** — utilise les prévisions horaires (`weather.get_forecasts`)
   pour anticiper sur 24-48h, plus un ajustement de refroidissement
   radiatif (vent faible + ciel dégagé) basé sur les données
   instantanées.
2. **Mildiou** — modèle "Smith Period" simplifié, basé sur
   l'historique recorder des 72 dernières heures (humidité/humectation
   foliaire + température).
3. **Oïdium** — indice simplifié température de jour / humidité de
   nuit, sur le même historique.

Les modèles historiques (mildiou, oïdium) et le modèle prévisionnel
(gel) cohabitent dans le même coordinator, avec des sources de données
différentes (recorder vs service météo), unifiées derrière une
interface commune (`level`, `RISK_NONE|WATCH|WARNING|SEVERE`).

### 3. Structure du code

```
custom_components/sentinelle_ecowitt/
├── __init__.py          # setup/unload de l'entry
├── manifest.json
├── const.py              # clés de config, domaines, niveaux de risque
├── config_flow.py        # sélection entités + modèles activés
├── coordinator.py        # lecture états + historique + prévisions, exécution des modèles
├── sensor.py              # une entité par modèle activé
├── strings.json / translations/{en,fr}.json
└── models/
    ├── frost.py
    ├── late_blight.py
    └── powdery_mildew.py
```

Chaque modèle est une fonction pure `evaluate_xxx_risk(...) ->
dataclass`, sans dépendance à Home Assistant : testable unitairement
sans instance HA, et facile à étendre (nouveau fichier `models/xxx.py`
+ entrée dans `const.AVAILABLE_MODELS`).

### 4. Fréquence de rafraîchissement

`DataUpdateCoordinator` avec un intervalle de 15 minutes par défaut —
suffisant pour du risque gel/maladie (évolution lente), tout en
restant raisonnable pour l'historique recorder et les appels au
service météo.

### 5. Don / soutien du projet

Choix : **Buy Me a Coffee**, standard dans l'écosystème HACS.
Intégré à deux endroits :
- badge Markdown en haut du `README.md` (visible dans HACS car
  `render_readme: true` dans `hacs.json`) ;
- lien rappelé en fin de README, section "Soutenir le projet".

Pas d'appel réseau ni de logique de don dans le code Python lui-même
(pas de tracking, pas de dépendance runtime) — uniquement de la
documentation. C'est la pratique standard des projets HACS pour rester
conforme aux règles du dépôt par défaut HACS (pas de monétisation
intrusive dans le produit).

## Ce qu'il reste à faire avant publication HACS

1. Remplacer les placeholders `YOUR_GITHUB_USERNAME` (manifest.json,
   README) et `YOUR_BMC_USERNAME` (README) par les vrais identifiants.
2. Créer le dépôt GitHub `ha-sentinelle-ecowitt`, pousser ce code.
3. Ajouter des captures d'écran du config flow et des entités dans le
   README (`brands` HACS si publication au dépôt par défaut).
4. Écrire des tests unitaires pour `models/*.py` (pytest, sans HA).
5. Tester en conditions réelles avec une station Ecowitt + une entité
   météo (ex. Met.no, intégrée nativement à HA).
6. Soumettre au dépôt par défaut HACS une fois le projet stable
   (optionnel — utilisable en dépôt personnalisé dès maintenant).

## Roadmap fonctionnelle

- **v0.2** — séparation jour/nuit correcte pour l'oïdium (actuellement
  approximée sur l'ensemble de l'historique), ajout tavelure du
  pommier (modèle de Mills), capteur "historique du risque" avec
  attributs graphables.
- **v0.3** — agrégation de plusieurs sources météo pour fiabiliser les
  prévisions de gel, service HA pour déclencher une notification
  formatée, blueprint d'automatisation prêt à l'emploi.
- **v0.4** — profils "culture" (potager, verger, vigne) avec seuils de
  risque adaptés par plante, sélectionnables dans le config flow.
