"""Ravageurs suivis par degrés-jours.

Le développement d'un insecte suit l'accumulation de chaleur, exactement
comme la phénologie de la plante. C'est ce qui rend ces modèles à la
fois simples et utiles : quelques seuils publiés suffisent à situer une
population dans son cycle, et donc à répondre à la seule question qui
compte — *est-ce le moment d'intervenir ?*

Trois choix de conception structurent ce module.

**Origine du cumul.** Deux familles de modèles coexistent et ne se
mélangent pas :

- ceux qui partent du **1er janvier** (`ORIGIN_SEASON`) — la mouche de la
  cerise, la tordeuse de la grappe. Le cumul est absolu, aucune
  observation n'est requise ;
- ceux qui partent d'un **biofix** (`ORIGIN_BIOFIX`), c'est-à-dire d'un
  événement observé : première capture soutenue au piège à phéromone
  pour le carpocapse, premières pontes pour le doryphore. Sans cet
  ancrage, le cumul n'a aucune signification — un modèle carpocapse
  démarré au 1er janvier se trompe de plusieurs semaines.

Pour cette seconde famille, l'intégration refuse d'inventer un résultat :
tant que le biofix est inconnu, le capteur l'annonce (`awaiting_biofix`)
au lieu d'afficher un niveau faux. Quand un **stade phénologique
d'ancrage** est documenté, un biofix approché peut être posé
automatiquement, mais il est explicitement marqué comme estimé.

**Plafond de température.** Au-delà d'un certain seuil, le développement
ne s'accélère plus. Le carpocapse utilise donc un plafond à 31,1 °C
(88 °F), appliqué par la méthode du *horizontal cutoff* : la température
maximale de la journée est écrêtée avant le calcul de la moyenne.

**Calibration régionale.** Comme pour les degrés-jours phénologiques,
ces seuils viennent de régions précises. Le décalage par arbre
(`gdd_offset`) ne s'applique **pas** ici : il recale la phénologie de la
plante, pas le cycle de l'insecte. Les écarts régionaux se corrigent en
déclarant le biofix réel, ce qui est justement le rôle du piège.

Sources
-------
- Carpocapse (*Cydia pomonella*) — UC IPM, modèle degrés-jours base
  50 °F / plafond 88 °F depuis le biofix.
  https://ipm.ucanr.edu/agriculture/apple/codling-moth/
- Mouche de la cerise (*Rhagoletis cerasi*) — Boller & Remund (1983) :
  430 degrés-jours base 5 °C pour l'émergence des adultes.
- Doryphore (*Leptinotarsa decemlineata*) — University of Wisconsin
  Extension, base 50 °F à partir des premières pontes.
  https://hort.extension.wisc.edu/degree-days-for-common-insect-pests/
- Tordeuse de la grappe (*Lobesia botrana*) — seuil thermique 7 °C et
  bornes de vol par génération, d'après les suivis publiés en vignoble
  istrien (Journal of Central European Agriculture, 2016).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..const import RISK_NONE, RISK_SEVERE, RISK_WARNING, RISK_WATCH
from .phenology import daily_gdd

#: Le cumul démarre au 1er janvier : aucune observation nécessaire.
ORIGIN_SEASON = "season"
#: Le cumul démarre à un événement observé (capture, ponte).
ORIGIN_BIOFIX = "biofix"

#: Conversion des seuils publiés en °F vers des degrés-jours °C.
#: Un degré-jour Fahrenheit vaut 5/9 de degré-jour Celsius.
_F = 1.0 / 1.8


def _dd_f(value: float) -> float:
    """Seuil publié en DD °F, converti en DD °C et arrondi au dixième."""
    return round(value * _F, 1)


@dataclass(frozen=True)
class PestStage:
    """Un jalon du cycle, atteint à partir d'un cumul de degrés-jours."""

    key: str
    #: Cumul (°C·j) à partir duquel ce jalon est considéré atteint.
    dd: float
    #: Niveau de risque tant que ce jalon est le plus avancé atteint.
    #: Il traduit l'urgence d'agir, pas la gravité des dégâts : le stade
    #: où l'insecte est le plus vulnérable porte le niveau le plus élevé.
    level: str
    #: Jalon extrapolé par ce plugin plutôt que publié tel quel.
    extrapolated: bool = False


