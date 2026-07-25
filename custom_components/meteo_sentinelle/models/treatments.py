"""Suivi des traitements : « vous êtes protégé jusqu'à… ».

Un modèle de risque dit « le risque est élevé ». Un outil d'aide à la
décision dit « traitez avant jeudi » ou « votre protection tient
encore 4 jours ». C'est cette dernière information qui est utile, et
elle exige de suivre trois choses :

- la **rémanence** du produit : durée de protection nominale ;
- le **lessivage** par la pluie : au-delà d'un cumul donné depuis
  l'application, la protection est considérée comme perdue, même si la
  rémanence n'est pas écoulée ;
- la **dilution par la croissance** : les nouvelles pousses ne sont pas
  couvertes. Non modélisée ici, mais c'est la limite à garder en tête.

Ce module est volontairement agnostique : aucune base de produits
phytosanitaires n'est embarquée. L'utilisateur déclare la rémanence et
la résistance au lavage correspondant à ce qu'il a appliqué, en se
fiant à l'étiquette du produit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

#: Valeurs par défaut prudentes, à ajuster selon l'étiquette du produit.
DEFAULT_RESIDUAL_DAYS = 7.0
DEFAULT_RAINFAST_MM = 20.0


@dataclass
class Treatment:
    """Une application enregistrée pour une cible donnée."""

    target: str
    product: str
    applied_at: datetime
    residual_days: float = DEFAULT_RESIDUAL_DAYS
    rainfast_mm: float = DEFAULT_RAINFAST_MM
    rain_since_mm: float = 0.0

    # --- Sérialisation pour le Store Home Assistant ---

    def to_dict(self) -> dict:
        data = asdict(self)
        data["applied_at"] = self.applied_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Treatment | None":
        try:
            applied_at = datetime.fromisoformat(data["applied_at"])
        except (KeyError, TypeError, ValueError):
            return None
        return cls(
            target=data.get("target", "unknown"),
            product=data.get("product", ""),
            applied_at=applied_at,
            residual_days=float(data.get("residual_days", DEFAULT_RESIDUAL_DAYS)),
            rainfast_mm=float(data.get("rainfast_mm", DEFAULT_RAINFAST_MM)),
            rain_since_mm=float(data.get("rain_since_mm", 0.0)),
        )

    # --- Logique de protection ---

    @property
    def expires_at(self) -> datetime:
        """Fin de protection par simple écoulement de la rémanence."""
        return self.applied_at + timedelta(days=self.residual_days)

    @property
    def washed_off(self) -> bool:
        """Protection perdue par lessivage."""
        return self.rainfast_mm > 0 and self.rain_since_mm >= self.rainfast_mm

    def remaining_hours(self, now: datetime) -> float:
        """Heures de protection restantes (0 si expirée ou lessivée)."""
        if self.washed_off:
            return 0.0
        remaining = (self.expires_at - now).total_seconds() / 3600.0
        return max(0.0, remaining)

    def is_active(self, now: datetime) -> bool:
        return self.remaining_hours(now) > 0

    def status(self, now: datetime) -> str:
        if self.washed_off:
            return "washed_off"
        if self.remaining_hours(now) <= 0:
            return "expired"
        return "protected"

    def add_rain(self, millimetres: float) -> None:
        """Cumule la pluie tombée depuis l'application.

        Le cumul est incrémenté à chaque cycle du coordinator plutôt que
        recalculé sur tout l'historique : c'est robuste et ça évite une
        requête recorder longue toutes les 15 minutes.
        """
        if millimetres > 0:
            self.rain_since_mm += millimetres


def protection_state(
    treatment: Treatment | None, now: datetime
) -> dict:
    """État de protection exploitable par une entité Home Assistant."""
    if treatment is None:
        return {
            "status": "none",
            "product": None,
            "applied_at": None,
            "protected_until": None,
            "hours_remaining": 0.0,
            "days_remaining": 0.0,
            "rain_since_mm": 0.0,
            "rainfast_mm": None,
        }

    remaining = treatment.remaining_hours(now)
    return {
        "status": treatment.status(now),
        "product": treatment.product,
        "applied_at": treatment.applied_at.isoformat(),
        "protected_until": (
            treatment.expires_at.isoformat() if not treatment.washed_off else None
        ),
        "hours_remaining": round(remaining, 1),
        "days_remaining": round(remaining / 24.0, 2),
        "rain_since_mm": round(treatment.rain_since_mm, 1),
        "rainfast_mm": treatment.rainfast_mm,
    }


def adjusted_level(risk_level: str, treatment: Treatment | None, now: datetime) -> str:
    """Niveau de risque tenant compte d'une protection en cours.

    Un risque météo élevé sur une culture protégée n'appelle pas la même
    réaction qu'un risque élevé sur une culture nue : on rétrograde d'un
    cran, sans jamais descendre sous « à surveiller » afin de ne pas
    masquer complètement la pression.
    """
    from ..const import RISK_NONE, RISK_SEVERE, RISK_WARNING, RISK_WATCH

    if treatment is None or not treatment.is_active(now):
        return risk_level

    downgrade = {
        RISK_SEVERE: RISK_WARNING,
        RISK_WARNING: RISK_WATCH,
        RISK_WATCH: RISK_WATCH,
        RISK_NONE: RISK_NONE,
    }
    return downgrade.get(risk_level, risk_level)
