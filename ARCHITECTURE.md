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

### 2 bis. Sources de secours (MeteoSwiss)

La station personnelle de l'utilisateur est un point de défaillance
unique : batterie vide, passerelle débranchée, capteur noyé. Comme les
modèles de risque n'ont d'intérêt que s'ils tournent en continu (une
alerte gel manquée = des plants perdus), l'intégration accepte une
**source de secours** par mesure, typiquement les capteurs temps réel
de l'intégration MeteoSwiss.

Priorité retenue, implémentée dans `coordinator._resolve_measurement` :

1. capteur Ecowitt configuré et exploitable → utilisé ;
2. sinon, capteur de secours (MeteoSwiss) exploitable → utilisé ;
3. sinon, mesure absente (`None`), les modèles dégradent proprement.

« Exploitable » signifie : entité présente, état différent de
`unknown`/`unavailable`, et valeur convertible en nombre. Une valeur
illisible bascule donc aussi sur le secours.

Ce choix (secours automatique plutôt que choix manuel par mesure)
évite à l'utilisateur d'avoir à reconfigurer quoi que ce soit le jour
où sa station tombe, tout en gardant la précision d'un capteur local
tant qu'il fonctionne — un capteur dans le jardin décrit mieux le
microclimat des plantes qu'une station officielle à plusieurs
kilomètres.

L'historique utilisé par les modèles maladie suit la même priorité
(`_resolve_history_entity`), pour éviter de mélanger deux séries de
mesures différentes dans un même calcul de Smith Period.

La traçabilité est exposée à l'utilisateur : `coordinator.sources`
associe chaque mesure à son origine (`ecowitt` / `meteoswiss` /
`unavailable`), repris en attributs sur chaque capteur de risque et
résumé par une entité dédiée « Source des données ». Cela permet de
créer une automatisation qui alerte quand la station perso décroche.

Rien dans le code n'est spécifique à la Suisse : les champs sont de
simples sélecteurs d'entités, donc n'importe quelle autre source
(Open-Meteo, station voisine, capteur Zigbee) peut jouer le rôle de
secours. MeteoSwiss est simplement le cas d'usage documenté.

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

### 5 bis. Passage aux modèles horaires et aux critères publiés (v0.3)

La v0.1 testait des seuils sur des agrégats journaliers. C'était un
drapeau « conditions favorables », pas un modèle. La v0.3 remplace ce
socle.

**Séries horaires (`models/hourly.py`).** Les critères publiés sont
définis en heures *continues* : « 6 heures entre 21 et 30 °C », « 11 h
à HR ≥ 90 % ». Les états du recorder arrivent à intervalle irrégulier ;
`resample_hourly` les agrège en pas horaires, `longest_run` compte les
séries consécutives (une série interrompue ne compte pas, ce qui est le
comportement prudent). `complete_days` écarte les journées trop
partielles, qui produiraient de faux négatifs en bord d'historique.

**Réponse thermique continue.** `beta_response` remplace les seuils
binaires par une courbe de type Bêta (Analytis) définie par ses
températures cardinales. Un test « T ≥ 10 °C » traite identiquement
11 °C et 20 °C alors que l'écart biologique est considérable ; la courbe
les distingue. Elle sert de pondération de la pression d'infection, pas
de critère de déclenchement — les critères restent ceux publiés, pour
rester comparables aux avertissements officiels.

**Hutton en plus de Smith.** Le niveau de risque mildiou suit désormais
les critères de Hutton (6 h) et non la Smith Period (11 h). Les deux
sont calculés et exposés : Smith reste utile pour comparer avec les
bulletins historiques, mais elle sous-détecte les génotypes agressifs
actuels. Choix : piloter par le critère le plus sensible, exposer
l'autre.

**Gubler-Thomas et le problème de l'état.** Cet indice est *cumulatif
sur la saison* : il ne peut pas être recalculé depuis une fenêtre
glissante de 96 h. Le coordinator porte donc l'état (`index`,
`epidemic_started`, `last_processed_day`) et le persiste via le `Store`
de Home Assistant. `evaluate_powdery_mildew_risk` n'avance l'indice que
sur les journées complètes non encore traitées, ce qui rend l'appel
idempotent — condition nécessaire puisqu'il est appelé toutes les
15 minutes.

**Écart documenté par rapport à Gubler-Thomas.** L'oïdium est inhibé
par l'eau libre, que le modèle d'origine ne prend pas en compte. La
pénalité pluie ajoutée reprend la règle du modèle Hop Powdery Mildew
(variante Cascade), dérivé de Gubler-Thomas. Elle est signalée comme
extension et désactivable : mieux vaut une déviation explicite et
paramétrable qu'une modification silencieuse d'un modèle publié.

**Seuils de gel phénologiques (`models/crops.py`).** Tables T10/T90 de
WSU, converties des °F. Le stade change au fil de la saison : le figer
dans les options aurait imposé une reconfiguration à chaque évolution.
Il est donc exposé comme entité `select`, modifiable depuis le tableau
de bord ou par automatisation. Les valeurs des cultures potagères ne
proviennent pas de ces tables et sont marquées `source="generic"`.

