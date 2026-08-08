# Architecture — Météo Sentinelle

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
custom_components/meteo_sentinelle/
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

### 5 ter. Multi-arbres, phénologie et alerting (v0.4)

**Un arbre = une sous-entrée = un appareil.** La v0.3 ne suivait qu'une
culture par entrée de configuration. Trois options existaient pour en
suivre plusieurs : dupliquer l'intégration (lourd, et autant de requêtes
météo), un service YAML (pas d'interface), ou les **sous-entrées**
(`ConfigSubentryFlow`). La dernière a été retenue : elle donne un bouton
« Ajouter un arbre » natif, un appareil Home Assistant par arbre, et
laisse les capteurs et les prévisions **partagés au niveau de l'entrée
principale** — une seule requête `weather.get_forecasts` et une seule
lecture du recorder alimentent tout le verger.

**Lisibilité des stades.** Le problème est réel : dix entités nommées
« Stade phénologique » seraient indiscernables. Trois réponses
superposées, du plus structurel au plus cosmétique :

1. l'entité appartient à l'appareil de l'arbre — le contexte est porté
   par le registre, pas par une convention de nommage ;
2. les options du `select` sont préfixées par l'espèce (« Pommier —
   Pleine floraison »), ce qui préserve le sens hors contexte (cartes,
   historique, journal) ;
3. les attributs `tree`, `crop_label`, `stage_label` restent
   disponibles pour les modèles Jinja.

**Modèles pertinents par espèce.** `CROP_DISEASE_MODELS` restreint les
maladies évaluées à celles qui concernent l'espèce. Appliquer le mildiou
de la pomme de terre à un pommier produirait une alerte dénuée de sens
agronomique — pire qu'une absence d'alerte, car elle érode la confiance.
Le risque météo mildiou reste calculé une fois pour le site (la météo est
la même partout), seule la protection est individuelle.

**Phénologie par degrés-jours.** Le développement printanier suit
l'accumulation thermique, pas le calendrier. On cumule des GDD (base
5,6 °C, moyenne journalière, depuis le 1er janvier) et on les compare à
des seuils par espèce et par stade.

Trois propriétés délibérées :

- **idempotence** — `accumulate` n'intègre que les journées complètes non
  encore comptées, condition nécessaire puisqu'il tourne toutes les
  15 minutes ;
- **monotonie** — `propose_advance` ne fait jamais reculer un stade. Un
  redoux ne peut pas « défaire » une floraison constatée ;
- **primauté de l'observation** — une correction manuelle devient la
  nouvelle référence et n'est jamais écrasée, car l'utilisateur qui
  regarde son arbre en sait plus que le modèle.

Le point faible est assumé et documenté : ces seuils sont **calibrés
régionalement** (données nord-américaines). D'où le `gdd_offset` par
arbre, qui permet de recaler la série sur les observations locales, et
l'interrupteur d'avancement automatique qui permet de tout couper.

**Alerting : événements d'abord.** Deux couches, dans cet ordre de
dépendance :

- les **événements** (`meteo_sentinelle_risk_changed`,
  `meteo_sentinelle_stage_advanced`) sont le mécanisme primitif. Ils ne
  présument rien du canal et servent de socle au blueprint fourni ;
- les **notifications persistantes** sont construites par-dessus, actives
  par défaut pour que le plugin soit utile sans configuration.

Deux règles évitent la fatigue d'alerte, qui est le vrai risque d'un
outil de ce type : on ne notifie qu'au **changement** de niveau (un
rappel toutes les 15 minutes apprendrait à ignorer le plugin) et
uniquement à l'**aggravation** (`escalated`). Les niveaux connus sont
amorcés au démarrage sans notification, pour ne pas déclencher une rafale
au redémarrage de Home Assistant sur des risques déjà en cours.

L'état par arbre (stade, indice oïdium, derniers niveaux, traitements)
est persisté dans le `Store`, indexé par `subentry_id`. Changer l'espèce
d'un arbre réinitialise son indice oïdium : le cumul saisonnier d'une
espèce n'a pas de sens pour une autre.

