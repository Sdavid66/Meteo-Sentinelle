"""Socle horaire commun aux modèles de risque.

Les modèles agronomiques publiés (Smith, Hutton, Gubler-Thomas...) sont
définis sur des **séries horaires** : « au moins 6 heures continues
entre 21 et 30 °C », « 11 heures à HR ≥ 90 % ». Les états bruts du
recorder Home Assistant arrivent à intervalle irrégulier ; ce module
les rééchantillonne en pas horaires et fournit les primitives de
comptage utilisées par tous les modèles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Iterable


@dataclass
class HourlySample:
    """Une heure agrégée."""

    time: datetime
    temp: float | None = None
    humidity: float | None = None
    leaf_wet: bool | None = None
    rain_mm: float = 0.0


def resample_hourly(raw: Iterable[dict]) -> list[HourlySample]:
    """Agrège des relevés bruts en pas horaires.

    `raw` : itérable de dicts avec au minimum `time` (datetime), et
    optionnellement `temp`, `humidity`, `leaf_wet`, `rain_rate`
    (mm/h). Les températures et humidités sont moyennées sur l'heure,
    `leaf_wet` est vrai si la feuille a été mouillée à un moment de
    l'heure, la pluie est intégrée depuis l'intensité.
    """
    buckets: dict[datetime, list[dict]] = {}
    for item in raw:
        when = item.get("time")
        if not isinstance(when, datetime):
            continue
        slot = when.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(slot, []).append(item)

    samples: list[HourlySample] = []
    for slot in sorted(buckets):
        items = buckets[slot]

        def _mean(key: str) -> float | None:
            vals = [
                i[key]
                for i in items
                if isinstance(i.get(key), (int, float)) and not isinstance(i.get(key), bool)
            ]
            return sum(vals) / len(vals) if vals else None

        wet_flags = [bool(i["leaf_wet"]) for i in items if i.get("leaf_wet") is not None]
        rates = [
            i["rain_rate"]
            for i in items
            if isinstance(i.get("rain_rate"), (int, float))
            and not isinstance(i.get("rain_rate"), bool)
        ]

        samples.append(
            HourlySample(
                time=slot,
                temp=_mean("temp"),
                humidity=_mean("humidity"),
                leaf_wet=any(wet_flags) if wet_flags else None,
                # Intensité moyenne (mm/h) sur une heure ≈ cumul (mm).
                rain_mm=(sum(rates) / len(rates)) if rates else 0.0,
            )
        )
    return samples


def longest_run(samples: list[HourlySample], predicate: Callable[[HourlySample], bool]) -> int:
    """Plus longue série *consécutive* d'heures vérifiant `predicate`.

    Les modèles publiés parlent d'heures « continues » : une série
    interrompue ne compte pas. Une heure dont la donnée est manquante
    (predicate faux faute de mesure) casse donc la série, ce qui est le
    comportement prudent attendu.
    """
    best = 0
    current = 0
    for sample in samples:
        if predicate(sample):
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def count_hours(samples: list[HourlySample], predicate: Callable[[HourlySample], bool]) -> int:
    """Nombre total (non nécessairement consécutif) d'heures vérifiant `predicate`."""
    return sum(1 for s in samples if predicate(s))


def group_by_day(samples: list[HourlySample]) -> dict[date, list[HourlySample]]:
    """Regroupe par jour calendaire, chaque groupe trié chronologiquement."""
    days: dict[date, list[HourlySample]] = {}
    for sample in samples:
        days.setdefault(sample.time.date(), []).append(sample)
    for group in days.values():
        group.sort(key=lambda s: s.time)
    return days


def complete_days(
    samples: list[HourlySample], min_hours: int = 20
) -> list[tuple[date, list[HourlySample]]]:
    """Jours suffisamment couverts pour être évalués, du plus ancien au plus récent.

    Un jour partiel (début d'historique, journée en cours) donnerait un
    faux négatif sur un critère du type « 11 heures dans la journée » :
    on l'écarte.
    """
    return [
        (day, group)
        for day, group in sorted(group_by_day(samples).items())
        if len(group) >= min_hours
    ]


def is_wet(sample: HourlySample, humidity_threshold: float = 90.0) -> bool:
    """Feuille considérée comme humide sur cette heure.

    Un capteur d'humectation foliaire, quand il existe, fait foi. Sinon
    on retombe sur le proxy classique HR ≥ seuil, utilisé par Smith et
    Hutton.
    """
    if sample.leaf_wet is not None:
        return sample.leaf_wet
    return sample.humidity is not None and sample.humidity >= humidity_threshold


def beta_response(
    temp: float | None, t_min: float, t_opt: float, t_max: float
) -> float:
    """Réponse thermique continue normalisée dans [0, 1].

    Remplace les seuils binaires par une courbe de type Bêta (Analytis),
    nulle hors de l'intervalle [t_min, t_max] et maximale à t_opt. Deux
    heures à 11 °C et à 20 °C ne pèsent alors plus pareil, alors qu'un
    simple test « ≥ 10 °C » les traite à l'identique.
    """
    if temp is None or temp <= t_min or temp >= t_max:
        return 0.0
    # Exposants déduits de la position de l'optimum, de sorte que la
    # courbe atteigne exactement 1 en t_opt.
    left = (temp - t_min) / (t_opt - t_min)
    right = (t_max - temp) / (t_max - t_opt)
    shape = (t_max - t_opt) / (t_opt - t_min)
    return max(0.0, min(1.0, left * (right ** shape)))


@dataclass
class DayMetrics:
    """Indicateurs journaliers réutilisés par plusieurs modèles."""

    day: date
    temp_min: float | None = None
    temp_max: float | None = None
    wet_hours_continuous: int = 0
    wet_hours_total: int = 0
    rain_mm: float = 0.0
    thermal_pressure: float = 0.0
    hours: list[HourlySample] = field(default_factory=list)


def day_metrics(
    day: date,
    hours: list[HourlySample],
    humidity_threshold: float = 90.0,
    cardinal: tuple[float, float, float] = (3.0, 20.0, 30.0),
) -> DayMetrics:
    """Calcule les indicateurs d'une journée à partir de ses heures."""
    temps = [h.temp for h in hours if h.temp is not None]
    responses = [beta_response(h.temp, *cardinal) for h in hours if h.temp is not None]

    return DayMetrics(
        day=day,
        temp_min=min(temps) if temps else None,
        temp_max=max(temps) if temps else None,
        wet_hours_continuous=longest_run(hours, lambda s: is_wet(s, humidity_threshold)),
        wet_hours_total=count_hours(hours, lambda s: is_wet(s, humidity_threshold)),
        rain_mm=sum(h.rain_mm for h in hours),
        thermal_pressure=(sum(responses) / len(responses)) if responses else 0.0,
        hours=hours,
    )


def longest_true_run(flags: list[bool]) -> int:
    """Plus longue série consécutive de `True` dans une liste de booléens."""
    best = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        best = max(best, current)
    return best