@dataclass(frozen=True)
class Pest:
    """Un ravageur et son modèle de développement."""

    key: str
    #: Température de base du cumul (°C).
    base: float
    #: Plafond appliqué à la température maximale (°C), ou None.
    upper: float | None
    origin: str
    stages: tuple[PestStage, ...]
    source: str
    #: Stade phénologique servant de biofix approché, faute d'observation.
    biofix_anchor: str | None = None

    @property
    def needs_biofix(self) -> bool:
        return self.origin == ORIGIN_BIOFIX


# ----------------------------------------------------------------------
# Définitions
# ----------------------------------------------------------------------

PEST_CODLING_MOTH = "codling_moth"
PEST_CHERRY_FRUIT_FLY = "cherry_fruit_fly"
PEST_COLORADO_POTATO_BEETLE = "colorado_potato_beetle"
PEST_GRAPEVINE_MOTH = "grapevine_moth"

PESTS: dict[str, Pest] = {
    # ------------------------------------------------------------------
    # Carpocapse des pommes et des poires — le « ver de la pomme ».
    #
    # La larve pénètre le fruit en quelques heures : une fois dedans,
    # plus rien n'est possible. Tout se joue donc sur la fenêtre entre
    # l'éclosion de l'œuf et la pénétration, d'où l'importance du biofix.
    # ------------------------------------------------------------------
    PEST_CODLING_MOTH: Pest(
        key=PEST_CODLING_MOTH,
        base=10.0,  # 50 °F
        upper=31.1,  # 88 °F, horizontal cutoff
        origin=ORIGIN_BIOFIX,
        biofix_anchor="full_bloom",
        source="UC IPM (base 50 °F, plafond 88 °F, depuis le biofix)",
        stages=(
            PestStage("flight", 0.0, RISK_WATCH),
            PestStage("egg_laying", _dd_f(100), RISK_WATCH),
            PestStage("hatch_start", _dd_f(220), RISK_WARNING),
            PestStage("hatch_peak", _dd_f(250), RISK_SEVERE),
            PestStage("oviposition_peak", _dd_f(550), RISK_WARNING),
            PestStage("second_generation", _dd_f(1060), RISK_WATCH),
        ),
    ),
    # ------------------------------------------------------------------
    # Mouche de la cerise — l'émergence dépend de la chaleur du sol au
    # printemps, après une diapause hivernale obligatoire.
    #
    # Un seul seuil est publié (430 °C·j). Les deux autres jalons sont
    # des extrapolations de ce plugin, signalées comme telles : l'un
    # anticipe l'émergence pour laisser le temps de poser les pièges,
    # l'autre couvre la maturation des adultes avant la ponte.
    # ------------------------------------------------------------------
    PEST_CHERRY_FRUIT_FLY: Pest(
        key=PEST_CHERRY_FRUIT_FLY,
        base=5.0,
        upper=None,
        origin=ORIGIN_SEASON,
        source="Boller & Remund (1983) : 430 °C·j base 5 °C",
        stages=(
            PestStage("approach", 375.0, RISK_WATCH, extrapolated=True),
            PestStage("emergence", 430.0, RISK_WARNING),
            PestStage("oviposition", 530.0, RISK_SEVERE, extrapolated=True),
        ),
    ),
    # ------------------------------------------------------------------
    # Doryphore — le cumul part des **premières pontes observées**, ce
    # que rappelle explicitement la source. Les jeunes larves (L1-L2)
    # sont la cible : au stade L4, l'essentiel de la défoliation est
    # déjà fait et l'intervention n'a plus grand intérêt.
    # ------------------------------------------------------------------
    PEST_COLORADO_POTATO_BEETLE: Pest(
        key=PEST_COLORADO_POTATO_BEETLE,
        base=10.0,  # 50 °F
        upper=None,
        origin=ORIGIN_BIOFIX,
        source="University of Wisconsin Extension (base 50 °F, depuis les premières pontes)",
        stages=(
            PestStage("eggs", 0.0, RISK_WATCH),
            PestStage("instar_1", _dd_f(185), RISK_WARNING),
            PestStage("instar_2", _dd_f(240), RISK_SEVERE),
            PestStage("instar_3", _dd_f(300), RISK_WARNING),
            PestStage("instar_4", _dd_f(400), RISK_WATCH),
            PestStage("pupation", _dd_f(675), RISK_NONE),
        ),
    ),
    # ------------------------------------------------------------------
    # Tordeuse de la grappe (eudémis) — trois générations. Les bornes
    # publiées décrivent des **fenêtres de vol** : entre deux vols, les
    # larves sont déjà dans les grappes et le niveau retombe.
    # ------------------------------------------------------------------
    PEST_GRAPEVINE_MOTH: Pest(
        key=PEST_GRAPEVINE_MOTH,
        base=7.0,
        upper=None,
        origin=ORIGIN_SEASON,
        source="Journal of Central European Agriculture (2016), base 7 °C depuis le 1er janvier",
        stages=(
            PestStage("first_flight", 217.9, RISK_WARNING),
            PestStage("first_generation", 406.6, RISK_WATCH),
            PestStage("second_flight", 786.3, RISK_WARNING),
            PestStage("second_generation", 1329.8, RISK_WATCH),
            PestStage("third_flight", 1452.8, RISK_WARNING),
            PestStage("third_generation", 2108.2, RISK_WATCH),
        ),
    ),
}


