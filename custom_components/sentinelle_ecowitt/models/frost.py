"""Modèle de risque de gel / gelée.

Combine la température courante, le point de rosée, le vent et la
couverture nuageuse (refroidissement radiatif) avec les prévisions
météo à venir pour estimer un niveau de risque et l'heure du prochain
épisode de gel probable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from ..const import RISK_NONE, RISK_SEVERE, RISK_WARNING, RISK_WATCH


@dataclass
class FrostRisk:
    level: str
    min_forecast_temp: float | None
    next_frost_time: datetime | None
    dew_point: float | None


def _dew_point(temp_c: float, humidity_pct: float) -> float:
    """Approximation du point de rosée (formule de Magnus)."""
    a, b = 17.62, 243.12
    gamma = (a * temp_c) / (b + temp_c) + math.log(max(humidity_pct, 1) / 100.0)
    return (b * gamma) / (a - gamma)


def evaluate_frost_risk(
    current_temp: float | None,
    current_humidity: float | None,
    wind_speed_kmh: float | None,
    cloud_cover_pct: float | None,
    forecast: list[tuple[datetime, float]],
) -> FrostRisk:
    """Évalue le risque de gel à partir des conditions actuelles et des
    prévisions (liste de tuples (datetime, température °C))."""

    dew_point = None
    if current_temp is not None and current_humidity is not None:
        dew_point = _dew_point(current_temp, current_humidity)

    min_temp: float | None = None
    next_frost_time: datetime | None = None
    for when, temp in forecast:
        if temp is None:
            continue
        if min_temp is None or temp < min_temp:
            min_temp = temp
        if temp <= 2 and next_frost_time is None:
            next_frost_time = when

    # Bonus de risque radiatif : ciel dégagé + vent faible accentuent le
    # refroidissement au sol au-delà de la température de l'air prévue.
    radiative_boost = 0.0
    if wind_speed_kmh is not None and wind_speed_kmh < 8:
        if cloud_cover_pct is not None and cloud_cover_pct < 30:
            radiative_boost = 2.0

    effective_min = min_temp + radiative_boost if min_temp is not None else None

    level = RISK_NONE
    if effective_min is not None:
        if effective_min <= -2:
            level = RISK_SEVERE
        elif effective_min <= 0:
            level = RISK_WARNING
        elif effective_min <= 3:
            level = RISK_WATCH

    return FrostRisk(
        level=level,
        min_forecast_temp=min_temp,
        next_frost_time=next_frost_time,
        dew_point=dew_point,
    )