### 5 quater. Migration des entrées existantes

Une leçon apprise à la dure : `ConfigFlow.VERSION` a été incrémentée de
1 à 4 au fil des versions **sans** fournir `async_migrate_entry`. Home
Assistant refuse alors de charger l'entrée et journalise
« Migration handler not found ». Toute installation antérieure était donc
cassée par la mise à jour.

Le handler couvre l'ensemble du chemin 1 → 4, la seule transformation
réellement nécessaire étant 3 → 4 : la culture unique portée par l'entrée
(`crop`, `stage`) devient une sous-entrée arbre. Les versions 1 et 2 ne
possédaient tout simplement pas ces clés, et le repli sur la culture
générique les couvre sans traitement particulier.

Deux décisions :

- **un arbre est créé même sans culture configurée.** Sans arbre,
  l'intégration ne produirait plus aucune entité de risque : l'utilisateur
  verrait ses capteurs disparaître sans comprendre pourquoi ;
- **on refuse de rétrograder.** Si `entry.version > 4`, le handler renvoie
  `False` plutôt que d'écraser des données écrites par une version plus
  récente.

La logique de transformation est isolée dans `tree.legacy_tree_data` et
`tree.strip_legacy_keys`, fonctions pures donc testables sans Home
Assistant — c'est ce qui permet de couvrir la migration dans la suite de
tests plutôt que de la découvrir en production.

### 5 quinquies. Ravageurs, voix et interface (v1.1)

**Un ravageur est un modèle comme un autre.** La tentation était de
créer une famille d'entités distincte — un capteur « stade du cycle »
par insecte. Choix inverse : un ravageur produit un `RiskSensor`
ordinaire, dont l'état est un niveau `none`/`watch`/`warning`/`severe`.
Conséquence immédiate : les événements, les notifications et les deux
blueprints existants fonctionnent sans une ligne de modification, et une
automatisation écrite pour le mildiou marche pour le carpocapse.

Le niveau ne mesure pas la gravité des dégâts mais l'**urgence
d'agir** : le doryphore au stade L2 est en `severe` parce que c'est là
que l'intervention est efficace, et retombe en `none` à la nymphose,
alors même que la défoliation est maximale. C'est contre-intuitif à la
lecture, mais c'est ce qui rend le capteur actionnable.

**Le biofix, ou le refus d'inventer une origine.** Un cumul de
degrés-jours pour le carpocapse démarré au 1er janvier se trompe de
plusieurs semaines : le modèle n'a de sens qu'à partir de la première
capture au piège. Trois options existaient :

1. exiger le piège — rigoureux, mais inutilisable pour la plupart des
   jardiniers ;
2. démarrer au 1er janvier en silence — utilisable, et faux ;
3. estimer le biofix à partir d'un stade phénologique, en le disant.

La troisième a été retenue, avec la même hiérarchie que pour les stades :
l'observation déclarée (`set_biofix`) écrase l'estimation et n'est jamais
réécrasée. Quand aucun ancrage phénologique n'est documenté — le
doryphore — le capteur annonce `awaiting_biofix` plutôt qu'un niveau
calculé sur une origine arbitraire. Le mode 2 n'a jamais été envisagé
sérieusement : c'est exactement le genre de faux négatif que la
réparation « historique insuffisant » cherche par ailleurs à éliminer.

Le cumul depuis le biofix se calcule par **soustraction** du cumul
saisonnier mémorisé au moment du biofix. Aucune relecture d'historique,
et l'opération reste juste même si Home Assistant a été arrêté entre
temps.

**Un cumulateur par barème, pas par ravageur.** `required_accumulators`
regroupe les modèles par couple (base, plafond). Le carpocapse et le
doryphore partagent la base 10 °C mais pas le plafond : ils ne partagent
donc pas leur série, ce que le test vérifie explicitement.

