"""Modèle de risque de mildiou — "Smith Period" simplifiée.

Le mildiou (Phytophthora infestans, pomme de terre / tomate) se
développe lorsque deux journées consécutives réunissent :
  - au moins 11h avec humidité relative >= 90 % (ou feuillage mouillé
    détecté par un capteur d'humectation foliaire) ;
  - une température minimale >= 10 °C.
Ce modèle est une simplification à but indicatif, pas un outil
phytosanitaire certifié.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..const import RISK_NONE, RISK_SEVERE, RISK_WATCH


@dataclass
class LateBlightRisk:
    level: str
    consecutive_favorable_days: int
    last_period_min_temp: float | None


def evaluate_late_blight_risk(hourly_samples: list[dict]) -> LateBlightRisk:
    """hourly_samples: échantillons triés par temps, avec les clés
    'time' (datetime), 'temp' (°C), 'humidity' (%, optionnel),
    'leaf_wet' (bool, optionnel). Couvre idéalement les ~72 dernières heures.
    """
    days: dict[str, list[dict]] = defaultdict(list)
    for sample in hourly_samples:
        day_key = sample["time"].date().isoformat()
        days[day_key].append(sample)

    favorable_flags: list[bool] = []
    day_min_temps: list[float | None] = []

    for day_key in sorted(days):
        samples = days[day_key]
        wet_hours = sum(
            1
            for s in samples
            if s.get("leaf_wet")
            or (s.get("humidity") is not None and s["humidity"] >= 90)
        )
        temps = [s["temp"] for s in samples if s.get("temp") is not None]
        min_temp = min(temps) if temps else None
        day_min_temps.append(min_temp)
        favorable = wet_hours >= 11 and min_temp is not None and min_temp >= 10
        favorable_flags.append(favorable)

    consecutive = 0
    max_consecutive = 0
    for flag in favorable_flags:
        consecutive = consecutive + 1 if flag else 0
        max_consecutive = max(max_consecutive, consecutive)

    level = RISK_NONE
    if max_consecutive >= 2:
        level = RISK_SEVERE
    elif max_consecutive == 1:
        level = RISK_WATCH

    return LateBlightRisk(
        level=level,
        consecutive_favorable_days=max_consecutive,
        last_period_min_temp=day_min_temps[-1] if day_min_temps else None,
    )
