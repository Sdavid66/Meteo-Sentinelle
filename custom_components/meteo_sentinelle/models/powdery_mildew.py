"""Oïdium — indice de risque Gubler-Thomas.

Modèle développé à UC Davis (Gubler & Thomas) pour l'oïdium de la vigne
(*Erysiphe necator*), largement repris pour d'autres cultures. Il pilote
l'espacement des traitements via un indice cumulatif de 0 à 100.

**Deux phases.**

*Initiation* — l'épidémie démarre après trois journées consécutives
comptant chacune au moins 6 heures **continues** entre 21,1 et 29,4 °C
(70-85 °F). L'indice part de 0 et gagne 20 points par telle journée ;
toute journée qui échoue le remet à 0. À 60, l'épidémie est lancée.

*Suivi* — chaque jour ensuite :

| Condition | Points |
|---|---|
| ≥ 6 h continues entre 21,1 et 29,4 °C | +20 |
| < 6 h continues dans cette plage | −10 |
| ≥ 35 °C pendant plus de 15 min | −10 |
| les deux (≥ 6 h dans la plage *et* pic ≥ 35 °C) | +10 |

Indice borné à [0, 100]. Bandes de risque publiées : 0-30 faible,
40-60 modéré, > 60 élevé.

**Correction ajoutée par ce plugin.** Contrairement au mildiou,
l'oïdium est *inhibé* par l'eau libre : une pluie lessive les conidies
et gêne la germination. Le Gubler-Thomas d'origine ne modélise pas la
pluie. On applique donc une pénalité de −10 points au-delà de 2,5 mm de
pluie sur la journée, en reprenant la règle du modèle « Hop Powdery
Mildew » (variante Cascade, D. Gent), lui-même dérivé de Gubler-Thomas.
Cette pénalité est signalée comme extension et peut être désactivée.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..const import RISK_NONE, RISK_SEVERE, RISK_WARNING, RISK_WATCH
from .hourly import HourlySample, complete_days, longest_run

#: Plage optimale de reproduction conidienne : 70-85 °F.
OPTIMAL_LOW = 21.1
OPTIMAL_HIGH = 29.4
#: Températures léthales pour les conidies : 95 °F.
LETHAL_TEMP = 35.0
#: Durée continue requise dans la plage optimale.
REQUIRED_HOURS = 6
#: Nombre de journées consécutives déclenchant l'épidémie.
INITIATION_DAYS = 3
EPIDEMIC_INDEX = 60
#: Pluie journalière à partir de laquelle on applique la pénalité.
RAIN_PENALTY_MM = 2.5
RAIN_PENALTY_POINTS = 10

INDEX_MIN = 0
INDEX_MAX = 100


@dataclass
class DailyGTMetrics:
    """Indicateurs journaliers nécessaires à l'indice."""

    day: date
    optimal_hours_continuous: int = 0
    hours_at_lethal: int = 0
    rain_mm: float = 0.0


@dataclass
class PowderyMildewRisk:
    level: str
    index: int = 0
    epidemic_started: bool = False
    #: Dernier jour complet intégré à l'indice.
    last_processed_day: str | None = None
    last_day_optimal_hours: int = 0
    last_day_rain_mm: float = 0.0
    last_day_delta: int = 0
    spray_interval_days: int | None = None
    days: list[dict] = field(default_factory=list)


def daily_metrics(day: date, hours: list[HourlySample]) -> DailyGTMetrics:
    """Extrait les indicateurs Gubler-Thomas d'une journée."""
    return DailyGTMetrics(
        day=day,
        optimal_hours_continuous=longest_run(
            hours,
            lambda s: s.temp is not None and OPTIMAL_LOW <= s.temp <= OPTIMAL_HIGH,
        ),
        hours_at_lethal=sum(
            1 for s in hours if s.temp is not None and s.temp >= LETHAL_TEMP
        ),
        rain_mm=sum(s.rain_mm for s in hours),
    )


