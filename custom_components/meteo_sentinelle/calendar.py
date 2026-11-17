"""Calendrier des traitements : ce qui a été fait, et ce qui reste à refaire.

Le calendrier se lit dans celui de Home Assistant, sans rien configurer.
Il porte deux sortes d'événements :

- un **traitement** par ligne du journal. Il couvre la période de
  protection, de l'application à sa fin : terme de la rémanence, lessivage
  ou traitement suivant ;
- un **renouvellement** par traitement en cours, posé sur le jour où la
  protection se termine. Il disparaît dès que le traitement est refait ou
  effacé : un renouvellement qui traîne est un traitement en retard.

Supprimer un traitement depuis le calendrier le retire du journal — c'est
la voie pour corriger une saisie ancienne. Supprimer un renouvellement
clôt le traitement en cours sans l'effacer du journal.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .alerting import dismiss_treatment_reminder
from .const import DOMAIN
from .entity import MeteoSentinelleSiteEntity
from .localize import Translator
from .models.treatments import JournalEntry, Treatment

#: Préfixe de l'identifiant d'un renouvellement, suivi de celui de sa ligne
#: du journal : c'est ce qui dit, à la suppression, lequel des deux est visé.
RENEWAL_PREFIX = "renew-"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TreatmentCalendar(coordinator, entry)])


def _number(value: float) -> str:
    """« 7 » plutôt que « 7.0 », « 0,5 » laissé tel quel."""
    return f"{value:g}"


def treatment_event(entry: JournalEntry, tr: Translator, active: bool) -> CalendarEvent:
    """Événement d'une application : la période qu'elle a protégée."""
    model = tr.treatment_target(entry.target)
    summary = tr.text(
        "calendar_treatment_product" if entry.product else "calendar_treatment",
        tree=entry.tree,
        model=model,
        product=entry.product,
    )

    lines = [
        tr.text(
            # Un lessivage à 0 mm veut dire « non pris en compte ».
            "calendar_residual" if entry.rainfast_mm > 0 else "calendar_residual_only",
            days=_number(entry.residual_days),
            mm=_number(entry.rainfast_mm),
        )
    ]
    if active:
        lines.append(tr.text("calendar_active"))
    elif entry.end_reason:
        lines.append(
            tr.text(
                f"calendar_end_{entry.end_reason}",
                rain=_number(round(entry.rain_mm or 0)),
            )
        )

    return CalendarEvent(
        start=entry.applied_at,
        # Un traitement clos à l'instant de son application garde une durée
        # nulle, que le calendrier accepte ; jamais une durée négative.
        end=max(entry.applied_at, entry.end),
        summary=summary,
        description="\n".join(lines),
        uid=entry.id,
    )


def renewal_event(
    entry: JournalEntry, treatment: Treatment, tr: Translator
) -> CalendarEvent:
    """Jour où le traitement en cours est à refaire."""
    day = dt_util.as_local(entry.end).date()
    return CalendarEvent(
        start=day,
        end=day + timedelta(days=1),
        summary=tr.text(
            "calendar_renewal",
            tree=entry.tree,
            model=tr.treatment_target(entry.target),
        ),
        description="\n".join(
            (
                tr.text(
                    "calendar_renewal_detail",
                    applied=dt_util.as_local(treatment.applied_at).strftime("%d/%m"),
                ),
                tr.text("notify_treatment_how"),
            )
        ),
        uid=f"{RENEWAL_PREFIX}{entry.id}",
    )


class TreatmentCalendar(MeteoSentinelleSiteEntity, CalendarEntity):
    """Journal des traitements du site, et renouvellements à venir."""

    _attr_icon = "mdi:spray-bottle"
    _attr_translation_key = "treatments"
    _attr_supported_features = CalendarEntityFeature.DELETE_EVENT

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_treatments"

    def _events(self) -> list[CalendarEvent]:
        """Tous les événements, dans l'ordre chronologique."""
        tr = Translator(self.hass)
        now = dt_util.utcnow()
        current = {
            treatment.journal_id: treatment
            for treatment in self.coordinator.treatments.values()
            if treatment.journal_id
        }
        events: list[CalendarEvent] = []
        for entry in self.coordinator.journal:
            treatment = current.get(entry.id)
            active = treatment is not None and treatment.is_active(now)
            events.append(treatment_event(entry, tr, active))
            if treatment is not None:
                events.append(renewal_event(entry, treatment, tr))
        events.sort(key=lambda event: event.start_datetime_local)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Événement en cours, ou à défaut le prochain."""
        now = dt_util.now()
        return next(
            (event for event in self._events() if event.end_datetime_local > now),
            None,
        )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            event
            for event in self._events()
            if event.start_datetime_local < end_date
            and event.end_datetime_local >= start_date
        ]

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        if uid.startswith(RENEWAL_PREFIX):
            key = await self.coordinator.async_end_treatment(uid[len(RENEWAL_PREFIX) :])
        else:
            key = await self.coordinator.async_delete_journal_entry(uid)
        if key is not None:
            # Le traitement n'est plus suivi : son rappel n'a plus d'objet.
            dismiss_treatment_reminder(self.hass, *key)
