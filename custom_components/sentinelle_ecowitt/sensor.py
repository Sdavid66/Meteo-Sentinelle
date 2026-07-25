"""Entités sensor exposant les niveaux de risque calculés."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODEL_FROST, MODEL_LATE_BLIGHT, MODEL_POWDERY_MILDEW

RISK_ICONS = {
    MODEL_FROST: "mdi:snowflake-alert",
    MODEL_LATE_BLIGHT: "mdi:leaf-off",
    MODEL_POWDERY_MILDEW: "mdi:leaf-circle-outline",
}

RISK_NAMES = {
    MODEL_FROST: "Risque de gel",
    MODEL_LATE_BLIGHT: "Risque de mildiou",
    MODEL_POWDERY_MILDEW: "Risque d'oïdium",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        PlantGuardRiskSensor(coordinator, entry, model_key)
        for model_key in coordinator.data.keys()
    ]
    async_add_entities(entities)


class PlantGuardRiskSensor(CoordinatorEntity, SensorEntity):
    """Représente le niveau de risque d'un modèle de prédiction."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, model_key: str) -> None:
        super().__init__(coordinator)
        self._model_key = model_key
        self._attr_unique_id = f"{entry.entry_id}_{model_key}"
        self._attr_name = RISK_NAMES.get(model_key, model_key)
        self._attr_icon = RISK_ICONS.get(model_key, "mdi:sprout")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Sentinelle Ecowitt",
            model="Moteur de prédiction",
        )

    @property
    def native_value(self) -> str | None:
        result = self.coordinator.data.get(self._model_key)
        return getattr(result, "level", None)

    @property
    def extra_state_attributes(self) -> dict:
        result = self.coordinator.data.get(self._model_key)
        if result is None:
            return {}
        return {k: v for k, v in vars(result).items() if k != "level"}
