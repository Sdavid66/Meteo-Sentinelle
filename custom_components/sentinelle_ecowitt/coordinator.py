"""DataUpdateCoordinator : lit les entités source + prévisions météo et
exécute les modèles de risque activés."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.recorder import get_instance, history
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_ENABLED_MODELS,
    CONF_HUMIDITY_ENTITY,
    CONF_LEAF_WETNESS_ENTITY,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_WIND_ENTITY,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    MODEL_FROST,
    MODEL_LATE_BLIGHT,
    MODEL_POWDERY_MILDEW,
)
from .models.frost import evaluate_frost_risk
from .models.late_blight import evaluate_late_blight_risk
from .models.powdery_mildew import evaluate_powdery_mildew_risk

_LOGGER = logging.getLogger(__name__)


class EcowittPlantGuardCoordinator(DataUpdateCoordinator[dict]):
    """Récupère les données et calcule les risques à intervalle régulier."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name="Sentinelle Ecowitt",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES),
        )

    def _state_float(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    async def _async_get_forecast(
        self, weather_entity: str | None
    ) -> list[tuple[datetime, float]]:
        """Récupère les prévisions horaires via le service weather.get_forecasts
        (API moderne HA, remplace l'ancien attribut 'forecast')."""
        if not weather_entity:
            return []
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001 - la prévision est optionnelle
            _LOGGER.debug("Prévisions indisponibles pour %s : %s", weather_entity, err)
            return []

        forecasts = (response or {}).get(weather_entity, {}).get("forecast", [])
        result: list[tuple[datetime, float]] = []
        for item in forecasts:
            when = item.get("datetime")
            temp = item.get("temperature")
            if when is None or temp is None:
                continue
            try:
                when_dt = datetime.fromisoformat(when)
            except ValueError:
                continue
            result.append((when_dt, temp))
        return result

    async def _async_get_history_samples(
        self, entry_data: dict, hours: int = 72
    ) -> list[dict]:
        """Historique récent (recorder) pour nourrir les modèles maladie."""
        temp_entity = entry_data.get(CONF_TEMP_ENTITY)
        humidity_entity = entry_data.get(CONF_HUMIDITY_ENTITY)
        leaf_entity = entry_data.get(CONF_LEAF_WETNESS_ENTITY)

        entity_ids = [e for e in (temp_entity, humidity_entity, leaf_entity) if e]
        if not entity_ids:
            return []

        start = datetime.utcnow() - timedelta(hours=hours)

        def _fetch() -> dict[str, list[State]]:
            return history.state_changes_during_period(
                self.hass, start, None, entity_ids, no_attributes=True
            )

        try:
            raw = await get_instance(self.hass).async_add_executor_job(_fetch)
        except Exception as err:  # noqa: BLE001 - l'historique est optionnel
            _LOGGER.debug("Historique indisponible : %s", err)
            return []

        samples: list[dict] = []
        temp_states = raw.get(temp_entity, []) if temp_entity else []
        for state in temp_states:
            try:
                temp_val = float(state.state)
            except ValueError:
                continue
            samples.append({"time": state.last_changed, "temp": temp_val})

        def _closest_value(states: list[State], when: datetime):
            candidates = [s for s in states if s.last_changed <= when]
            if not candidates:
                return None
            latest = candidates[-1]
            try:
                return float(latest.state)
            except ValueError:
                return latest.state == "on"

        humidity_states = raw.get(humidity_entity, []) if humidity_entity else []
        leaf_states = raw.get(leaf_entity, []) if leaf_entity else []
        for sample in samples:
            sample["humidity"] = _closest_value(humidity_states, sample["time"])
            if leaf_entity:
                sample["leaf_wet"] = bool(_closest_value(leaf_states, sample["time"]))

        return samples

    async def _async_update_data(self) -> dict:
        entry_data = {**self.entry.data, **self.entry.options}
        enabled_models = entry_data.get(CONF_ENABLED_MODELS, [MODEL_FROST])

        current_temp = self._state_float(entry_data.get(CONF_TEMP_ENTITY))
        current_humidity = self._state_float(entry_data.get(CONF_HUMIDITY_ENTITY))
        wind_speed = self._state_float(entry_data.get(CONF_WIND_ENTITY))

        weather_entity = entry_data.get(CONF_WEATHER_ENTITY)
        forecast = await self._async_get_forecast(weather_entity)

        cloud_cover = None
        weather_state = self.hass.states.get(weather_entity) if weather_entity else None
        if weather_state is not None:
            cloud_cover = weather_state.attributes.get("cloud_coverage")

        results: dict[str, object] = {}

        if MODEL_FROST in enabled_models:
            results[MODEL_FROST] = evaluate_frost_risk(
                current_temp, current_humidity, wind_speed, cloud_cover, forecast
            )

        if MODEL_LATE_BLIGHT in enabled_models or MODEL_POWDERY_MILDEW in enabled_models:
            samples = await self._async_get_history_samples(entry_data)

            if MODEL_LATE_BLIGHT in enabled_models:
                results[MODEL_LATE_BLIGHT] = evaluate_late_blight_risk(samples)

            if MODEL_POWDERY_MILDEW in enabled_models:
                day_temps = [s["temp"] for s in samples if s.get("temp") is not None]
                night_humidities = [
                    s["humidity"]
                    for s in samples
                    if isinstance(s.get("humidity"), (int, float))
                ]
                results[MODEL_POWDERY_MILDEW] = evaluate_powdery_mildew_risk(
                    day_temps, night_humidities
                )

        return results
