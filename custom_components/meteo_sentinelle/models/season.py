"""Saisons du site : hémisphère, début de saison et repos hivernal.

Un modèle agronomique n'a de sens que sur une plante en activité. Sans
notion de saison, un pommier resté au stade « pleine floraison » depuis
le printemps déclenche une alerte de gel en novembre, sur des rameaux
nus. Ce module répond à deux questions, à partir du lieu déclaré dans
Home Assistant :

**Quand la saison commence-t-elle ?** Au 1er janvier dans l'hémisphère
nord, au 1er juillet dans l'hémisphère sud : c'est la convention de
l'indice de saison de végétation de l'ETCCDI, et la seule qui place tout
l'hiver d'un côté de la coupure. Cumuler des degrés-jours depuis le
1er janvier à Santiago couperait l'été austral en deux.

**Quand le repos commence-t-il ?** Au premier de ces deux événements :

- une **date calendaire** dépendant du lieu. Elle part du 5 novembre à
  45° de latitude au niveau de la mer et avance avec la latitude et
  l'altitude, dans l'esprit de la loi bioclimatique de Hopkins. Les pentes
  retenues sont volontairement plus douces que celles de Hopkins, établies
  au printemps : la chute des feuilles varie moins que le débourrement.
  Ce sont des ordres de grandeur, pas une calibration ;
- une **vague de froid observée** : six jours consécutifs sous 5 °C de
  moyenne journalière, le critère de fin de saison de l'ETCCDI. Elle
  rattrape ce que le calendrier ignore, un climat continental notamment.

**La fin du repos n'est pas une date.** La reprise suit les degrés-jours,
comme tout le reste de la phénologie : la plante se réveille en
atteignant le seuil de son premier stade, ce que `phenology.wake_stage`
détermine. Un printemps tardif la laisse donc endormie plus longtemps.

Sous les tropiques, il n'y a pas d'hiver à proprement parler : le repos
n'est pas appliqué et la saison reste calée sur l'année civile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

HEMISPHERE_NORTH = "north"
HEMISPHERE_SOUTH = "south"

PHASE_GROWING = "growing"
PHASE_WINTER_REST = "winter_rest"
#: Lieu tropical : pas d'hiver, donc pas de repos appliqué.
PHASE_NO_WINTER = "no_winter"
#: Repos désactivé dans les options de l'intégration.
PHASE_DISABLED = "disabled"
PHASES = [PHASE_GROWING, PHASE_WINTER_REST, PHASE_NO_WINTER, PHASE_DISABLED]

TRIGGER_CALENDAR = "calendar"
TRIGGER_COLD_SPELL = "cold_spell"

#: Latitude des tropiques : en deçà, pas de repos hivernal.
TROPIC_LATITUDE = 23.5

#: Date de référence du repos, à 45° de latitude et au niveau de la mer.
REFERENCE_LATITUDE = 45.0
REFERENCE_MONTH_NORTH = 11
REFERENCE_MONTH_SOUTH = 5
REFERENCE_DAY = 5
DAYS_PER_DEGREE = 3.0
DAYS_PER_100M = 2.0
#: Bornes du décalage : le 25 septembre et le 15 décembre dans le nord.
#: La borne tardive garantit quelques semaines de repos avant le début de
#: la saison suivante, même aux latitudes les plus douces.
EARLIEST_SHIFT_DAYS = -41
LATEST_SHIFT_DAYS = 40

#: Vague de froid : critère de fin de saison de végétation de l'ETCCDI.
COLD_SPELL_DAYS = 6
COLD_SPELL_MEAN_C = 5.0
#: Une semaine froide au cœur du printemps n'endort pas un verger : seule
#: la fin de saison est examinée, à partir de ce nombre de mois.
AUTUMN_AFTER_MONTHS = 8


@dataclass(frozen=True)
class SiteClimate:
    """Ce que le lieu d'installation dit des saisons."""

    latitude: float
    elevation: float = 0.0

    @property
    def hemisphere(self) -> str:
        return HEMISPHERE_SOUTH if self.latitude < 0 else HEMISPHERE_NORTH

    @property
    def has_winter(self) -> bool:
        return abs(self.latitude) >= TROPIC_LATITUDE

    @property
    def season_start_month(self) -> int:
        """Mois de début de saison : juillet dans le sud, sauf sous les tropiques."""
        if self.has_winter and self.hemisphere == HEMISPHERE_SOUTH:
            return 7
        return 1


