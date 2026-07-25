"""Entités sensor : niveaux de risque, protection, diagnostic."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    MODEL_FROST,
    MODEL_LATE_BLIGHT,
    MODEL_POWDERY_MILDEW,
    RISK_LEVELS,
    SOURCE_NONE,
    TREATABLE_MODELS,
)

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

PROTECTION_NAMES = {
    MODEL_LATE_BLIGHT: "Protection mildiou",
    MODEL_POWDERY_MILDEW: "Protection oïdium",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SentinelleEntity] = [
        RiskSensor(coordinator, entry, model_key) for model_key in coordinator.data
    ]

    if MODEL_POWDERY_MILDEW in coordinator.data:
        entities.append(MildewIndexSensor(coordinator, entry))

    for target in TREATABLE_MODELS:
        if target in coordinator.data:
            entities.append(ProtectionSensor(coordinator, entry, target))

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


class RiskSensor(SentinelleEntity):
    """Niveau de risque d'un modèle de prédiction."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = RISK_LEVELS

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
        attributes: dict = {}
        if result is not None:
            attributes = {
                key: value for key, value in vars(result).items() if key != "level"
            }
        attributes["sources"] = dict(getattr(self.coordinator, "sources", {}))
        protection = getattr(self.coordinator, "protection", {}).get(self._model_key)
        if protection:
            attributes["protection"] = protection
        return attributes


class MildewIndexSensor(SentinelleEntity):
    """Indice Gubler-Thomas (0-100), cumulatif sur la saison."""

    _attr_icon = "mdi:chart-line"
    _attr_native_unit_of_measurement = "points"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_powdery_mildew_index"
        self._attr_name = "Indice oïdium (Gubler-Thomas)"

    @property
    def native_value(self) -> int | None:
        result = self.coordinator.data.get(MODEL_POWDERY_MILDEW)
        return getattr(result, "index", None)

    @property
    def extra_state_attributes(self) -> dict:
        result = self.coordinator.data.get(MODEL_POWDERY_MILDEW)
        if result is None:
            return {}
        return {
            "epidemic_started": result.epidemic_started,
            "spray_interval_days": result.spray_interval_days,
            "last_processed_day": result.last_processed_day,
            "last_day_optimal_hours": result.last_day_optimal_hours,
            "last_day_rain_mm": result.last_day_rain_mm,
            "last_day_delta": result.last_day_delta,
            "days": result.days,
        }


class ProtectionSensor(SentinelleEntity):
    """Échéance de protection : « protégé jusqu'à… »."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:shield-sun"

    def __init__(self, coordinator, entry: ConfigEntry, target: str) -> None:
        super().__init__(coordinator, entry)
        self._target = target
        self._attr_unique_id = f"{entry.entry_id}_protection_{target}"
        self._attr_name = PROTECTION_NAMES.get(target, f"Protection {target}")

    @property
    def native_value(self):
        """Date de fin de protection, ou None si non protégé / lessivé."""
        state = getattr(self.coordinator, "protection", {}).get(self._target, {})
        until = state.get("protected_until")
        if not until:
            return None
        return dt_util.parse_datetime(until)

    @property
    def extra_state_attributes(self) -> dict:
        return dict(getattr(self.coordinator, "protection", {}).get(self._target, {}))


class DataSourceSensor(SentinelleEntity):
    """Indique quelle station alimente réellement les calculs."""

    _attr_icon = "mdi:database-marker"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ecowitt", "meteoswiss", "mixed", "unavailable"]

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_data_source"
        self._attr_name = "Source des données"

    @property
    def native_value(self) -> str:
        sources = getattr(self.coordinator, "sources", {}) or {}
        used = set(sources.values()) - {SOURCE_NONE}
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
