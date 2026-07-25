"""Mildiou de la pomme de terre et de la tomate (*Phytophthora infestans*).

Deux critères sont évalués en parallèle sur des séries horaires :

- **Smith Period** (Smith, 1956) — deux jours consécutifs comptant
  chacun au moins 11 heures continues à HR ≥ 90 % et une température
  minimale ≥ 10 °C. Standard britannique historique.
- **Critères de Hutton** (James Hutton Institute / AHDB, 2017) — mêmes
  deux jours consécutifs avec T min ≥ 10 °C, mais seulement **6 heures**
  à HR ≥ 90 %. Ces critères remplacent officiellement la Smith Period
  au Royaume-Uni : les essais en enceinte climatique ont montré que les
  isolats contemporains infectent dans des conditions nettement moins
  humides que ne le prévoyait Smith, qui sous-détecte donc les
  génotypes agressifs modernes.

Le niveau de risque est piloté par Hutton, plus sensible. La Smith
Period reste exposée pour comparaison et continuité.

Un capteur d'humectation foliaire, quand il est disponible, remplace le
proxy HR ≥ 90 % (voir `hourly.is_wet`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..const import RISK_NONE, RISK_SEVERE, RISK_WARNING, RISK_WATCH
from .hourly import DayMetrics, HourlySample, complete_days, day_metrics, longest_true_run

#: Températures cardinales retenues pour la réponse thermique continue
#: de P. infestans (min, optimum, max) en °C.
CARDINAL_TEMPS = (3.0, 20.0, 30.0)

HUMIDITY_THRESHOLD = 90.0
MIN_TEMP = 10.0
SMITH_WET_HOURS = 11
HUTTON_WET_HOURS = 6
CONSECUTIVE_DAYS = 2


@dataclass
class LateBlightRisk:
    level: str
    hutton_met: bool = False
    smith_met: bool = False
    hutton_consecutive_days: int = 0
    smith_consecutive_days: int = 0
    favourable_days: int = 0
    #: Pression thermique moyenne (0-1) sur les jours favorables.
    thermal_pressure: float = 0.0
    last_day_min_temp: float | None = None
    last_day_wet_hours: int = 0
    evaluated_days: int = 0
    days: list[dict] = field(default_factory=list)


def _favourable(metrics: DayMetrics, wet_hours_required: int) -> bool:
    return (
        metrics.temp_min is not None
        and metrics.temp_min >= MIN_TEMP
        and metrics.wet_hours_continuous >= wet_hours_required
    )


def evaluate_late_blight_risk(hourly: list[HourlySample]) -> LateBlightRisk:
    """Évalue le risque à partir d'une série horaire (idéalement ≥ 72 h)."""
    days = complete_days(hourly)
    if not days:
        return LateBlightRisk(level=RISK_NONE)

    metrics = [
        day_metrics(day, hours, HUMIDITY_THRESHOLD, CARDINAL_TEMPS)
        for day, hours in days
    ]

    hutton_flags = [_favourable(m, HUTTON_WET_HOURS) for m in metrics]
    smith_flags = [_favourable(m, SMITH_WET_HOURS) for m in metrics]

    hutton_run = longest_true_run(hutton_flags)
    smith_run = longest_true_run(smith_flags)

    hutton_met = hutton_run >= CONSECUTIVE_DAYS
    smith_met = smith_run >= CONSECUTIVE_DAYS

    favourable_metrics = [m for m, ok in zip(metrics, hutton_flags) if ok]
    pressure = (
        sum(m.thermal_pressure for m in favourable_metrics) / len(favourable_metrics)
        if favourable_metrics
        else 0.0
    )

    if hutton_met:
        level = RISK_SEVERE
    elif hutton_run == 1:
        # Une seule journée favorable : la sévérité dépend de la
        # « qualité » thermique de cette journée pour le pathogène.
        level = RISK_WARNING if pressure >= 0.6 else RISK_WATCH
    else:
        level = RISK_NONE

    last = metrics[-1]
    return LateBlightRisk(
        level=level,
        hutton_met=hutton_met,
        smith_met=smith_met,
        hutton_consecutive_days=hutton_run,
        smith_consecutive_days=smith_run,
        favourable_days=sum(hutton_flags),
        thermal_pressure=round(pressure, 3),
        last_day_min_temp=last.temp_min,
        last_day_wet_hours=last.wet_hours_continuous,
        evaluated_days=len(metrics),
        days=[
            {
                "date": m.day.isoformat(),
                "temp_min": m.temp_min,
                "wet_hours_continuous": m.wet_hours_continuous,
                "hutton": hf,
                "smith": sf,
            }
            for m, hf, sf in zip(metrics, hutton_flags, smith_flags)
        ],
    )
