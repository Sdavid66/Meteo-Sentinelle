"""Entités sensor : risques par arbre, protection, degrés-jours, diagnostic."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    MODEL_FROST,
    MODEL_LATE_BLIGHT,
    MODEL_POWDERY_MILDEW,
    RISK_LEVELS,
    SOURCE_NONE,
)
from .entity import MeteoSentinelleSiteEntity, MeteoSentinelleTreeEntity
from .models import phenology
from .models.crops import STAGE_LABELS, all_stage_keys
from .tree import Tree

RISK_ICONS = {
    MODEL_FROST: "mdi:snowflake-alert",
    MODEL_LATE_BLIGHT: "mdi:leaf-off",
    MODEL_POWDERY_MILDEW: "mdi:leaf-circle-outline",
}

#: Clés de traduction, pas des libellés : Home Assistant résout chacune
#: dans « entity.sensor.<clé> » de strings.json selon la langue choisie.
RISK_TRANSLATION_KEYS = {
    MODEL_FROST: "frost_risk",
    MODEL_LATE_BLIGHT: "late_blight_risk",
    MODEL_POWDERY_MILDEW: "powdery_mildew_risk",
}

PROTECTION_TRANSLATION_KEYS = {
    MODEL_LATE_BLIGHT: "late_blight_protection",
    MODEL_POWDERY_MILDEW: "powdery_mildew_protection",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Entités du site, rattachées à l'entrée principale.
    async_add_entities([DataSourceSensor(coordinator, entry), GddSensor(coordinator, entry)])

    # Entités par arbre, rattachées à leur sous-entrée respective : c'est
    # ce qui fait apparaître un appareil distinct par arbre.
    for subentry_id, tree in coordinator.trees.items():
        entities: list = [StageSensor(coordinator, entry, tree)]
        results = (coordinator.data or {}).get(subentry_id, {})

        for model_key in results:
            entities.append(RiskSensor(coordinator, entry, tree, model_key))

        if MODEL_POWDERY_MILDEW in results:
            entities.append(MildewIndexSensor(coordinator, entry, tree))

        for target in (MODEL_LATE_BLIGHT, MODEL_POWDERY_MILDEW):
            if target in results:
                entities.append(ProtectionSensor(coordinator, entry, tree, target))

        async_add_entities(entities, config_subentry_id=subentry_id)


class RiskSensor(MeteoSentinelleTreeEntity, SensorEntity):
    """Niveau de risque d'un modèle, pour un arbre donné."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = RISK_LEVELS

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree, model_key: str) -> None:
        super().__init__(coordinator, entry, tree)
        self._model_key = model_key
        self._attr_unique_id = f"{entry.entry_id}_{tree.subentry_id}_{model_key}"
        self._attr_translation_key = RISK_TRANSLATION_KEYS.get(model_key, model_key)
        self._attr_icon = RISK_ICONS.get(model_key, "mdi:sprout")

    @property
    def native_value(self) -> str | None:
        result = self.coordinator.result(self._subentry_id, self._model_key)
        return getattr(result, "level", None)

    @property
    def extra_state_attributes(self) -> dict:
        result = self.coordinator.result(self._subentry_id, self._model_key)
        attributes: dict = {}
        if result is not None:
            attributes = {
                key: value for key, value in vars(result).items() if key != "level"
            }
        tree = self.tree
        if tree is not None:
            attributes["tree"] = tree.display_name
            attributes["crop"] = tree.crop
            attributes["stage"] = tree.stage
            attributes["stage_label"] = tree.stage_label
        attributes["sources"] = dict(getattr(self.coordinator, "sources", {}))
        protection = self.coordinator.tree_protection(self._subentry_id, self._model_key)
        if protection:
            attributes["protection"] = protection
        return attributes


