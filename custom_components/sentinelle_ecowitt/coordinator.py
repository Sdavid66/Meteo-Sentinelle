"""Coordinator : collecte des données et exécution des modèles.

Trois responsabilités :

1. résoudre chaque mesure avec bascule Ecowitt → station de secours ;
2. construire une **série horaire** à partir du recorder, socle exigé
   par les modèles publiés (Smith, Hutton, Gubler-Thomas) ;
3. porter l'**état persistant** que ces modèles réclament : l'indice
   Gubler-Thomas est cumulatif sur la saison et ne peut pas être
   recalculé depuis une fenêtre glissante, et les traitements déclarés
   doivent survivre à un redémarrage.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.recorder import get_instance, history
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CROP,
    CONF_ENABLED_MODELS,
    CONF_LEAF_WETNESS_ENTITY,
    CONF_RAIN_PENALTY,
    CONF_STAGE,
    CONF_WEATHER_ENTITY,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    HISTORY_HOURS,
    MEASUREMENT_SOURCES,
    MODEL_FROST,
    MODEL_LATE_BLIGHT,
    MODEL_POWDERY_MILDEW,
    SOURCE_FALLBACK,
    SOURCE_NONE,
    SOURCE_PRIMARY,
    STORAGE_KEY,
    STORAGE_VERSION,
    TREATABLE_MODELS,
)
from .models.crops import GENERIC_CROP
from .models.frost import evaluate_frost_risk
from .models.hourly import resample_hourly
from .models.late_blight import evaluate_late_blight_risk
from .models.powdery_mildew import evaluate_powdery_mildew_risk
from .models.treatments import Treatment, adjusted_level, protection_state

_LOGGER = logging.getLogger(__name__)


class SentinelleEcowittCoordinator(DataUpdateCoordinator[dict]):
    """Récupère les données et calcule les risques à intervalle régulier."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.entry = entry
        self.sources: dict[str, str] = {}
        self.treatments: dict[str, Treatment] = {}
        self.protection: dict[str, dict] = {}
        #: État cumulatif de l'indice Gubler-Thomas.
        self._mildew_index: int = 0
        self._mildew_started: bool = False
        self._mildew_last_day: str | None = None
        #: Stade phénologique courant, pilotable par l'entité select.
        self._stage_override: str | None = None
        self._last_rain_check: datetime | None = None
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        super().__init__(
            hass,
            _LOGGER,
            name="Sentinelle Ecowitt",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES),
        )

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------

    async def async_load_state(self) -> None:
        stored = await self._store.async_load() or {}
        mildew = stored.get("powdery_mildew", {})
        self._mildew_index = int(mildew.get("index", 0))
        self._mildew_started = bool(mildew.get("epidemic_started", False))
        self._mildew_last_day = mildew.get("last_processed_day")
        self._stage_override = stored.get("stage")

        for target, data in (stored.get("treatments") or {}).items():
            treatment = Treatment.from_dict(data)
            if treatment is not None:
                self.treatments[target] = treatment

        last_rain = stored.get("last_rain_check")
        if last_rain:
            try:
                self._last_rain_check = datetime.fromisoformat(last_rain)
            except ValueError:
                self._last_rain_check = None

    async def async_save_state(self) -> None:
        await self._store.async_save(
            {
                "powdery_mildew": {
                    "index": self._mildew_index,
                    "epidemic_started": self._mildew_started,
                    "last_processed_day": self._mildew_last_day,
                },
                "stage": self._stage_override,
                "treatments": {
                    target: treatment.to_dict()
                    for target, treatment in self.treatments.items()
                },
                "last_rain_check": (
                    self._last_rain_check.isoformat() if self._last_rain_check else None
                ),
            }
        )

    # ------------------------------------------------------------------
    # Stade phénologique (piloté par l'entité select)
    # ------------------------------------------------------------------

    @property
    def crop(self) -> str:
        data = {**self.entry.data, **self.entry.options}
        return data.get(CONF_CROP, GENERIC_CROP)

    @property
    def stage(self) -> str | None:
        if self._stage_override:
            return self._stage_override
        data = {**self.entry.data, **self.entry.options}
        return data.get(CONF_STAGE)

    async def async_set_stage(self, stage: str) -> None:
        self._stage_override = stage
        await self.async_save_state()
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Traitements
    # ------------------------------------------------------------------

    async def async_log_treatment(
        self,
        target: str,
        product: str,
        residual_days: float,
        rainfast_mm: float,
    ) -> None:
        self.treatments[target] = Treatment(
            target=target,
            product=product,
            applied_at=dt_util.utcnow(),
            residual_days=residual_days,
            rainfast_mm=rainfast_mm,
        )
        await self.async_save_state()
        await self.async_request_refresh()

    async def async_clear_treatment(self, target: str | None = None) -> None:
        if target is None:
            self.treatments.clear()
        else:
            self.treatments.pop(target, None)
        await self.async_save_state()
        await self.async_request_refresh()

    async def async_reset_mildew_index(self) -> None:
        self._mildew_index = 0
        self._mildew_started = False
        self._mildew_last_day = None
        await self.async_save_state()
        await self.async_request_refresh()

    def _accumulate_rain(self, rain_rate: float | None, now: datetime) -> None:
        """Cumule la pluie tombée depuis le dernier cycle sur chaque traitement."""
        previous = self._last_rain_check
        self._last_rain_check = now
        if previous is None or rain_rate is None or rain_rate <= 0:
            return
        elapsed_hours = (now - previous).total_seconds() / 3600.0
        if elapsed_hours <= 0 or elapsed_hours > 6:
            # Trou d'indisponibilité : on n'extrapole pas sur une longue
            # période à partir d'une intensité instantanée.
            return
        millimetres = rain_rate * elapsed_hours
        for treatment in self.treatments.values():
            treatment.add_rain(millimetres)

    # ------------------------------------------------------------------
    # Lecture des états
    # ------------------------------------------------------------------

    def _state_float(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _resolve_measurement(
        self, entry_data: dict, measurement: str
    ) -> tuple[float | None, str]:
        """(valeur, origine), la station Ecowitt restant prioritaire."""
        primary_key, fallback_key = MEASUREMENT_SOURCES[measurement]

        value = self._state_float(entry_data.get(primary_key))
        if value is not None:
            return value, SOURCE_PRIMARY

        value = self._state_float(entry_data.get(fallback_key))
        if value is not None:
            if entry_data.get(primary_key):
                _LOGGER.debug(
                    "Mesure %s : capteur Ecowitt indisponible, bascule sur %s",
                    measurement,
                    entry_data.get(fallback_key),
                )
            return value, SOURCE_FALLBACK

        return None, SOURCE_NONE

    def _resolve_history_entity(self, entry_data: dict, measurement: str) -> str | None:
        primary_key, fallback_key = MEASUREMENT_SOURCES[measurement]
        if self.sources.get(measurement) == SOURCE_FALLBACK:
            return entry_data.get(fallback_key)
        return entry_data.get(primary_key) or entry_data.get(fallback_key)

    # ------------------------------------------------------------------
    # Prévisions et historique
    # ------------------------------------------------------------------

    async def _async_get_forecast(
        self, weather_entity: str | None
    ) -> list[tuple[datetime, float]]:
        """Prévisions horaires via weather.get_forecasts (MeteoSwiss, Met.no...)."""
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
            if isinstance(when, datetime):
                when_dt = when
            else:
                try:
                    when_dt = datetime.fromisoformat(when)
                except (TypeError, ValueError):
                    continue
            result.append((when_dt, temp))
        return result

    async def _async_get_hourly(self, entry_data: dict) -> list:
        """Série horaire reconstruite depuis le recorder."""
        temp_entity = self._resolve_history_entity(entry_data, "temperature")
        humidity_entity = self._resolve_history_entity(entry_data, "humidity")
        rain_entity = self._resolve_history_entity(entry_data, "rain_rate")
        leaf_entity = entry_data.get(CONF_LEAF_WETNESS_ENTITY)

        entity_ids = [
            e for e in (temp_entity, humidity_entity, rain_entity, leaf_entity) if e
        ]
        if not entity_ids:
            return []

        start = dt_util.utcnow() - timedelta(hours=HISTORY_HOURS)

        def _fetch() -> dict[str, list[State]]:
            return history.state_changes_during_period(
                self.hass, start, None, entity_ids, no_attributes=True
            )

        try:
            raw = await get_instance(self.hass).async_add_executor_job(_fetch)
        except Exception as err:  # noqa: BLE001 - l'historique est optionnel
            _LOGGER.debug("Historique indisponible : %s", err)
            return []

        def _numeric(state: State) -> float | None:
            try:
                return float(state.state)
            except (TypeError, ValueError):
                return None

        records: list[dict] = []
        for entity_id, key in (
            (temp_entity, "temp"),
            (humidity_entity, "humidity"),
            (rain_entity, "rain_rate"),
        ):
            if not entity_id:
                continue
            for state in raw.get(entity_id, []):
                value = _numeric(state)
                if value is not None:
                    records.append({"time": state.last_changed, key: value})

        if leaf_entity:
            for state in raw.get(leaf_entity, []):
                value = _numeric(state)
                if value is not None:
                    # Capteur analogique : humectation > 0 = feuille mouillée.
                    wet = value > 0
                else:
                    wet = state.state == "on"
                records.append({"time": state.last_changed, "leaf_wet": wet})

        return resample_hourly(records)

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        entry_data = {**self.entry.data, **self.entry.options}
        enabled = entry_data.get(CONF_ENABLED_MODELS, [MODEL_FROST])
        now = dt_util.utcnow()

        values: dict[str, float | None] = {}
        sources: dict[str, str] = {}
        for measurement in MEASUREMENT_SOURCES:
            value, source = self._resolve_measurement(entry_data, measurement)
            values[measurement] = value
            sources[measurement] = source
        self.sources = sources

        self._accumulate_rain(values.get("rain_rate"), now)

        weather_entity = entry_data.get(CONF_WEATHER_ENTITY)
        forecast = await self._async_get_forecast(weather_entity)

        cloud_cover = None
        weather_state = self.hass.states.get(weather_entity) if weather_entity else None
        if weather_state is not None:
            cloud_cover = weather_state.attributes.get("cloud_coverage")

        results: dict[str, object] = {}

        if MODEL_FROST in enabled:
            results[MODEL_FROST] = evaluate_frost_risk(
                values["temperature"],
                values["humidity"],
                values["wind_speed"],
                cloud_cover,
                forecast,
                crop=self.crop,
                stage=self.stage,
            )

        needs_history = any(
            model in enabled for model in (MODEL_LATE_BLIGHT, MODEL_POWDERY_MILDEW)
        )
        if needs_history:
            hourly = await self._async_get_hourly(entry_data)

            if MODEL_LATE_BLIGHT in enabled:
                results[MODEL_LATE_BLIGHT] = evaluate_late_blight_risk(hourly)

            if MODEL_POWDERY_MILDEW in enabled:
                mildew = evaluate_powdery_mildew_risk(
                    hourly,
                    index=self._mildew_index,
                    epidemic_started=self._mildew_started,
                    last_processed_day=self._mildew_last_day,
                    apply_rain_penalty=entry_data.get(CONF_RAIN_PENALTY, True),
                )
                self._mildew_index = mildew.index
                self._mildew_started = mildew.epidemic_started
                self._mildew_last_day = mildew.last_processed_day
                results[MODEL_POWDERY_MILDEW] = mildew

        # Protection en cours : rétrograde le niveau affiché et expose
        # l'échéance « protégé jusqu'à ».
        self.protection = {}
        for target in TREATABLE_MODELS:
            if target not in enabled:
                continue
            treatment = self.treatments.get(target)
            self.protection[target] = protection_state(treatment, now)
            result = results.get(target)
            if result is not None and treatment is not None:
                result.level = adjusted_level(result.level, treatment, now)

        await self.async_save_state()
        return results
