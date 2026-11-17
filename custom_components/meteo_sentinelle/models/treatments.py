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

Déclarer un traitement programme aussi son **rappel** : savoir qu'on est
protégé ne sert que si l'on apprend aussi quand on ne l'est plus. Deux
moments sont signalés, une seule fois chacun : la veille de l'échéance,
pour laisser le temps de trouver une fenêtre de traitement, et la fin de
la protection — à l'échéance, ou plus tôt si la pluie l'a lessivée.

Chaque application est aussi consignée dans un **journal**. Le traitement
en cours dit où en est la protection ; le journal garde ce qui a été fait,
y compris une fois le traitement remplacé, terminé ou l'arbre supprimé.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from uuid import uuid4

#: Valeurs par défaut prudentes, à ajuster selon l'étiquette du produit.
DEFAULT_RESIDUAL_DAYS = 7.0
DEFAULT_RAINFAST_MM = 20.0

#: Motifs d'un rappel. Les deux derniers reprennent les états de `status`.
REASON_EXPIRING = "expiring_soon"
REASON_EXPIRED = "expired"
REASON_WASHED_OFF = "washed_off"
REMINDER_REASONS = [REASON_EXPIRING, REASON_EXPIRED, REASON_WASHED_OFF]

#: Préavis avant la fin de la protection.
REMINDER_LEAD_HOURS = 24.0
#: En deçà de cette rémanence, le préavis suivrait de trop près l'application.
MIN_RESIDUAL_DAYS_FOR_NOTICE = 3.0

#: Ce qui a mis fin à un traitement du journal. Les deux premiers reprennent
#: les états de `status`.
END_EXPIRED = "expired"
END_WASHED_OFF = "washed_off"
END_REPLACED = "replaced"
END_CLEARED = "cleared"
END_SEASON = "season_end"

#: Délai pendant lequel effacer ou redéclarer un traitement encore actif
#: corrige la saisie, au lieu d'ajouter une ligne au journal.
CORRECTION_WINDOW_HOURS = 24.0
#: Le journal garde trois saisons : de quoi comparer d'une année à l'autre.
JOURNAL_KEEP_DAYS = 3 * 365
JOURNAL_MAX_ENTRIES = 500


@dataclass
class Treatment:
    """Une application enregistrée pour une cible donnée."""

    target: str
    product: str
    applied_at: datetime
    residual_days: float = DEFAULT_RESIDUAL_DAYS
    rainfast_mm: float = DEFAULT_RAINFAST_MM
    rain_since_mm: float = 0.0
    #: Rappels déjà émis. Persistés : un redémarrage ne doit pas les rejouer.
    notice_sent: bool = False
    end_sent: bool = False
    #: Ligne du journal qui consigne cette application.
    journal_id: str | None = None

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
            notice_sent=bool(data.get("notice_sent", False)),
            end_sent=bool(data.get("end_sent", False)),
            journal_id=data.get("journal_id"),
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

    def natural_end(self, now: datetime) -> tuple[datetime, str] | None:
        """(moment, motif) de la fin de protection, ou None si elle tient.

        Le lessivage est daté du moment où on le constate : le cumul de pluie
        n'est relevé qu'à chaque cycle, pas à la minute.
        """
        if self.washed_off:
            return now, END_WASHED_OFF
        if self.remaining_hours(now) <= 0:
            return self.expires_at, END_EXPIRED
        return None

    def add_rain(self, millimetres: float) -> None:
        """Cumule la pluie tombée depuis l'application.

        Le cumul est incrémenté à chaque cycle du coordinator plutôt que
        recalculé sur tout l'historique : c'est robuste et ça évite une
        requête recorder longue toutes les 15 minutes.
        """
        if millimetres > 0:
            self.rain_since_mm += millimetres


