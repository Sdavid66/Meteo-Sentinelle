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

    entities: list[SentinelleEntity] = [
        PlantGuardRiskSensor(coordinator, entry, model_key)
        for model_key in coordinator.data
    ]
    entities.append(DataSourceSensor(coordinator, entry))
    async_add_entities(entities)


class SentinelleEntity(CoordinatorEntity, SensorEntity):
    """Base commune : rattache toutes les entités au même appareil."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Sentinelle Ecowitt",
            model="Moteur de prédiction",
        )


class PlantGuardRiskSensor(SentinelleEntity):
    """Représente le niveau de risque d'un modèle de prédiction."""

    def __init__(self, coordinator, entry: ConfigEntry, model_key: str) -> None:
        super().__init__(coordinator, entry)
        self._model_key = model_key
        self._attr_unique_id = f"{entry.entry_id}_{model_key}"
        self._attr_name = RISK_NAMES.get(model_key, model_key)
        self._attr_icon = RISK_ICONS.get(model_key, "mdi:sprout")

    @property
    def native_value(self) -> str | None:
        result = self.coordinator.data.get(self._model_key)
        return getattr(result, "level", None)

    @property
    def extra_state_attributes(self) -> dict:
        result = self.coordinator.data.get(self._model_key)
        attributes = {} if result is None else {
            k: v for k, v in vars(result).items() if k != "level"
        }
        # Origine réelle des mesures ayant servi au calcul (ecowitt /
        # meteoswiss / unavailable), utile pour diagnostiquer une panne
        # de capteur.
        attributes["sources"] = dict(getattr(self.coordinator, "sources", {}))
        return attributes


class DataSourceSensor(SentinelleEntity):
    """Indique quelle station alimente réellement les calculs."""

    _attr_icon = "mdi:database-marker"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_data_source"
        self._attr_name = "Source des données"

    @property
    def native_value(self) -> str:
        sources = getattr(self.coordinator, "sources", {}) or {}
        used = set(sources.values()) - {"unavailable"}
        if not used:
            return "unavailable"
        if used == {"ecowitt"}:
            return "ecowitt"
        if used == {"meteoswiss"}:
            return "meteoswiss"
        return "mixed"

    @property
    def extra_state_attributes(self) -> dict:
        return dict(getattr(self.coordinator, "sources", {}))