def advance_index(
    index: int,
    epidemic_started: bool,
    metrics: DailyGTMetrics,
    apply_rain_penalty: bool = True,
) -> tuple[int, bool, int]:
    """Fait avancer l'indice d'une journée.

    Renvoie (nouvel indice, épidémie démarrée, variation appliquée).
    """
    in_range = metrics.optimal_hours_continuous >= REQUIRED_HOURS
    # Le pas horaire ne permet pas de mesurer « plus de 15 minutes » :
    # une heure au-dessus du seuil léthal en est la traduction la plus
    # fidèle possible à cette résolution.
    hot = metrics.hours_at_lethal >= 1

    if not epidemic_started:
        # Phase d'initiation : 3 journées consécutives à +20 → 60.
        if in_range:
            new_index = min(index + 20, INDEX_MAX)
        else:
            new_index = 0
        started = new_index >= EPIDEMIC_INDEX
        return new_index, started, new_index - index

    if in_range and hot:
        delta = +10
    elif in_range:
        delta = +20
    else:
        delta = -10

    if apply_rain_penalty and metrics.rain_mm >= RAIN_PENALTY_MM:
        delta -= RAIN_PENALTY_POINTS

    new_index = max(INDEX_MIN, min(INDEX_MAX, index + delta))
    return new_index, True, new_index - index


def risk_level(index: int, epidemic_started: bool) -> str:
    """Traduit l'indice 0-100 dans les niveaux de l'intégration.

    Bandes Gubler-Thomas : 0-30 faible, 40-60 modéré, > 60 élevé. Tant
    que l'épidémie n'est pas déclenchée, le risque reste au plus « à
    surveiller », l'indice ne mesurant alors que la montée en puissance.
    """
    if not epidemic_started:
        return RISK_WATCH if index >= 40 else RISK_NONE
    if index >= 90:
        return RISK_SEVERE
    if index >= 70:
        return RISK_WARNING
    if index >= 40:
        return RISK_WATCH
    return RISK_NONE


def spray_interval(index: int) -> int:
    """Intervalle de traitement conseillé (jours), d'après les bandes UC IPM.

    Valeurs pour fongicides de synthèse ; le soufre demande des
    intervalles plus courts (7 à 21 jours selon la bande).
    """
    if index > 60:
        return 14
    return 21


def evaluate_powdery_mildew_risk(
    hourly: list[HourlySample],
    index: int = 0,
    epidemic_started: bool = False,
    last_processed_day: str | None = None,
    apply_rain_penalty: bool = True,
) -> PowderyMildewRisk:
    """Avance l'indice sur les journées complètes non encore traitées.

    L'indice Gubler-Thomas est **cumulatif sur la saison** : il ne peut
    pas être recalculé depuis une fenêtre glissante de 72 h. L'appelant
    conserve donc l'état (`index`, `epidemic_started`,
    `last_processed_day`) d'un cycle à l'autre et le repasse ici.
    """
    processed: list[dict] = []
    current_index = index
    started = epidemic_started
    last_day = last_processed_day
    last_delta = 0
    last_metrics: DailyGTMetrics | None = None

    for day, hours in complete_days(hourly):
        day_str = day.isoformat()
        if last_day is not None and day_str <= last_day:
            continue  # déjà intégré lors d'un cycle précédent
        metrics = daily_metrics(day, hours)
        current_index, started, last_delta = advance_index(
            current_index, started, metrics, apply_rain_penalty
        )
        last_day = day_str
        last_metrics = metrics
        processed.append(
            {
                "date": day_str,
                "optimal_hours_continuous": metrics.optimal_hours_continuous,
                "hours_at_lethal": metrics.hours_at_lethal,
                "rain_mm": round(metrics.rain_mm, 2),
                "delta": last_delta,
                "index": current_index,
            }
        )

    return PowderyMildewRisk(
        level=risk_level(current_index, started),
        index=current_index,
        epidemic_started=started,
        last_processed_day=last_day,
        last_day_optimal_hours=(
            last_metrics.optimal_hours_continuous if last_metrics else 0
        ),
        last_day_rain_mm=round(last_metrics.rain_mm, 2) if last_metrics else 0.0,
        last_day_delta=last_delta,
        spray_interval_days=spray_interval(current_index) if started else None,
        days=processed,
    )