@dataclass
class PestRisk:
    """Résultat de l'évaluation d'un ravageur pour un arbre."""

    level: str
    pest: str
    #: Jalon courant du cycle de l'insecte, ou None si le premier n'est
    #: pas encore atteint.
    #:
    #: Délibérément nommé « cycle_stage » et non « stage » : l'entité de
    #: risque expose aussi le **stade phénologique de la plante**, et
    #: deux clés homonymes dans les mêmes attributs finiraient par
    #: s'écraser l'une l'autre.
    cycle_stage: str | None = None
    #: Cumul de degrés-jours depuis l'origine du modèle.
    degree_days: float = 0.0
    base_temperature: float = 0.0
    upper_temperature: float | None = None
    origin: str = ORIGIN_SEASON
    #: Le modèle attend un biofix que personne n'a encore déclaré.
    awaiting_biofix: bool = False
    biofix_date: str | None = None
    #: Le biofix a été déduit d'un stade phénologique, pas observé.
    biofix_estimated: bool = False
    next_cycle_stage: str | None = None
    next_cycle_stage_dd: float | None = None
    dd_to_next_cycle_stage: float | None = None
    #: Le jalon courant est une extrapolation de ce plugin.
    extrapolated: bool = False
    #: Le cumul saisonnier ne remonte pas jusqu'au 1er janvier : le
    #: résultat est une **sous-estimation**, pas une erreur aléatoire.
    incomplete_season: bool = False
    source: str = ""
    stages: list[dict] = field(default_factory=list)


def daily_degree_days(
    temp_min: float | None,
    temp_max: float | None,
    base: float,
    upper: float | None = None,
) -> float:
    """Degrés-jours d'une journée pour le barème d'un ravageur.

    Simple alias nommé de `phenology.daily_gdd` : le calcul est le même
    que celui de la phénologie, seuls la base et le plafond changent.
    Une seule implémentation, pour qu'une correction profite aux deux.
    """
    return daily_gdd(temp_min, temp_max, base, upper)


def accumulator_key(pest: Pest) -> str:
    """Identifiant du cumulateur partagé par les modèles de même barème.

    Deux ravageurs de même base et même plafond partagent exactement la
    même série : il serait absurde de l'accumuler deux fois.
    """
    return f"{pest.base:g}:{'' if pest.upper is None else format(pest.upper, 'g')}"