class StageSensor(MeteoSentinelleTreeEntity, SensorEntity):
    """Stade phénologique courant, en lecture, avec son contexte.

    Doublon apparent avec l'entité `select`, mais utile : un capteur
    s'historise proprement et se met dans un tableau de bord sans risque
    de modification accidentelle.
    """

    _attr_icon = "mdi:flower-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "phenology_stage"

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree) -> None:
        super().__init__(coordinator, entry, tree)
        self._attr_unique_id = f"{entry.entry_id}_{tree.subentry_id}_stage_sensor"
        # Un capteur d'énumération doit annoncer toutes les valeurs qu'il
        # peut prendre ; l'espèce d'un arbre est modifiable après coup, donc
        # on déclare l'ensemble des stades connus plutôt que ceux de
        # l'espèce du moment.
        self._attr_options = all_stage_keys()

    @property
    def native_value(self) -> str | None:
        """Clé du stade : Home Assistant l'affiche traduite."""
        tree = self.tree
        return tree.stage if tree else None

    @property
    def extra_state_attributes(self) -> dict:
        tree = self.tree
        if tree is None:
            return {}
        frost = self.coordinator.result(self._subentry_id, MODEL_FROST)
        gdd = self.coordinator.gdd
        following = phenology.next_stage_threshold(tree.crop, tree.stage)

        attributes: dict = {
            "tree": tree.display_name,
            "crop": tree.crop,
            "crop_label": tree.crop_label,
            "stage_key": tree.stage,
            "auto_advance": tree.auto_advance,
            "last_change_automatic": tree.stage_auto_applied,
            "changed_at": (
                tree.stage_changed_at.isoformat() if tree.stage_changed_at else None
            ),
            "gdd_total": round(gdd.total, 1),
            "gdd_offset": tree.gdd_offset,
        }
        if following is not None:
            next_stage, threshold = following
            attributes["next_stage"] = STAGE_LABELS.get(next_stage, next_stage)
            attributes["next_stage_gdd"] = threshold
            attributes["gdd_to_next_stage"] = round(
                max(0.0, threshold - (gdd.total + tree.gdd_offset)), 1
            )
        if frost is not None:
            attributes["t10"] = getattr(frost, "t10", None)
            attributes["t90"] = getattr(frost, "t90", None)
        if tree.bloom_date is not None:
            attributes["bloom_date"] = tree.bloom_date.isoformat()
            attributes["days_to_harvest"] = phenology.days_to_harvest(
                tree.crop, tree.bloom_date, dt_util.now().date()
            )
        return attributes


class MildewIndexSensor(MeteoSentinelleTreeEntity, SensorEntity):
    """Indice Gubler-Thomas (0-100), cumulatif sur la saison."""

    _attr_icon = "mdi:chart-line"
    _attr_native_unit_of_measurement = "points"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree) -> None:
        super().__init__(coordinator, entry, tree)
        self._attr_unique_id = f"{entry.entry_id}_{tree.subentry_id}_mildew_index"
        self._attr_translation_key = "powdery_mildew_index"

    @property
    def native_value(self) -> int | None:
        result = self.coordinator.result(self._subentry_id, MODEL_POWDERY_MILDEW)
        return getattr(result, "index", None)

    @property
    def extra_state_attributes(self) -> dict:
        result = self.coordinator.result(self._subentry_id, MODEL_POWDERY_MILDEW)
        if result is None:
            return {}
        return {
            "epidemic_started": result.epidemic_started,
            "spray_interval_days": result.spray_interval_days,
            "last_processed_day": result.last_processed_day,
            "last_day_optimal_hours": result.last_day_optimal_hours,
            "last_day_rain_mm": result.last_day_rain_mm,
            "last_day_delta": result.last_day_delta,
        }


class ProtectionSensor(MeteoSentinelleTreeEntity, SensorEntity):
    """Échéance de protection : « protégé jusqu'à… »."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:shield-sun"

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree, target: str) -> None:
        super().__init__(coordinator, entry, tree)
        self._target = target
        self._attr_unique_id = f"{entry.entry_id}_{tree.subentry_id}_protection_{target}"
        self._attr_translation_key = PROTECTION_TRANSLATION_KEYS.get(
            target, f"{target}_protection"
        )

    @property
    def native_value(self):
        state = self.coordinator.tree_protection(self._subentry_id, self._target)
        until = state.get("protected_until")
        return dt_util.parse_datetime(until) if until else None

    @property
    def extra_state_attributes(self) -> dict:
        return dict(self.coordinator.tree_protection(self._subentry_id, self._target))


class GddSensor(MeteoSentinelleSiteEntity, SensorEntity):
    """Cumul de degrés-jours du site depuis le 1er janvier."""

    _attr_icon = "mdi:thermometer-plus"
    _attr_native_unit_of_measurement = "°C·j"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_gdd"
        self._attr_translation_key = "growing_degree_days"

    @property
    def native_value(self) -> float:
        return round(self.coordinator.gdd.total, 1)

    @property
    def extra_state_attributes(self) -> dict:
        gdd = self.coordinator.gdd
        return {
            "season_year": gdd.season_year,
            "base_temperature": phenology.GDD_BASE_C,
            "last_day": gdd.last_day,
            "recent_days": gdd.recent,
        }


class DataSourceSensor(MeteoSentinelleSiteEntity, SensorEntity):
    """Indique quelle station alimente réellement les calculs."""

    _attr_icon = "mdi:database-marker"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ecowitt", "meteoswiss", "mixed", "unavailable"]

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_data_source"
        self._attr_translation_key = "data_source"

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
