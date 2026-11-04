"""Avancement automatique du stade phénologique par degrés-jours.

Principe
--------
Le développement d'un arbre fruitier au printemps suit l'accumulation de
chaleur, pas le calendrier. On cumule donc des **degrés-jours de
croissance** (GDD) depuis le 1er janvier, et on compare ce cumul à des
seuils publiés par stade.

Méthode de calcul retenue : moyenne journalière simple,
``GDD = max(0, (Tmax + Tmin) / 2 - Tbase)``, avec **Tbase = 5,6 °C**
(42 °F). C'est la base utilisée par les services de vulgarisation
nord-américains pour les arbres fruitiers (MSU Enviroweather, NEWA), d'où
proviennent les seuils ci-dessous.

Limite importante et assumée
----------------------------
Ces seuils sont **calibrés régionalement**. Les valeurs de référence
proviennent du Michigan ; sous un autre climat, une autre latitude ou
avec une autre variété, les mêmes stades surviennent à des cumuls
sensiblement différents. Deux garde-fous en découlent :

1. un **décalage régional** réglable par arbre (`gdd_offset`) permet de
   recaler la série sur les observations réelles du jardin ;
2. toute correction manuelle du stade **fait autorité** : elle devient
   la nouvelle référence, et l'avancement automatique repart de là.

L'avancement est **monotone** : le modèle ne fait jamais reculer un
stade. Un redoux en février ne peut pas « défaire » une floraison
constatée.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .crops import CROPS, REST_STAGES, stage_options
from .season import season_year as _season_year

#: Température de base des degrés-jours arbres fruitiers (42 °F).
GDD_BASE_C = 5.6

#: Seuils de cumul GDD (base 5,6 °C, depuis le 1er janvier) marquant
#: l'entrée dans chaque stade. Ordre = ordre phénologique.
#:
#: Référence principale : début de floraison ≈ 370 DD42 et fin de
#: floraison ≈ 749 DD42 pour le pommier (MSU Enviroweather). Les stades
#: intermédiaires sont interpolés sur cette échelle et alignés sur les
#: séquences de stades des tables WSU utilisées pour le gel.
STAGE_GDD: dict[str, dict[str, float]] = {
    "apple": {
        "silver_tip": 90,
        "green_tip": 130,
        "half_inch_green": 200,
        "tight_cluster": 280,
        "first_pink": 330,
        "full_pink": 370,
        "first_bloom": 420,
        "full_bloom": 500,
    },
    "pear": {
        "swollen_bud": 80,
        "bud_burst": 120,
        "green_cluster": 190,
        "white_bud": 260,
        "full_white": 310,
        "first_bloom": 360,
        "full_bloom": 420,
        "petal_fall": 520,
    },
    "apricot": {
        "first_swell": 50,
        "tip_separation": 90,
        "first_white": 150,
        "first_bloom": 190,
        "full_bloom": 230,
        "in_the_shuck": 330,
        "shuck_split": 430,
    },
    "plum": {
        "swollen_bud": 70,
        "side_white": 110,
        "green_tip": 160,
        "tight_cluster": 220,
        "first_white": 280,
        "first_bloom": 320,
        "full_bloom": 370,
        "post_bloom": 470,
    },
    "peach": {
        "swollen_bud": 60,
        "calyx_green": 110,
        "quarter_inch_green": 160,
        "pink": 220,
        "first_bloom": 270,
        "full_bloom": 320,
        "post_bloom": 420,
    },
    "sweet_cherry": {
        "swollen_bud": 70,
        "bud_burst": 120,
        "tight_cluster": 190,
        "white_bud": 250,
        "first_bloom": 300,
        "full_bloom": 350,
        "post_bloom": 450,
    },
    "vine": {
        "dormant": 0,
        "bud_swell": 150,
        "bud_burst": 220,
        "first_leaves": 300,
        "shoots_10cm": 400,
    },
    # Annuelles : aucune phénologie suivie, ce seuil marque seulement le
    # moment de recommencer à surveiller. Il est volontairement précoce —
    # un plant sorti trop tôt et gelé sans alerte coûte plus cher qu'une
    # veille commencée quelques semaines avant la plantation.
    "tender_annual": {"growing": 100},
    "potato": {"emerged": 100},
}

#: Durée indicative entre pleine floraison et récolte (jours), à titre
#: informatif pour l'utilisateur. Très dépendante de la variété.
BLOOM_TO_HARVEST_DAYS: dict[str, int] = {
    "apple": 145,
    "pear": 135,
    "apricot": 110,
    "plum": 130,
    "peach": 110,
    "sweet_cherry": 60,
    "vine": 150,
}

#: Stades marquant la floraison, utilisés pour dater la nouaison.
BLOOM_STAGES = {"full_bloom", "first_bloom"}


@dataclass
class GddState:
    """Cumul de degrés-jours de la saison en cours."""

    season_year: int
    total: float = 0.0
    #: Dernier jour complet déjà intégré (évite tout double comptage).
    last_day: str | None = None
    #: Premier jour intégré de la saison. Un cumul censé partir du
    #: 1er janvier mais commencé en avril **sous-estime** le total, et le
    #: sous-estime silencieusement : ce champ permet de le signaler.
    first_day: str | None = None
    #: Détail des derniers jours, pour diagnostic.
    recent: list[dict] = field(default_factory=list)
    #: Mois de début de saison : janvier, ou juillet dans l'hémisphère sud.
    start_month: int = 1

    @property
    def complete_season(self) -> bool:
        """Le cumul couvre-t-il bien le début de la saison ?

        Tolérance à janvier : sous nos climats, les degrés-jours des
        toutes premières semaines sont négligeables, et exiger le
        1er janvier au jour près rendrait le drapeau inutilement
        alarmiste.
        """
        if self.first_day is None:
            return False
        return self.first_day <= f"{self.season_year}-{self.start_month:02d}-31"


def daily_gdd(
    temp_min: float | None,
    temp_max: float | None,
    base: float = GDD_BASE_C,
    upper: float | None = None,
) -> float:
    """Degrés-jours d'une journée (méthode de la moyenne simple).

    `base` et `upper` sont paramétrables car tous les modèles thermiques
    ne partagent pas le même barème : la phénologie des arbres fruitiers
    travaille en base 5,6 °C sans plafond, le carpocapse en base 10 °C
    avec un plafond à 31,1 °C, la mouche de la cerise en base 5 °C.

    Le plafond est appliqué en *horizontal cutoff* : les températures
    sont écrêtées **avant** la moyenne, ce qui traduit le fait qu'au-delà
    d'un certain seuil le développement cesse d'accélérer. Écrêter aussi
    la minimale évite qu'une journée entièrement au-dessus du plafond ne
    produise un cumul aberrant.
    """
    if temp_min is None or temp_max is None:
        return 0.0
    if upper is not None:
        temp_max = min(temp_max, upper)
        temp_min = min(temp_min, upper)
    return max(0.0, (temp_max + temp_min) / 2.0 - base)


def accumulate(
    state: GddState,
    days: list[tuple[date, float | None, float | None]],
    base: float = GDD_BASE_C,
    upper: float | None = None,
) -> GddState:
    """Ajoute les journées complètes non encore comptées.

    `days` : liste de (jour, temp_min, temp_max) triée chronologiquement.
    Idempotent : une journée déjà intégrée est ignorée.
    """
    recent = list(state.recent)
    total = state.total
    last_day = state.last_day
    first_day = state.first_day
    season = state.season_year

    for day, tmin, tmax in days:
        # Changement de saison : le cumul repart de zéro, au 1er janvier
        # ou au 1er juillet selon l'hémisphère.
        #
        # Seulement vers l'avant : début janvier, l'historique relu contient
        # encore des jours de décembre, qui ne doivent pas rouvrir la saison
        # passée et lui faire perdre son cumul.
        day_season = _season_year(day, state.start_month)
        if day_season < season:
            continue
        if day_season > season:
            season = day_season
            total = 0.0
            last_day = None
            first_day = None
            recent = []

        day_str = day.isoformat()
        if last_day is not None and day_str <= last_day:
            continue

        value = daily_gdd(tmin, tmax, base, upper)
        total += value
        last_day = day_str
        if first_day is None:
            first_day = day_str
        recent.append(
            {"date": day_str, "gdd": round(value, 1), "total": round(total, 1)}
        )

    return GddState(
        season_year=season,
        total=total,
        last_day=last_day,
        first_day=first_day,
        recent=recent[-14:],
        start_month=state.start_month,
    )


def roll_season(state: GddState, season: int) -> GddState:
    """Ouvre la saison `season` si le cumul en est encore à une précédente.

    `accumulate` n'y suffit pas : il ne voit passer un nouveau jour qu'une
    fois celui-ci complet. Pendant tout le premier jour de la saison, le
    cumul resterait celui de l'année écoulée, assez élevé pour réveiller
    d'un coup tous les arbres au dernier stade.
    """
    if state.season_year >= season:
        return state
    return GddState(season_year=season, start_month=state.start_month)


def ordered_stages(crop: str) -> list[str]:
    """Stades d'une espèce, dans l'ordre phénologique croissant."""
    table = STAGE_GDD.get(crop)
    if not table:
        return []
    return sorted(table, key=lambda stage: table[stage])


def stage_for_gdd(crop: str, gdd_total: float, offset: float = 0.0) -> str | None:
    """Stade attendu pour un cumul de degrés-jours donné.

    `offset` recale la série sur les observations locales : positif si le
    verger est en avance sur la table, négatif s'il est en retard.
    """
    table = STAGE_GDD.get(crop)
    if not table:
        return None
    effective = gdd_total + offset
    reached = [stage for stage in ordered_stages(crop) if effective >= table[stage]]
    return reached[-1] if reached else None


def stage_path(crop: str) -> list[dict]:
    """Stades d'une espèce dans l'ordre, avec leur seuil et leur sensibilité.

    C'est ce qu'il faut pour montrer où en est l'arbre et à quels moments
    le gel est dangereux, sans recopier les tables dans la carte.
    """
    table = STAGE_GDD.get(crop, {})
    entry = CROPS.get(crop)
    path: list[dict] = []
    for stage in stage_options(crop):
        limits = entry.stages.get(stage) if entry else None
        path.append(
            {
                "key": stage,
                "gdd": table.get(stage),
                "t10": limits[0] if limits else None,
            }
        )
    return path


def next_stage_threshold(crop: str, stage: str | None) -> tuple[str, float] | None:
    """(stade suivant, seuil GDD) après le stade donné, ou None si dernier."""
    stages = ordered_stages(crop)
    if not stages:
        return None
    table = STAGE_GDD[crop]
    if stage is None or (stage in REST_STAGES and stage not in stages):
        return stages[0], table[stages[0]]
    if stage not in stages:
        return None
    index = stages.index(stage)
    if index + 1 >= len(stages):
        return None
    following = stages[index + 1]
    return following, table[following]


def propose_advance(
    crop: str,
    current_stage: str | None,
    gdd_total: float,
    offset: float = 0.0,
) -> str | None:
    """Nouveau stade à appliquer, ou None s'il n'y a rien à changer.

    L'avancement est strictement **monotone** : si le stade attendu est
    antérieur au stade courant (météo fraîche après une correction
    manuelle, ou recalage), on ne redescend pas.
    """
    stages = ordered_stages(crop)
    if not stages:
        return None

    expected = stage_for_gdd(crop, gdd_total, offset)
    if expected is None or expected == current_stage:
        return None

    if current_stage is None:
        return expected
    if current_stage not in stages:
        return expected

    if stages.index(expected) > stages.index(current_stage):
        return expected
    return None


def wake_stage(crop: str, gdd_total: float, offset: float = 0.0) -> str | None:
    """Premier stade d'activité, s'il est atteint ; sinon None.

    Sert aux arbres dont l'avancement automatique est désactivé. Eux aussi
    passent en repos, et personne ne pense à les réveiller en février : les
    laisser endormis ferait taire les alertes de gel au pire moment. Ils
    reprennent donc au premier stade, et la suite reste à l'utilisateur.
    """
    table = STAGE_GDD.get(crop)
    if not table:
        return None
    for stage in ordered_stages(crop):
        if stage not in REST_STAGES:
            return stage if gdd_total + offset >= table[stage] else None
    return None


def days_to_harvest(
    crop: str, bloom_date: datetime | date | None, today: date
) -> int | None:
    """Jours restants estimés avant récolte, depuis la date de floraison.

    Estimation grossière : les durées floraison → récolte varient
    fortement selon la variété. Fournie à titre indicatif.
    """
    if bloom_date is None:
        return None
    duration = BLOOM_TO_HARVEST_DAYS.get(crop)
    if duration is None:
        return None
    if isinstance(bloom_date, datetime):
        bloom_date = bloom_date.date()
    elapsed = (today - bloom_date).days
    return max(0, duration - elapsed)