def required_accumulators() -> dict[str, tuple[float, float | None]]:
    """Barèmes (base, plafond) à cumuler pour couvrir tous les ravageurs."""
    return {
        accumulator_key(pest): (pest.base, pest.upper) for pest in PESTS.values()
    }


def current_stage(pest: Pest, degree_days: float) -> PestStage | None:
    """Jalon le plus avancé atteint pour ce cumul."""
    reached = [stage for stage in pest.stages if degree_days >= stage.dd]
    return reached[-1] if reached else None


def next_stage(pest: Pest, degree_days: float) -> PestStage | None:
    """Prochain jalon attendu, ou None si le cycle suivi est terminé."""
    for stage in pest.stages:
        if degree_days < stage.dd:
            return stage
    return None


def evaluate_pest_risk(
    pest_key: str,
    degree_days: float | None,
    *,
    biofix_date: str | None = None,
    biofix_estimated: bool = False,
    complete_season: bool = True,
) -> PestRisk | None:
    """Situe une population dans son cycle.

    `degree_days` est le cumul **depuis l'origine du modèle** : depuis le
    1er janvier, ou depuis le biofix. Le calcul de cette origine est du
    ressort de l'appelant, qui seul connaît l'historique.

    Renvoie None si le ravageur est inconnu. Un modèle à biofix sans
    biofix renvoie un résultat explicitement incomplet (`awaiting_biofix`)
    plutôt qu'un niveau calculé sur une origine arbitraire.

    `complete_season` ne concerne que les modèles partant du 1er janvier.
    Une intégration installée en avril n'a pas les degrés-jours de
    février et mars : son cumul est plus bas que la réalité, et le
    modèle annonce donc le cycle **en retard**. Le drapeau propage
    l'information au lieu de laisser croire à un résultat exact ; la
    saison suivante, partie du 1er janvier, est correcte.
    """
    pest = PESTS.get(pest_key)
    if pest is None:
        return None

    common = {
        "pest": pest_key,
        "base_temperature": pest.base,
        "upper_temperature": pest.upper,
        "origin": pest.origin,
        "source": pest.source,
        "stages": [
            {
                "stage": stage.key,
                "degree_days": stage.dd,
                "level": stage.level,
                "extrapolated": stage.extrapolated,
            }
            for stage in pest.stages
        ],
    }

    if pest.needs_biofix and biofix_date is None:
        return PestRisk(level=RISK_NONE, awaiting_biofix=True, **common)

    # Un cumul relatif à un biofix reste juste même si la saison n'a pas
    # été suivie depuis janvier : c'est une différence, pas un absolu.
    incomplete = pest.origin == ORIGIN_SEASON and not complete_season

    total = max(0.0, degree_days or 0.0)
    stage = current_stage(pest, total)
    following = next_stage(pest, total)

    return PestRisk(
        level=stage.level if stage else RISK_NONE,
        cycle_stage=stage.key if stage else None,
        degree_days=round(total, 1),
        awaiting_biofix=False,
        biofix_date=biofix_date,
        biofix_estimated=biofix_estimated,
        next_cycle_stage=following.key if following else None,
        next_cycle_stage_dd=following.dd if following else None,
        dd_to_next_cycle_stage=(
            round(following.dd - total, 1) if following else None
        ),
        extrapolated=bool(stage and stage.extrapolated),
        incomplete_season=incomplete,
        **common,
    )


def all_stage_keys() -> list[str]:
    """Tous les jalons connus, tous ravageurs confondus.

    Un capteur d'énumération doit annoncer l'ensemble des valeurs qu'il
    peut prendre ; certains jalons sont homonymes d'un ravageur à
    l'autre, d'où la déduplication.
    """
    seen: list[str] = []
    for pest in PESTS.values():
        for stage in pest.stages:
            if stage.key not in seen:
                seen.append(stage.key)
    return seen
