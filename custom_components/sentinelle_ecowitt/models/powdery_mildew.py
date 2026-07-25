"""Modèle de risque d'oïdium (powdery mildew).

Contrairement au mildiou, l'oïdium ne nécessite pas d'eau libre sur la
feuille : il favorise les journées chaudes (21-30 °C) suivies de nuits
humides (>= 90 % HR). Modèle simplifié à but indicatif.

Note (v0.1) : la séparation jour/nuit des échantillons n'est pas encore
faite par le coordinator — voir ARCHITECTURE.md, section Roadmap.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..const import RISK_NONE, RISK_WARNING, RISK_WATCH


@dataclass
class PowderyMildewRisk:
    level: str
    day_temp_avg: float | None
    night_humidity_avg: float | None


def evaluate_powdery_mildew_risk(
    day_temps: list[float],
    night_humidities: list[float],
) -> PowderyMildewRisk:
    day_avg = sum(day_temps) / len(day_temps) if day_temps else None
    night_avg = (
        sum(night_humidities) / len(night_humidities) if night_humidities else None
    )

    level = RISK_NONE
    if day_avg is not None and night_avg is not None:
        if 21 <= day_avg <= 30 and night_avg >= 90:
            level = RISK_WARNING
        elif 18 <= day_avg <= 32 and night_avg >= 80:
            level = RISK_WATCH

    return PowderyMildewRisk(
        level=level, day_temp_avg=day_avg, night_humidity_avg=night_avg
    )
