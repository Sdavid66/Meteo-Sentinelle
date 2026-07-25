"""Modèle de risque de gel, adossé aux seuils phénologiques.

Deux améliorations par rapport à un simple test sur la température
prévue :

1. **Seuils par culture et stade** — tables T10/T90 de Washington State
   University (voir `crops.py`). Le risque est évalué contre la
   sensibilité réelle de la plante au stade où elle se trouve.
2. **Température de surface estimée** — une gelée blanche au sol
   survient couramment alors que l'abri à 2 m affiche encore +2 à
   +4 °C. Sous ciel dégagé et vent faible, le rayonnement nocturne
   refroidit les surfaces de 3 à 5 °C sous la température de l'air.
   Les cultures basses sont donc évaluées sur cette température de
   surface, les arbres sur la température de l'air.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from ..const import RISK_NONE, RISK_SEVERE, RISK_WARNING, RISK_WATCH
from .crops import GENERIC_CROP, is_ground_level, thresholds

#: Écart maximal entre l'air à 2 m et la surface, sous ciel dégagé et
#: vent nul. Paramétrisation empirique (ordre de grandeur documenté :
#: 3 à 5 °C), et non un modèle de bilan énergétique validé.
MAX_RADIATIVE_OFFSET = 5.0

#: Au-delà de ce vent, le brassage annule pratiquement l'écart.
WIND_MIXING_KMH = 20.0


@dataclass
class FrostRisk:
    level: str
    #: Minimum de l'air prévu (°C).
    air_min: float | None = None
    #: Minimum estimé au niveau des surfaces / du gazon (°C).
    surface_min: float | None = None
    #: Température effectivement comparée aux seuils.
    reference_min: float | None = None
    #: Quelle référence a été utilisée ("air" ou "surface").
    reference: str = "air"
    next_frost_time: datetime | None = None
    dew_point: float | None = None
    radiative_offset: float = 0.0
    crop: str = GENERIC_CROP
    stage: str | None = None
    t10: float | None = None
    t90: float | None = None
    #: Interprétation lisible du croisement seuil / température.
    expected_damage: str = "none"


def dew_point(temp_c: float, humidity_pct: float) -> float:
    """Point de rosée (approximation de Magnus)."""
    a, b = 17.62, 243.12
    gamma = (a * temp_c) / (b + temp_c) + math.log(max(humidity_pct, 1.0) / 100.0)
    return (b * gamma) / (a - gamma)


def radiative_offset(
    cloud_cover_pct: float | None, wind_speed_kmh: float | None
) -> float:
    """Écart air → surface attendu cette nuit, en °C (positif).

    Maximal par ciel dégagé et vent nul, s'annule par ciel couvert ou
    vent soutenu. En l'absence de donnée, on retient une valeur
    intermédiaire prudente plutôt que zéro : ignorer le refroidissement
    radiatif ferait manquer des gelées blanches.
    """
    clear = 1.0 if cloud_cover_pct is None else max(0.0, 1.0 - cloud_cover_pct / 100.0)
    if wind_speed_kmh is None:
        calm = 0.5
    else:
        calm = max(0.0, 1.0 - wind_speed_kmh / WIND_MIXING_KMH)
    return MAX_RADIATIVE_OFFSET * clear * calm


def _generic_level(reference_min: float | None) -> tuple[str, str]:
    """Seuils fixes, pour l'utilisateur qui n'a pas choisi de culture."""
    if reference_min is None:
        return RISK_NONE, "unknown"
    if reference_min <= -2:
        return RISK_SEVERE, "hard_frost"
    if reference_min <= 0:
        return RISK_WARNING, "frost"
    if reference_min <= 3:
        return RISK_WATCH, "possible_frost"
    return RISK_NONE, "none"


def _phenological_level(
    reference_min: float | None, t10: float, t90: float | None
) -> tuple[str, str]:
    """Croise la température de référence avec les seuils T10 / T90.

    - au-dessous de T90 : perte massive attendue (≈90 % des bourgeons) ;
    - au-dessous de T10 : premiers dégâts significatifs (≈10 %) ;
    - dans les 2 °C au-dessus de T10 : marge d'incertitude, vigilance.
    """
    if reference_min is None:
        return RISK_NONE, "unknown"
    if t90 is not None and reference_min <= t90:
        return RISK_SEVERE, "severe_loss"
    if reference_min <= t10:
        # Sans T90 connue, un net dépassement de T10 reste grave.
        if t90 is None and reference_min <= t10 - 3:
            return RISK_SEVERE, "severe_loss"
        return RISK_WARNING, "partial_loss"
    if reference_min <= t10 + 2:
        return RISK_WATCH, "near_threshold"
    return RISK_NONE, "none"


def evaluate_frost_risk(
    current_temp: float | None,
    current_humidity: float | None,
    wind_speed_kmh: float | None,
    cloud_cover_pct: float | None,
    forecast: list[tuple[datetime, float]],
    crop: str = GENERIC_CROP,
    stage: str | None = None,
) -> FrostRisk:
    """Évalue le risque de gel.

    `forecast` : liste de (datetime, température de l'air en °C).
    """
    dew = None
    if current_temp is not None and current_humidity is not None:
        dew = dew_point(current_temp, current_humidity)

    air_min: float | None = None
    next_frost: datetime | None = None
    offset = radiative_offset(cloud_cover_pct, wind_speed_kmh)

    for when, temp in forecast:
        if temp is None:
            continue
        if air_min is None or temp < air_min:
            air_min = temp
        # Première échéance où la surface peut atteindre 0 °C.
        if next_frost is None and (temp - offset) <= 0:
            next_frost = when

    # À défaut de prévision, on se rabat sur la mesure courante : mieux
    # vaut un signal dégradé que pas de signal.
    if air_min is None and current_temp is not None:
        air_min = current_temp

    surface_min = air_min - offset if air_min is not None else None

    ground = is_ground_level(crop)
    reference_min = surface_min if ground else air_min
    reference = "surface" if ground else "air"

    limits = thresholds(crop, stage) if crop != GENERIC_CROP else None
    if limits is None:
        level, damage = _generic_level(reference_min)
        t10 = t90 = None
    else:
        t10, t90 = limits
        level, damage = _phenological_level(reference_min, t10, t90)

    return FrostRisk(
        level=level,
        air_min=air_min,
        surface_min=surface_min,
        reference_min=reference_min,
        reference=reference,
        next_frost_time=next_frost,
        dew_point=dew,
        radiative_offset=round(offset, 2),
        crop=crop,
        stage=stage,
        t10=t10,
        t90=t90,
        expected_damage=damage,
    )
