"""Entité select : stade phénologique de la culture surveillée.

Le stade change au fil de la saison — imposer un passage par les
options de l'intégration à chaque évolution serait pénible. Une entité
`select` permet de le changer depuis le tableau de bord, ou de
l'automatiser (par cumul de degrés-jours, par date, ou à la main lors
de l'observation du verger).
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .models.crops import GENERIC_CROP, STAGE_LABELS, stage_options


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Sans culture choisie, il n'y a pas de stade à piloter.
    if coordinator.crop == GENERIC_CROP:
        return
    if not stage_options(coordinator.crop):
        return

    async_add_entities([PhenologyStageSelect(coordinator, entry)])


class PhenologyStageSelect(CoordinatorEntity, SelectEntity):
    """Stade phénologique courant, sélectionnable par l'utilisateur."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sprout-outline"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_stage"
        self._attr_name = "Stade phénologique"
        self._stages = stage_options(coordinator.crop)
        self._attr_options = [label for _, label in self._stages]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Sentinelle Ecowitt",
            model="Moteur de prédiction",
        )

    def _key_for(self, label: str) -> str | None:
        for key, lbl in self._stages:
            if lbl == label:
                return key
        return None

    @property
    def current_option(self) -> str | None:
        stage = self.coordinator.stage
        if stage is None:
            return None
        return STAGE_LABELS.get(stage, stage)

    async def async_select_option(self, option: str) -> None:
        key = self._key_for(option)
        if key is not None:
            await self.coordinator.async_set_stage(key)

    @property
    def extra_state_attributes(self) -> dict:
        frost = self.coordinator.data.get("frost")
        if frost is None:
            return {"crop": self.coordinator.crop}
        return {
            "crop": self.coordinator.crop,
            "stage_key": self.coordinator.stage,
            "t10": getattr(frost, "t10", None),
            "t90": getattr(frost, "t90", None),
        }