@dataclass
class JournalEntry:
    """Une application, telle qu'elle reste consignée.

    L'arbre y figure par son nom : la ligne doit rester lisible une fois
    l'arbre renommé ou supprimé.
    """

    id: str
    subentry_id: str
    tree: str
    crop: str
    target: str
    product: str
    applied_at: datetime
    residual_days: float
    rainfast_mm: float
    logged_at: datetime
    ended_at: datetime | None = None
    end_reason: str | None = None
    #: Pluie reçue entre l'application et la fin, si elle est connue.
    rain_mm: float | None = None

    @classmethod
    def record(
        cls,
        subentry_id: str,
        tree: str,
        crop: str,
        treatment: Treatment,
        logged_at: datetime,
    ) -> "JournalEntry":
        """Ouvre la ligne d'un traitement et les relie l'un à l'autre."""
        entry = cls(
            id=uuid4().hex,
            subentry_id=subentry_id,
            tree=tree,
            crop=crop,
            target=treatment.target,
            product=treatment.product,
            applied_at=treatment.applied_at,
            residual_days=treatment.residual_days,
            rainfast_mm=treatment.rainfast_mm,
            logged_at=logged_at,
        )
        treatment.journal_id = entry.id
        return entry

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("applied_at", "logged_at", "ended_at"):
            data[key] = data[key].isoformat() if data[key] else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "JournalEntry | None":
        try:
            applied_at = datetime.fromisoformat(data["applied_at"])
            logged_at = datetime.fromisoformat(data.get("logged_at") or data["applied_at"])
            ended_at = (
                datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None
            )
            return cls(
                id=str(data["id"]),
                subentry_id=str(data.get("subentry_id", "")),
                tree=str(data.get("tree", "")),
                crop=str(data.get("crop", "")),
                target=str(data["target"]),
                product=str(data.get("product", "")),
                applied_at=applied_at,
                residual_days=float(data.get("residual_days", DEFAULT_RESIDUAL_DAYS)),
                rainfast_mm=float(data.get("rainfast_mm", DEFAULT_RAINFAST_MM)),
                logged_at=logged_at,
                ended_at=ended_at,
                end_reason=data.get("end_reason"),
                rain_mm=data.get("rain_mm"),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def planned_end(self) -> datetime:
        """Fin de protection prévue à l'application."""
        return self.applied_at + timedelta(days=self.residual_days)

    @property
    def end(self) -> datetime:
        """Fin réelle si elle est connue, sinon celle qui était prévue."""
        return self.ended_at or self.planned_end

    def close(
        self, when: datetime, reason: str, rain_mm: float | None = None
    ) -> None:
        """Consigne la fin de la protection, une seule fois.

        Un traitement ne finit ni avant d'avoir commencé, ni après le terme
        de sa rémanence : effacer un traitement déjà expiré ne repousse pas
        sa fin à aujourd'hui.
        """
        if self.ended_at is not None:
            return
        self.ended_at = max(self.applied_at, min(when, self.planned_end))
        self.end_reason = reason
        if rain_mm is not None:
            self.rain_mm = round(rain_mm, 1)

    def is_correction(self, now: datetime) -> bool:
        """La ligne vient-elle d'être saisie ? Elle se corrige encore."""
        return (
            self.ended_at is None
            and now - self.logged_at < timedelta(hours=CORRECTION_WINDOW_HOURS)
        )

    def summary(self) -> dict:
        """Ce qu'il faut pour afficher la ligne dans la carte."""
        return {
            "applied_at": self.applied_at.isoformat(),
            "product": self.product,
            "residual_days": self.residual_days,
            "ended_at": self.end.isoformat(),
            "end_reason": self.end_reason,
        }


def prune_journal(journal: list[JournalEntry], now: datetime) -> list[JournalEntry]:
    """Journal trié par date d'application, sans ses lignes trop anciennes."""
    cutoff = now - timedelta(days=JOURNAL_KEEP_DAYS)
    kept = sorted(
        (entry for entry in journal if entry.applied_at >= cutoff),
        key=lambda entry: entry.applied_at,
    )
    return kept[-JOURNAL_MAX_ENTRIES:]


def journal_history(
    journal: list[JournalEntry],
    subentry_id: str,
    target: str,
    exclude: str | None = None,
    limit: int = 3,
) -> list[dict]:
    """Applications précédentes d'un arbre contre une cible, la plus récente d'abord."""
    entries = [
        entry
        for entry in journal
        if entry.subentry_id == subentry_id
        and entry.target == target
        and entry.id != exclude
    ]
    entries.sort(key=lambda entry: entry.applied_at, reverse=True)
    return [entry.summary() for entry in entries[:limit]]


def applied_moment(day: date | None, now: datetime) -> datetime:
    """Moment retenu pour une application déclarée à une date.

    `now` est l'heure locale. Sans date, ou pour aujourd'hui, c'est
    maintenant. Pour un jour passé, l'heure n'est pas connue : midi coupe la
    poire en deux, l'erreur ne dépasse pas une demi-journée.
    """
    if day is None or day >= now.date():
        return now
    return datetime.combine(day, time(12, 0), tzinfo=now.tzinfo)


def rain_since(samples: list, since: datetime) -> float:
    """Pluie tombée depuis `since`, d'après les relevés horaires disponibles.

    Sert aux traitements déclarés après coup : le cumul tenu à chaque cycle
    ne commence qu'à la déclaration. L'heure de l'application elle-même n'est
    pas comptée, un produit pulvérisé sous la pluie ne se déclare pas.
    """
    return sum(
        sample.rain_mm
        for sample in samples
        if sample.time >= since and sample.rain_mm > 0
    )


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
            "residual_days": None,
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
        "residual_days": treatment.residual_days,
    }


def pending_reminder(treatment: Treatment, now: datetime) -> str | None:
    """Rappel à émettre maintenant pour ce traitement, ou None."""
    status = treatment.status(now)
    if status != "protected":
        return None if treatment.end_sent else status
    if treatment.notice_sent or treatment.residual_days < MIN_RESIDUAL_DAYS_FOR_NOTICE:
        return None
    if treatment.remaining_hours(now) <= REMINDER_LEAD_HOURS:
        return REASON_EXPIRING
    return None


def mark_reminded(treatment: Treatment, reason: str) -> None:
    """Mémorise l'émission d'un rappel.

    La fin de protection rend le préavis sans objet : il est marqué lui
    aussi, pour qu'un traitement lessivé tôt ne déclenche pas les deux.
    """
    treatment.notice_sent = True
    if reason != REASON_EXPIRING:
        treatment.end_sent = True


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
