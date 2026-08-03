<p align="center">
  <img src="https://raw.githubusercontent.com/Sdavid66/Meteo-Sentinelle/main/images/logo.png" alt="Météo Sentinelle" width="260">
</p>

<h1 align="center">Météo Sentinelle</h1>

<p align="center">
  <a href="README.md">English</a> · <b>Français</b>
</p>

Intégration Home Assistant, installable via **HACS**, qui prédit les
risques de **gel** et de **maladies des plantes** (mildiou, oïdium...)
à partir des capteurs de **votre station météo, quelle qu'elle soit**,
combinés aux prévisions météo.
Si vous le souhaitez, vous pouvez me donner un peu de courage en me payant un café :-). 

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support%20the%20project-orange?logo=buy-me-a-coffee&logoColor=white)](https://buymeacoffee.com/sdavid66)
![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)
[![Ouvrir ce dépôt dans HACS sur votre instance Home Assistant.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sdavid66&repository=Meteo-Sentinelle&category=integration)
![Version](https://img.shields.io/github/v/release/Sdavid66/Meteo-Sentinelle?label=version&color=blue)

## Pourquoi

Une station météo donne des mesures brutes (température, humidité,
pluie, humectation foliaire...). Ce plugin les transforme en **alertes
actionnables** : « gel probable cette nuit sur le pommier en fleur »,
« conditions favorables au mildiou depuis 2 jours », directement
utilisables dans vos automatisations (notification, mise en route d'un
voile d'hivernage, traitement préventif...).

## Quelle station météo ?

**Peu importe la marque.** Le plugin ne parle à aucun matériel : il lit
des **entités Home Assistant**. Toute source capable de fournir une
température et une humidité dans Home Assistant fait l'affaire.

Fonctionnent immédiatement :

- une station **privée** intégrée nativement — Ecowitt, Netatmo, Davis,
  WeatherFlow Tempest, Bresser, Acurite via un pont, Aqara, Zigbee ou
  Z-Wave ;
- une station **officielle ou publique** — MeteoSwiss, Met.no, Météo-France,
  DWD, OpenWeatherMap, AccuWeather ;
- un **assemblage de capteurs isolés** : un thermomètre Zigbee au verger
  et un hygromètre dans la serre suffisent à démarrer.

### Station non intégrée dans Home Assistant

Si votre station n'a pas d'intégration native — modèle exotique,
montage maison, matériel ancien — il suffit d'en faire entrer les
mesures dans Home Assistant sous forme d'entités. Plusieurs voies
existent, par ordre de simplicité :

| Situation | Voie |
|---|---|
| La station publie en MQTT | Intégration **MQTT**, `mqtt sensor` |
| La station expose une page ou une API HTTP | `rest` sensor, ou `scrape` |
| Console avec logiciel type Weewx / Meteobridge | Passerelle MQTT ou export HTTP |
| Station Ecowitt sans passerelle supportée | Protocole *custom server* d'Ecowitt vers Home Assistant |
| Données déjà présentes mais mal formées | `template` sensor pour convertir unités ou extraire une valeur |
| Relevés manuels ou fichier | `input_number`, ou `file`/`command_line` sensor |

Dès que ces capteurs apparaissent dans Home Assistant, Météo Sentinelle
les utilise comme n'importe quels autres — il les sélectionne dans une
simple liste déroulante à la configuration.

Le seul élément qui doit venir d'une intégration météo classique est
l'entité **`weather.*`** fournissant les **prévisions horaires**, sur
laquelle repose l'anticipation du gel. N'importe quelle intégration
météo gratuite convient (Met.no est installée par défaut dans Home
Assistant).

## Fonctionnement

Le plugin **ne communique avec aucun matériel** : il réutilise les
entités déjà présentes dans Home Assistant. C'est ce qui le rend
indépendant de la marque, du modèle et du protocole de votre station —
et robuste, puisqu'il n'y a aucun pilote à maintenir.

Il combine :
- les capteurs de votre station (température, humidité, vent,
  humectation foliaire si disponible) ;
- en secours, les capteurs temps réel d'une station officielle comme
  **MeteoSwiss** (voir ci-dessous) ;
- les prévisions d'une entité météo Home Assistant (`weather.*`) pour
  anticiper sur plusieurs heures/jours ;
- des modèles agronomiques publiés pour calculer un niveau de risque :
  `none` / `watch` / `warning` / `severe`.

## Support MeteoSwiss

Si vous utilisez l'intégration [MeteoSwiss](https://github.com/Rudd-O/homeassistant-meteoswiss)
(installable via HACS), vous pouvez l'associer à Météo Sentinelle de
deux manières complémentaires :

1. **Comme source de prévisions** — choisissez simplement son entité
   `weather.*` à l'étape de configuration. C'est elle qui alimente le
   modèle de gel avec les prévisions horaires officielles suisses.
2. **Comme source de secours** — à la deuxième étape du config flow,
   vous pouvez désigner les capteurs temps réel de votre station
   MeteoSwiss (température, humidité, vent, pluie).

Le principe de secours est simple : **votre station personnelle reste
toujours prioritaire** — un capteur au verger décrit mieux le microclimat
de vos plantes qu'une station officielle à plusieurs kilomètres. Le
capteur de secours prend automatiquement le relais dans deux cas :

- la mesure n'existe pas chez vous (par exemple si vous n'avez pas
  d'anémomètre) ;
- votre capteur tombe en panne, passe en `unavailable` ou renvoie une
  valeur illisible.

Les prédictions continuent donc de fonctionner même si votre station
personnelle est hors service. Une entité **Source des données**
(`ecowitt` / `meteoswiss` / `mixed` / `unavailable`) indique à tout
moment quelle station alimente réellement les calculs, avec le détail
mesure par mesure en attributs — pratique pour recevoir une
notification quand votre station décroche.

Cette étape est entièrement facultative : si vous laissez les champs
vides, l'intégration fonctionne comme avant, uniquement avec votre
station personnelle. Et rien n'est spécifique à la Suisse — n'importe
quelle autre source de capteurs Home Assistant peut servir de secours.

## Prérequis

- Home Assistant 2026.3.0 ou supérieur (nécessaire pour l'icône locale).
- **Au minimum un capteur de température et un capteur d'humidité**
  visibles dans Home Assistant, quelle qu'en soit la provenance (voir
  « Quelle station météo ? » ci-dessus).
- Une entité météo (`weather.*`) configurée pour les prévisions —
  l'intégration MeteoSwiss convient parfaitement en Suisse.
- (Optionnel mais recommandé pour le mildiou) un capteur d'humectation
  foliaire, par exemple un Ecowitt WH55 ou tout capteur équivalent.
- (Optionnel) une seconde source météo — MeteoSwiss ou autre — pour
  servir de secours si un capteur de votre station tombe en panne.
- Le **recorder** actif sur vos capteurs de température et d'humidité :
  les modèles maladie ont besoin d'environ 4 jours d'historique horaire.
  Si vous excluez ces entités du recorder, seul le modèle de gel
  fonctionnera.

## Installation via HACS

Météo Sentinelle fait partie du magasin HACS par défaut : il n'y a aucun
dépôt personnalisé à ajouter.

1. Ouvrir HACS et rechercher « Météo Sentinelle ».
2. Installer, puis redémarrer Home Assistant.
3. Paramètres → Appareils et services → Ajouter une intégration →
   « Météo Sentinelle ».

## Configuration

La configuration sépare ce qui est **commun au site** de ce qui est
**propre à chaque arbre**.

**À l'installation — le site :**
- le capteur de température et d'humidité de votre station, quelle qu'en
  soit la marque ;
- (optionnel) vent, intensité de pluie (mm/h), humectation foliaire ;
- l'entité météo à utiliser pour les prévisions (ex. MeteoSwiss) ;
- les modèles de risque à activer et les notifications ;
- (facultatif) les capteurs MeteoSwiss de secours.

**Ensuite — vos arbres**, un par un, via le bouton **« Ajouter un
arbre »** sur la page de l'intégration. Pour chacun :

| Champ | Rôle |
|---|---|
| Nom | « Golden du fond », « Cerisier de la terrasse »… |
| Espèce | détermine les seuils de gel T10/T90 et les maladies suivies |
| Stade phénologique | position actuelle dans la saison |
| Avancement automatique | laisse les degrés-jours faire progresser le stade |
| Décalage de degrés-jours | recale le modèle sur votre verger |

Les capteurs et la météo restent **partagés** : ajouter un dixième
arbre ne déclenche aucune requête supplémentaire.

## Plusieurs arbres, chacun son calcul

Chaque arbre devient un **appareil Home Assistant distinct**, nommé
« Espèce + votre nom » (par exemple *Pommier Golden du fond*). Ses
entités sont rattachées à cet appareil :

- **Risque de gel** — calculé avec les seuils du stade de *cet* arbre.
  Un pommier en floraison et un cerisier encore en bourgeon gonflé, la
  même nuit, ne donnent pas la même alerte.
- **Stade phénologique** — en capteur (historisable) et en `select`
  (modifiable).
- **Avancement automatique** — interrupteur, pour reprendre la main
  arbre par arbre.
- **Risques maladie et protection** — uniquement ceux qui concernent
  l'espèce. Un pommier reçoit l'oïdium, une pomme de terre le mildiou ;
  appliquer le mildiou de la pomme de terre à un pommier n'aurait aucun
  sens agronomique.

**Comment distinguer les stades d'un arbre à l'autre ?** Le contexte
vient de l'appareil : l'entité appartient à l'appareil de l'arbre, donc
Home Assistant l'affiche *« Pommier Golden du fond — Stade
phénologique »*. Les attributs `tree`, `crop` et `stage` portent le même
contexte pour les cartes et les modèles Jinja.

## Avancement automatique du stade

Le développement printanier suit l'accumulation de chaleur, pas le
calendrier. Le plugin cumule donc des **degrés-jours** (base 5,6 °C,
depuis le 1er janvier, méthode de la moyenne journalière) et compare ce
cumul à des seuils par espèce et par stade.

Quand un seuil est franchi, le stade est **avancé et appliqué
automatiquement**, et vous en êtes informé — notification et événement.
Trois garde-fous :

- **votre correction fait autorité.** Changez le stade à la main depuis
  le `select` : il devient la nouvelle référence ;
- **l'avancement est monotone.** Le modèle ne fait jamais reculer un
  stade : un redoux ne « défait » pas une floraison constatée ;
- **tout est débrayable.** L'interrupteur *Avancement automatique*
  coupe l'automatisme pour un arbre donné.

Le capteur de stade expose aussi le prochain stade attendu, les
degrés-jours restants pour l'atteindre, la date de floraison relevée et
une estimation des jours avant récolte.

⚠️ **Ces seuils sont calibrés régionalement.** Les valeurs de référence
proviennent de données nord-américaines (base 42 °F, MSU Enviroweather).
Sous un autre climat ou avec une autre variété, les mêmes stades
surviennent à des cumuls différents. Le champ **décalage de
degrés-jours** sert précisément à recaler le modèle : positif si votre
verger est régulièrement en avance sur les annonces, négatif s'il est en
retard.

## Alertes

Deux mécanismes complémentaires, tous deux par arbre :

**Notifications intégrées** (activées par défaut, désactivables dans les
options) — une notification Home Assistant à chaque aggravation, à
partir du niveau « alerte » :

> **Pommier Golden du fond — Risque de gel : Danger**
> Stade phénologique : Pleine floraison
> minimum attendu −4,1 °C sous abri, seuil de dégâts −2,2 °C, vers 12/04 03:00

**Événements**, pour vos propres automatisations :

| Événement | Émis quand |
|---|---|
| `meteo_sentinelle_risk_changed` | un niveau de risque change |
| `meteo_sentinelle_stage_advanced` | un stade est avancé automatiquement |

Les données de l'événement contiennent l'arbre, l'espèce, le stade, le
modèle, l'ancien et le nouveau niveau, un booléen `escalated` et un
`detail` déjà rédigé.

### Blueprints prêts à l'emploi

Deux automatisations toutes faites, à installer en un clic — aucun YAML
à écrire. Ces blueprints ne sont **pas** livrés par HACS (qui n'installe
que `custom_components/`) : il faut les importer une fois.

**Protection contre le gel** — prévient au franchissement du seuil,
allume un dispositif de protection (câble chauffant, aspersion, prise
connectée) et le coupe quand le risque retombe. Le dispositif est
facultatif : sans lui, c'est une simple alerte gel.

[![Ouvrir dans Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FSdavid66%2FMeteo-Sentinelle%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fmeteo_sentinelle%2Fprotection_gel.yaml)

**Alertes tous risques** — route gel, mildiou, oïdium et changements de
stade vers le canal de votre choix, avec filtrage par niveau minimal et
par type de risque.

[![Ouvrir dans Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FSdavid66%2FMeteo-Sentinelle%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fmeteo_sentinelle%2Falerte_meteo_sentinelle.yaml)

Les versions anglaises de ces deux blueprints existent aussi
(`frost_protection.yaml` et `risk_alerts.yaml`) : un blueprint ne peut
pas être traduit par Home Assistant, chaque langue est donc un fichier.

Si le bouton ne fonctionne pas, copier l'URL du fichier YAML depuis
`blueprints/automation/meteo_sentinelle/` et l'importer depuis
**Paramètres → Automatisations et scènes → Blueprints → Importer**.

Les deux blueprints ne se déclenchent qu'au **franchissement** du seuil
choisi : rester en alerte ne renotifie pas, et repasser en dessous
déclenche la remise à l'état normal.

Deux principes de conception : on n'alerte **qu'aux changements** — un
rappel toutes les 15 minutes apprendrait vite à ignorer le plugin — et
**seulement à l'aggravation**, une amélioration n'ayant pas à réveiller
qui que ce soit.

Ces réglages sont modifiables à tout moment via **Options** sur
l'intégration ; les arbres se modifient depuis leur propre entrée.

## Modèles de risque

Tous les modèles travaillent sur des **séries horaires** reconstruites
depuis l'historique de Home Assistant, comme l'exigent les critères
publiés (« 6 heures continues », « 11 heures à HR ≥ 90 % »).

### Gel — seuils phénologiques

Il n'existe pas *un* seuil de gel. Un pommier supporte −18 °C en
dormance et souffre dès −2,2 °C en pleine floraison. L'intégration
utilise les tables **T10 / T90** de Washington State University
(températures provoquant 10 % et 90 % de mortalité des bourgeons après
30 min d'exposition), pour pommier, poirier, abricotier, prunier,
pêcher/nectarinier et cerisier doux.

Vous choisissez la culture à la configuration ; le **stade
phénologique** se change ensuite à tout moment depuis l'entité
`select.…_stade_phenologique` — utile pour l'automatiser ou l'ajuster
en observant le verger.

L'intégration estime aussi la **température de surface** : sous ciel
dégagé et vent faible, le rayonnement nocturne refroidit le sol de 3 à
5 °C sous la température de l'air. Une gelée blanche survient donc
couramment alors que l'abri affiche encore +2 °C. Les cultures basses
(tomate, pomme de terre, légumes) sont évaluées sur cette température
de surface, les arbres sur celle de l'air.

### Mildiou — critères de Hutton *et* Smith Period

Deux critères sont calculés en parallèle :

| Critère | Condition | Origine |
|---|---|---|
| **Hutton** | 2 jours consécutifs, T min ≥ 10 °C, **≥ 6 h** continues à HR ≥ 90 % | James Hutton Institute / AHDB, 2017 |
| **Smith** | 2 jours consécutifs, T min ≥ 10 °C, **≥ 11 h** continues à HR ≥ 90 % | Smith, 1956 |

Le niveau de risque suit **Hutton**, plus sensible. Les essais en
enceinte climatique ayant conduit à ces critères ont montré que les
isolats contemporains de *Phytophthora infestans* infectent dans des
conditions nettement moins humides que ne le prévoyait Smith : cette
dernière sous-détecte les génotypes agressifs modernes. Elle reste
exposée en attribut, pour comparaison.

Un capteur d'humectation foliaire, si vous en avez un, remplace le
proxy HR ≥ 90 %.

### Oïdium — indice Gubler-Thomas

Indice cumulatif 0-100 développé à UC Davis, qui pilote l'espacement
des traitements. L'épidémie démarre après 3 journées consécutives
comptant ≥ 6 h continues entre 21,1 et 29,4 °C ; ensuite l'indice gagne
20 points par journée favorable, en perd 10 par journée défavorable ou
par pic à ≥ 35 °C (léthal pour les conidies).

Bandes publiées : 0-30 faible, 40-60 modéré, > 60 élevé — avec un
intervalle de traitement conseillé exposé en attribut.

**Correction ajoutée par ce plugin :** contrairement au mildiou,
l'oïdium est *inhibé* par l'eau libre — la pluie lessive les conidies.
Le Gubler-Thomas d'origine ne modélise pas la pluie ; on applique donc
une pénalité de −10 points au-delà de 2,5 mm journaliers, en reprenant
la règle du modèle « Hop Powdery Mildew » (variante Cascade), lui-même
dérivé de Gubler-Thomas. Désactivable dans les options.

### Suivi des traitements — « protégé jusqu'à »

Un modèle dit « le risque est élevé ». Un outil de décision dit
« traitez avant jeudi ». Le service `meteo_sentinelle.log_treatment`
enregistre une application :

```yaml
action: meteo_sentinelle.log_treatment
data:
  target: powdery_mildew
  tree: Pommier Golden du fond   # omis = tous les arbres concernés
  product: Soufre mouillable
  residual_days: 10
  rainfast_mm: 20
```

L'intégration en déduit une entité **Protection mildiou / oïdium**
donnant la date de fin de protection, en tenant compte de la rémanence
**et du lessivage** : au-delà du cumul de pluie déclaré, la protection
est considérée comme perdue même si la rémanence n'est pas écoulée.
Tant qu'une protection est active, le niveau de risque affiché est
rétrogradé d'un cran.

Le suivi est **par arbre** : vous pouvez traiter le pommier aujourd'hui
et le poirier la semaine prochaine sans que les deux se confondent.

Aucune base de produits n'est embarquée : renseignez rémanence et
résistance au lavage d'après l'étiquette de ce que vous appliquez.

### Limites assumées

Ces modèles reproduisent fidèlement des critères publiés, mais restent
en deçà d'un outil professionnel sur trois points :

- **l'inoculum n'est pas modélisé** — trois jours humides en avril sans
  foyer à proximité sont inoffensifs ; les mêmes après une déclaration
  chez le voisin sont critiques. Sans réseau de surveillance régional,
  ces modèles supposent le pathogène présent et alertent donc parfois
  pour rien ;
- **pas de suivi de cohortes d'infection** (latence, sortie des
  lésions) ;
- **aucune validation au champ** — les modèles experts sont calibrés
  sur des essais multi-années et multi-régions.

À utiliser comme aide à la vigilance, pas comme avis phytosanitaire.

### Sources

- Critères de Hutton — [AHDB / James Hutton Institute](https://potatoes.ahdb.org.uk/development-and-implementation-of-a-new-national-warning-system-for-potato-late-blight-in-great-britain-hutton-criteria)
- Indice Gubler-Thomas — [UC IPM, Gubler *et al.* 1999](https://uspest.org/npdn/riskdoc.html)
- Températures critiques T10/T90 — [WSU, publié par USU Extension IPM-012-11](https://extension.usu.edu/productionhort/files/CriticalTemperaturesFrostDamageFruitTrees.pdf)
- Degrés-jours et phénologie du pommier — [MSU Enviroweather](https://enviroweather.msu.edu/weathermodels/growingdegreedays)

## Feuille de route

- v0.4 : plusieurs arbres surveillés, chacun avec son stade et ses
  calculs ; avancement automatique par degrés-jours ; alertes par
  événements, notifications et blueprint.
- v0.5 : renommage en Météo Sentinelle, positionnement ouvert à toute
  station météo, domaine `meteo_sentinelle`.
- v0.6 : interface entièrement traduite (français et anglais).
- v0.7 : blueprint de protection contre le gel, prêt à l'emploi.
- v0.8 : documentation anglaise par défaut, blueprints bilingues,
  notifications traduites.
- **v1.0 (actuelle)** : première version stable — les fonctionnalités,
  les noms d'entités et le contenu des événements sont désormais
  considérés comme figés, et l'intégration est disponible dans le
  magasin HACS par défaut.
- Ensuite : tavelure du pommier (table de Mills), cohortes d'infection
  avec latence pour le mildiou, sensibilité variétale, apprentissage du
  décalage de degrés-jours sur les corrections manuelles.

Voir [ARCHITECTURE.md](ARCHITECTURE.md) pour le détail des choix de
conception.

## Langue de l'interface

L'intégration s'affiche dans la langue de Home Assistant : espèces,
stades phénologiques, niveaux de risque et noms de capteurs existent en
français et en anglais, et basculent automatiquement selon la langue de
l'utilisateur.

Conséquence à connaître pour les automatisations : les entités exposent
une **clé technique** comme état (`full_bloom`), pas le texte affiché
(« Pleine floraison »). C'est Home Assistant qui traduit à l'affichage.
Une condition doit donc comparer la clé :

```yaml
condition:
  - condition: state
    entity_id: sensor.pommier_stade_phenologique
    state: "full_bloom"   # et non « Pleine floraison »
```

Les notifications sont traduites elles aussi, en composant leur texte à
partir des traductions au moment de l'envoi.

Les blueprints font seule exception : Home Assistant n'offre aucun
mécanisme de traduction pour eux, ils existent donc en deux fichiers
distincts, anglais et français.

## Icône dans HACS et Home Assistant

Depuis Home Assistant 2026.3, une intégration personnalisée peut fournir
sa propre icône **directement dans son dossier**, sans passer par le
dépôt central `home-assistant/brands` (qui n'accepte d'ailleurs plus les
soumissions d'intégrations personnalisées). C'est la méthode que ce
projet utilise :

```
custom_components/meteo_sentinelle/brand/
├── icon.png      (256×256)
├── icon@2x.png   (512×512)
└── icon.svg      (source, non utilisée par Home Assistant)
```

Nécessite Home Assistant 2026.3 ou supérieur ; sur une version plus
ancienne, l'icône ne s'affiche nulle part (repli silencieux sur le
générique), sans que cela n'affecte le fonctionnement de l'intégration.

## Soutenir le projet

Si cette intégration vous fait gagner du temps (ou sauve vos plants de
tomates !), vous pouvez m'offrir un café :

👉 [Buy Me a Coffee](https://buymeacoffee.com/sdavid66)

## Licence

GPL-3.0 — voir [LICENSE](LICENSE). Le code reste libre : vous pouvez l'utiliser, le modifier et le redistribuer, à condition que toute version dérivée reste elle aussi open source sous la même licence.