@dataclass(frozen=True)
class SeasonInfo:
    """Situation du site à une date donnée."""

    #: Année du début de la saison courante.
    season_year: int
    season_start: date
    hemisphere: str
    #: Le repos est-il applicable sur ce site ?
    rest_enabled: bool
    #: Début du repos de la saison courante, ou None s'il ne s'applique pas.
    rest_start: date | None = None
    trigger: str | None = None
    #: La date de début du repos est atteinte. La saison suivante n'a pas
    #: encore commencé : aucun stade ne doit avancer d'ici là.
    in_rest: bool = False


def season_year(day: date, start_month: int = 1) -> int:
    """Année de début de la saison à laquelle appartient un jour."""
    return day.year if day.month >= start_month else day.year - 1


def calendar_rest_start(climate: SiteClimate, year: int) -> date:
    """Début calendaire du repos pour la saison commencée l'année `year`."""
    shift = (abs(climate.latitude) - REFERENCE_LATITUDE) * -DAYS_PER_DEGREE
    shift -= max(0.0, climate.elevation) / 100.0 * DAYS_PER_100M
    shift = max(EARLIEST_SHIFT_DAYS, min(LATEST_SHIFT_DAYS, round(shift)))

    if climate.hemisphere == HEMISPHERE_SOUTH:
        reference = date(year + 1, REFERENCE_MONTH_SOUTH, REFERENCE_DAY)
    else:
        reference = date(year, REFERENCE_MONTH_NORTH, REFERENCE_DAY)
    return reference + timedelta(days=shift)


def _autumn_start(climate: SiteClimate, year: int) -> date:
    month = climate.season_start_month + AUTUMN_AFTER_MONTHS
    return date(year + (month - 1) // 12, (month - 1) % 12 + 1, 1)


def find_cold_spell(
    days: list[tuple[date, float]], climate: SiteClimate
) -> date | None:
    """Jour où s'achève la première vague de froid automnale, s'il y en a une.

    `days` : (jour, température moyenne) triés chronologiquement. Un jour
    manquant interrompt la série : une panne de capteur ne vaut pas
    observation du froid.
    """
    run = 0
    previous: date | None = None
    for day, mean in days:
        year = season_year(day, climate.season_start_month)
        if mean >= COLD_SPELL_MEAN_C or day < _autumn_start(climate, year):
            run = 0
            previous = None
            continue
        contiguous = previous is not None and day - previous == timedelta(days=1)
        run = run + 1 if contiguous else 1
        previous = day
        if run >= COLD_SPELL_DAYS:
            return day
    return None


def evaluate(
    climate: SiteClimate,
    today: date,
    cold_spell: date | None = None,
    enabled: bool = True,
) -> SeasonInfo:
    """Situe le site dans sa saison.

    `cold_spell` n'est retenue que si elle appartient à la saison courante :
    celle de l'automne dernier ne dit rien de l'automne prochain.
    """
    start_month = climate.season_start_month
    year = season_year(today, start_month)
    common = {
        "season_year": year,
        "season_start": date(year, start_month, 1),
        "hemisphere": climate.hemisphere,
    }
    if not enabled or not climate.has_winter:
        return SeasonInfo(rest_enabled=False, **common)

    rest_start = calendar_rest_start(climate, year)
    trigger = TRIGGER_CALENDAR
    if (
        cold_spell is not None
        and season_year(cold_spell, start_month) == year
        and cold_spell < rest_start
    ):
        rest_start = cold_spell
        trigger = TRIGGER_COLD_SPELL

    return SeasonInfo(
        rest_enabled=True,
        rest_start=rest_start,
        trigger=trigger,
        in_rest=today >= rest_start,
        **common,
    )


def rest_due(
    info: SeasonInfo,
    rest_season: int | None,
    stage_changed_on: date | None,
) -> int | None:
    """Saison dont le repos reste à appliquer à un arbre, ou None.

    Le passage en repos n'a lieu **qu'une fois par saison** : il suffit de
    mémoriser la saison déjà traitée pour qu'un stade corrigé à la main en
    plein hiver ne soit pas réécrasé au cycle suivant.

    Le second cas rattrape un repos manqué, Home Assistant arrêté ou mise à
    jour installée pendant l'hiver : un stade qui n'a pas bougé depuis la
    saison passée est forcément périmé.
    """
    if not info.rest_enabled:
        return None
    if info.in_rest:
        return info.season_year if rest_season != info.season_year else None
    if (
        (rest_season is None or rest_season < info.season_year - 1)
        and stage_changed_on is not None
        and stage_changed_on < info.season_start
    ):
        return info.season_year - 1
    return None