**Le drapeau de saison incomplète.** Un cumul censé partir du 1er janvier
mais commencé en avril produit un total plus bas que la réalité — donc
un cycle annoncé *en retard*, jamais en avance. Le biais est
systématique et connu : `GddState.first_day` permet de le détecter et
`incomplete_season` de le propager. Ne rien dire aurait fait porter au
modèle un défaut qui vient de la date d'installation.

**La réparation plutôt que le silence.** Sans historique, les modèles
maladie annoncent « aucun risque ». Ce n'est pas une panne visible :
c'est une réponse plausible et fausse, le pire cas possible pour un
outil de vigilance. Le registre des réparations était l'endroit exact
pour ça — visible, non bloquant, et refermable automatiquement. Le
critère retenu est la mesure **la moins bien couverte** : un critère
« 6 h continues à HR ≥ 90 % » ne vaut rien avec une température
complète et une humidité absente.

**La carte servie par l'intégration.** L'usage établi est un second
dépôt HACS de catégorie « plugin », que l'utilisateur installe puis
déclare en ressource Lovelace. Deux étapes ratées par une bonne part des
utilisateurs, pour un fichier de quelques kilo-octets déjà présent sur
leur machine. L'intégration l'expose donc elle-même
(`async_register_static_paths` + `add_extra_js_url`).

Trois bénéfices : disponible dès l'installation, versionnée avec le
composant — impossible d'avoir une carte et un composant désaccordés —
et un dépôt de moins à maintenir. Contrepartie assumée : le script est
chargé sur toutes les pages du frontend, y compris là où la carte n'est
pas utilisée.

**Les phrases Assist et l'écriture dans la configuration.** Home
Assistant ne lit les phrases personnalisées que depuis
`<config>/custom_sentences/<langue>/`, et l'API qui permettait à une
intégration d'en enregistrer a été retirée. Le seul chemin praticable
est la recopie.

Écrire chez l'utilisateur mérite trois garde-fous, tous implémentés :
la case à cocher dans les options, l'absence totale d'écrasement d'un
fichier modifié (comparaison par empreinte), et un en-tête dans le
fichier qui explique d'où il vient et comment s'en débarrasser.

À noter, un effet de bord précieux : l'API LLM d'Assist construit
automatiquement un outil par intent enregistré. Écrire les gestionnaires
avec une `description` soignée les rend utilisables par un agent adossé
à un modèle de langage **sans** ces phrases — deux publics couverts pour
un seul travail.

**`cycle_stage` et non `stage`.** Les attributs d'un capteur de risque
portent déjà le stade phénologique de la plante. Nommer `stage` le jalon
du cycle de l'insecte aurait produit une collision silencieuse, l'un
écrasant l'autre selon l'ordre de construction du dictionnaire. Le
renommage est explicite plutôt que défensif.

### 6. Identité visuelle

Deux usages distincts, deux mécanismes différents :

- **Bannière README** (`images/logo.png`, 640 px) — le logo complet,
  qui illustre la chaîne mesures → moteur → alertes. Affiché en grand,
  il est lisible et explique le projet d'un coup d'œil. Un simple
  fichier dans le dépôt, rendu par GitHub.
- **Icône HACS / Home Assistant**
  (`custom_components/meteo_sentinelle/brand/`) — une version épurée
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
`/api/brands/integration/meteo_sentinelle/…` et leur donne priorité
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

1. Intégrer `tests/test_models.py` (140 vérifications, exécutable sans
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
- **v0.4** (actuelle) — plusieurs arbres en sous-entrées, avancement
  phénologique par degrés-jours, alerting par événements, notifications
  et blueprint.
- **v0.5** — tavelure du pommier (table de Mills inversée en
  degrés-heures), cohortes d'infection avec latence pour le mildiou.
- **v0.6** — sensibilité variétale, agrégation de plusieurs sources
  météo.
- **v0.7** — recalage automatique du `gdd_offset` par apprentissage sur
  les corrections manuelles de l'utilisateur.
