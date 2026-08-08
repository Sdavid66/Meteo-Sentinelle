"""Fenêtres de pulvérisation.

Un modèle de risque dit « le mildiou menace ». Un outil de décision dit
« traitez jeudi entre 6 h et 10 h ». Ce module fournit la seconde
moitié : il cherche, dans les prévisions horaires, les créneaux où
pulvériser a un sens.

Trois conditions, dans l'ordre d'importance :

1. **Vent** — c'est la seule contrainte qui soit *réglementaire* et non
   agronomique. En France, l'arrêté du 4 mai 2017 interdit l'application
   de produits phytopharmaceutiques lorsque le vent dépasse le degré 3
   de l'échelle de Beaufort, soit environ 19 km/h. La valeur retenue par
   défaut est donc ce seuil. Les autres pays ont leurs propres règles :
   la vérification reste de la responsabilité de l'utilisateur.
2. **Pluie** — une averse survenant avant que le produit ne soit sec
   lessive l'application. Le délai de résistance au lavage dépend du
   produit et figure sur son étiquette ; il est donc un paramètre, pas
   une constante.
3. **Température** — hors d'une plage raisonnable, l'efficacité chute :
   trop froid, la plante et le pathogène sont peu actifs ; trop chaud,
   la dérive et l'évaporation dominent, et certains produits deviennent
   phytotoxiques. Ces bornes sont des ordres de grandeur horticoles
   usuels, pas une norme.

Ce module ne connaît ni les produits ni les cultures : il répond
uniquement à « le temps permet-il d'intervenir ». Le choix du produit et
la légalité de son emploi restent à l'utilisateur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

#: Vent maximal admis (km/h) — degré 3 Beaufort, seuil réglementaire
#: français pour l'application de produits phytopharmaceutiques.
MAX_WIND_KMH = 19.0

#: Plage de température utile (°C). Ordres de grandeur horticoles.
MIN_TEMP_C = 5.0
MAX_TEMP_C = 25.0

#: Délai par défaut, en heures, pendant lequel il ne doit pas pleuvoir
#: après l'application. Beaucoup d'étiquettes annoncent 1 à 2 heures.
DEFAULT_RAINFAST_HOURS = 2

#: Pluie horaire (mm) au-delà de laquelle l'heure est considérée pluvieuse.
RAIN_THRESHOLD_MM = 0.2

#: Durée minimale d'un créneau pour être proposé (heures). Un créneau
#: d'une heure isolée n'est pas exploitable en pratique.
MIN_WINDOW_HOURS = 2


@dataclass
class ForecastHour:
    """Une heure de prévision, réduite à ce dont le modèle a besoin."""

    time: datetime
    temperature: float | None = None
    wind_speed: float | None = None
    precipitation: float | None = None


@dataclass
class SprayWindow:
    """Un créneau continu où les conditions sont réunies."""

    start: datetime
    end: datetime

    @property
    def hours(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() // 3600))

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "hours": self.hours,
        }


@dataclass
class SprayAdvice:
    """Ce que le modèle a trouvé dans l'horizon de prévision."""

    #: Créneau en cours, si l'heure présente est déjà favorable.
    current: SprayWindow | None = None
    #: Prochain créneau à venir.
    upcoming: SprayWindow | None = None
    windows: list[SprayWindow] = field(default_factory=list)
    #: Raisons du blocage à l'heure la plus proche, pour l'expliquer.
    blocking: list[str] = field(default_factory=list)
    horizon_hours: int = 0
    max_wind_kmh: float = MAX_WIND_KMH
    rainfast_hours: int = DEFAULT_RAINFAST_HOURS

    def as_dict(self) -> dict:
        return {
            "current": self.current.as_dict() if self.current else None,
            "upcoming": self.upcoming.as_dict() if self.upcoming else None,
            "windows": [w.as_dict() for w in self.windows],
            "blocking": list(self.blocking),
            "horizon_hours": self.horizon_hours,
            "max_wind_kmh": self.max_wind_kmh,
            "rainfast_hours": self.rainfast_hours,
        }


def _rain_soon(
    hours: list[ForecastHour], index: int, rainfast_hours: int
) -> bool:
    """Pleut-il dans les heures qui suivent le créneau envisagé ?

    Une donnée de pluie absente n'est pas traitée comme « il ne pleut
    pas » : faute de prévision, le créneau est refusé. Mieux vaut ne rien
    proposer que proposer un traitement lessivé une heure plus tard.
    """
    window = hours[index : index + max(1, rainfast_hours) + 1]
    if not window:
        return True
    for hour in window:
        if hour.precipitation is None:
            return True
        if hour.precipitation >= RAIN_THRESHOLD_MM:
            return True
    return False


def _blocking_reasons(
    hour: ForecastHour, hours: list[ForecastHour], index: int, rainfast_hours: int,
    max_wind: float,
) -> list[str]:
    """Ce qui empêche de traiter à cette heure, en clés techniques."""
    reasons: list[str] = []
    if hour.wind_speed is None:
        reasons.append("wind_unknown")
    elif hour.wind_speed > max_wind:
        reasons.append("wind")
    if hour.temperature is None:
        reasons.append("temperature_unknown")
    elif not (MIN_TEMP_C <= hour.temperature <= MAX_TEMP_C):
        reasons.append("temperature")
    if _rain_soon(hours, index, rainfast_hours):
        reasons.append("rain")
    return reasons


def find_spray_windows(
    forecast: list[ForecastHour],
    *,
    now: datetime | None = None,
    rainfast_hours: int = DEFAULT_RAINFAST_HOURS,
    max_wind_kmh: float = MAX_WIND_KMH,
    min_window_hours: int = MIN_WINDOW_HOURS,
) -> SprayAdvice:
    """Cherche les créneaux favorables dans une prévision horaire triée."""
    hours = sorted(
        (h for h in forecast if h.time is not None), key=lambda h: h.time
    )
    advice = SprayAdvice(
        horizon_hours=len(hours),
        max_wind_kmh=max_wind_kmh,
        rainfast_hours=rainfast_hours,
    )
    if not hours:
        advice.blocking = ["no_forecast"]
        return advice

    reference = now or hours[0].time

    suitable = [
        not _blocking_reasons(hour, hours, index, rainfast_hours, max_wind_kmh)
        for index, hour in enumerate(hours)
    ]

    # Regroupe les heures favorables consécutives en créneaux.
    windows: list[SprayWindow] = []
    start_index: int | None = None
    for index, ok in enumerate(suitable):
        if ok and start_index is None:
            start_index = index
        elif not ok and start_index is not None:
            windows.append(
                SprayWindow(hours[start_index].time, hours[index - 1].time + timedelta(hours=1))
            )
            start_index = None
    if start_index is not None:
        windows.append(
            SprayWindow(hours[start_index].time, hours[-1].time + timedelta(hours=1))
        )

    advice.windows = [w for w in windows if w.hours >= min_window_hours]

    for window in advice.windows:
        if window.start <= reference < window.end:
            advice.current = window
        elif window.start > reference and advice.upcoming is None:
            advice.upcoming = window

    if advice.current is None:
        # Expliquer le refus est aussi utile que le refus lui-même.
        index = next(
            (i for i, hour in enumerate(hours) if hour.time >= reference), 0
        )
        advice.blocking = _blocking_reasons(
            hours[index], hours, index, rainfast_hours, max_wind_kmh
        )

    return advice