**Air ou surface.** Les seuils WSU s'entendent sur la température des
bourgeons, proche de celle de l'air. Les cultures basses subissent en
revanche le refroidissement radiatif du sol : elles sont évaluées sur
une température de surface estimée (jusqu'à 5 °C sous l'air par ciel
dégagé et vent nul). L'attribut `reference` indique laquelle a servi.
Cette paramétrisation est empirique, calée sur l'ordre de grandeur
documenté de 3 à 5 °C, et non un bilan énergétique validé.

**Suivi des traitements.** Le cumul de pluie depuis une application est
incrémenté à chaque cycle plutôt que recalculé sur tout l'historique :
une requête recorder de trois semaines toutes les 15 minutes serait
inacceptable. Conséquence assumée : une longue indisponibilité de Home
Assistant sous-estime le lessivage, et le code refuse d'extrapoler
au-delà de 6 h à partir d'une intensité instantanée.

### 6. Identité visuelle

Deux usages distincts, deux mécanismes différents :

- **Bannière README** (`images/logo.png`, 640 px) — le logo complet,
  qui illustre la chaîne mesures → moteur → alertes. Affiché en grand,
  il est lisible et explique le projet d'un coup d'œil. Un simple
  fichier dans le dépôt, rendu par GitHub.
- **Icône HACS / Home Assistant**
  (`custom_components/sentinelle_ecowitt/brand/`) — une version épurée
  du même logo (feuille + flocon, palette identique, sans texte).
  Nécessaire car l'interface affiche l'icône entre 32 et 64 px, taille
  à laquelle tout texte devient illisible.

**Choix du mécanisme de livraison de l'icône.** Deux options
existaient : soumettre les images au dépôt central
`home-assistant/brands` (l'ancienne méthode), ou les livrer directement
dans le dossier de l'intégration (`brand/`, méthode introduite avec
Home Assistant 2026.3). La seconde a été retenue : le dépôt `brands`
n'accepte d'ailleurs plus les soumissions d'intégrations personnalisées
depuis cette version, et la méthode locale ne dépend d'aucune PR
externe ni délai de fusion — l'icône est disponible dès l'installation.
Home Assistant sert ces images via
`/api/brands/integration/sentinelle_ecowitt/…` et leur donne priorité
sur celles du dépôt central.

Contrepartie assumée : nécessite HA ≥ 2026.3 (contrainte répercutée
dans `hacs.json`), et une limitation connue de HACS fait que le tableau
de bord HACS (avant installation) n'affiche pas ces icônes locales —
son catalogue de vignettes vient d'une source distincte
(`data-v2.hacs.xyz`) qui n'a pas connaissance des icônes livrées dans
les dossiers d'intégration ([hacs/integration#5171](https://github.com/hacs/integration/issues/5171),
[#5223](https://github.com/hacs/integration/issues/5223), non résolus
au moment de l'écriture). L'icône s'affiche correctement une fois
l'intégration installée, ce qui est la garantie qui compte.

La source vectorielle de l'icône est versionnée (`icon.svg`, à côté
des PNG dans `brand/`, ignorée par Home Assistant), afin de pouvoir la
régénérer à n'importe quelle résolution sans perte.

Contraintes respectées pour le format `brand/` : PNG carré, canal
alpha, détouré sans marge transparente, 256 px et 512 px — les mêmes
exigences que `home-assistant/brands`, seul l'emplacement change.

## Ce qu'il reste à faire avant publication HACS

1. Intégrer `tests/test_models.py` (80 vérifications, exécutable sans
   Home Assistant) à un workflow GitHub Actions.
2. Ajouter des captures d'écran du config flow et des entités au README.
3. Tester en conditions réelles avec une station Ecowitt + une entité
   météo (MeteoSwiss ou Met.no).
4. Vérifier le parcours de mise à jour depuis la v0.1 (le config flow
   est passé en VERSION 2 ; les entrées existantes n'ont simplement pas
   d'entités de secours, ce qui reste valide).
5. Passer le dépôt en public, puis soumettre au dépôt par défaut HACS
   une fois le projet stable (optionnel — utilisable en dépôt
   personnalisé dès maintenant).

## Roadmap fonctionnelle

- **v0.2** — support MeteoSwiss comme source de prévisions et de
  secours automatique, entité « Source des données ».
- **v0.3** (actuelle) — socle horaire, critères de Hutton, indice
  Gubler-Thomas, seuils de gel T10/T90 par stade, température de
  surface, suivi des traitements.
- **v0.4** — tavelure du pommier (table de Mills inversée en
  degrés-heures), cohortes d'infection avec latence pour le mildiou,
  historique de risque graphable.
- **v0.5** — agrégation de plusieurs sources météo, notifications
  formatées, blueprint d'automatisation.
- **v0.6** — avancement automatique du stade phénologique par cumul de
  degrés-jours, sensibilité variétale.
