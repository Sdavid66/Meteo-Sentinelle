"""Coordinator : collecte des données et exécution des modèles.

Le site est partagé (capteurs, prévisions, degrés-jours), les **arbres**
sont individuels : chacun a son stade phénologique, donc ses propres
seuils de gel, ses propres modèles maladie selon l'espèce, son propre
indice oïdium et ses propres traitements.

Une seule requête de prévisions et une seule lecture d'historique
alimentent tous les arbres.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.components.recorder import get_instance, history
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENABLED_MODELS,
    CONF_LEAF_WETNESS_ENTITY,
    CONF_RAIN_PENALTY,
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
    SUBENTRY_TYPE_TREE,
)
from .models import phenology
from .models.frost import evaluate_frost_risk
from .models.hourly import HourlySample, complete_days, resample_hourly
from .models.late_blight import evaluate_late_blight_risk
from .models.phenology import GddState
from .models.powdery_mildew import evaluate_powdery_mildew_risk
from .models.treatments import Treatment, adjusted_level, protection_state
from .tree import Tree

_LOGGER = logging.getLogger(__name__)

#: Profondeur d'historique pour les degrés-jours : couvre une reprise
#: après plusieurs jours d'arrêt de Home Assistant.
GDD_HISTORY_DAYS = 10


class MeteoSentinelleCoordinator(DataUpdateCoordinator[dict]):
    """Calcule les risques du site et de chaque arbre."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.entry = entry
        self.sources: dict[str, str] = {}
        self.trees: dict[str, Tree] = {}
        #: Traitements indexés par (subentry_id, modèle).
        self.treatments: dict[tuple[str, str], Treatment] = {}
        self.protection: dict[str, dict[str, dict]] = {}
        self.gdd = GddState(season_year=dt_util.now().year)
        #: Avancements de stade appliqués au dernier cycle, à notifier.
        self.pending_advances: list[dict] = []
        self._last_rain_check: datetime | None = None
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        super().__init__(
            hass,
            _LOGGER,
            name="Météo Sentinelle",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES),
        )

    # ------------------------------------------------------------------
    # Arbres
    # ------------------------------------------------------------------

    def load_trees(self) -> None:
        """(Re)construit la liste des arbres depuis les sous-entrées."""
        existing = dict(self.trees)
        self.trees = {}
        for subentry in self.entry.subentries.values():
            if subentry.subentry_type != SUBENTRY_TYPE_TREE:
                continue
            tree = Tree.from_subentry(subentry.subentry_id, dict(subentry.data))
            previous = existing.get(subentry.subentry_id)
            if previous is not None:
                # Conserve l'état vivant (stade avancé, indice, niveaux).
                tree.restore_state(previous.state_dict())
                # Sauf si l'utilisateur vient de changer d'espèce.
                if previous.crop != tree.crop:
                    tree.stage = subentry.data.get("stage")
                    tree.mildew_index = 0
                    tree.mildew_started = False
                    tree.mildew_last_day = None
            self.trees[subentry.subentry_id] = tree

    def tree(self, subentry_id: str) -> Tree | None:
        return self.trees.get(subentry_id)

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------

    async def async_load_state(self) -> None:
        stored = await self._store.async_load() or {}

        gdd = stored.get("gdd") or {}
        self.gdd = GddState(
            season_year=int(gdd.get("season_year", dt_util.now().year)),
            total=float(gdd.get("total", 0.0)),
            last_day=gdd.get("last_day"),
            recent=list(gdd.get("recent") or []),
        )

        self.load_trees()
        for subentry_id, data in (stored.get("trees") or {}).items():
            tree = self.trees.get(subentry_id)
            if tree is not None:
                tree.restore_state(data)

        for key, data in (stored.get("treatments") or {}).items():
            if "|" not in key:
                continue
            subentry_id, target = key.split("|", 1)
            treatment = Treatment.from_dict(data)
            if treatment is not None:
                self.treatments[(subentry_id, target)] = treatment

        last_rain = stored.get("last_rain_check")
        if last_rain:
            try:
                self._last_rain_check = datetime.fromisoformat(last_rain)
            except ValueError:
                self._last_rain_check = None

    async def async_save_state(self) -> None:
        await self._store.async_save(
            {
                "gdd": {
                    "season_year": self.gdd.season_year,
                    "total": self.gdd.total,
                    "last_day": self.gdd.last_day,
                    "recent": self.gdd.recent,
                },
                "trees": {
                    subentry_id: tree.state_dict()
                    for subentry_id, tree in self.trees.items()
                },
                "treatments": {
                    f"{subentry_id}|{target}": treatment.to_dict()
                    for (subentry_id, target), treatment in self.treatments.items()
                },
                "last_rain_check": (
                    self._last_rain_check.isoformat() if self._last_rain_check else None
                ),
            }
        )

    # ------------------------------------------------------------------
    # Actions utilisateur
    # ------------------------------------------------------------------

    async def async_set_stage(self, subentry_id: str, stage: str) -> None:
        """Correction manuelle du stade : elle fait autorité."""
        tree = self.trees.get(subentry_id)
        if tree is None or tree.stage == stage:
            return
        tree.stage = stage
        tree.stage_auto_applied = False
        tree.stage_changed_at = dt_util.utcnow()
        if stage in phenology.BLOOM_STAGES and tree.bloom_date is None:
            tree.bloom_date = dt_util.utcnow()
        await self.async_save_state()
        await self.async_request_refresh()

    async def async_log_treatment(
        self,
        target: str,
        product: str,
        residual_days: float,
        rainfast_mm: float,
        subentry_ids: list[str] | None = None,
    ) -> None:
        ids = subentry_ids if subentry_ids is not None else list(self.trees)
        now = dt_util.utcnow()
        for subentry_id in ids:
            tree = self.trees.get(subentry_id)
            if tree is None or target not in tree.models:
                continue
            self.treatments[(subentry_id, target)] = Treatment(
                target=target,
                product=product,
                applied_at=now,
                residual_days=residual_days,
                rainfast_mm=rainfast_mm,
            )
        await self.async_save_state()
        await self.async_request_refresh()

    async def async_clear_treatment(
        self, target: str | None = None, subentry_ids: list[str] | None = None
    ) -> None:
        ids = set(subentry_ids) if subentry_ids is not None else set(self.trees)
        for key in list(self.treatments):
            subentry_id, existing_target = key
            if subentry_id in ids and (target is None or existing_target == target):
                self.treatments.pop(key, None)
        await self.async_save_state()
        await self.async_request_refresh()

    async def async_reset_mildew_index(
        self, subentry_ids: list[str] | None = None
    ) -> None:
        ids = subentry_ids if subentry_ids is not None else list(self.trees)
        for subentry_id in ids:
            tree = self.trees.get(subentry_id)
            if tree is None:
                continue
            tree.mildew_index = 0
            tree.mildew_started = False
            tree.mildew_last_day = None
        await self.async_save_state()
        await self.async_request_refresh()

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

    def _accumulate_rain(self, rain_rate: float | None, now: datetime) -> None:
        previous = self._last_rain_check
        self._last_rain_check = now
        if previous is None or rain_rate is None or rain_rate <= 0:
            return
        elapsed_hours = (now - previous).total_seconds() / 3600.0
        if elapsed_hours <= 0 or elapsed_hours > 6:
            return
        millimetres = rain_rate * elapsed_hours
        for treatment in self.treatments.values():
            treatment.add_rain(millimetres)

    # ------------------------------------------------------------------
    # Prévisions et historique
    # ------------------------------------------------------------------

    async def _async_get_forecast(
        self, weather_entity: str | None
    ) -> list[tuple[datetime, float]]:
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

    async def _async_get_hourly(
        self, entry_data: dict, hours: int
    ) -> list[HourlySample]:
        temp_entity = self._resolve_history_entity(entry_data, "temperature")
        humidity_entity = self._resolve_history_entity(entry_data, "humidity")
        rain_entity = self._resolve_history_entity(entry_data, "rain_rate")
        leaf_entity = entry_data.get(CONF_LEAF_WETNESS_ENTITY)

        entity_ids = [
            e for e in (temp_entity, humidity_entity, rain_entity, leaf_entity) if e
        ]
        if not entity_ids:
            return []

        start = dt_util.utcnow() - timedelta(hours=hours)

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
                wet = value > 0 if value is not None else state.state == "on"
                records.append({"time": state.last_changed, "leaf_wet": wet})

        return resample_hourly(records)

    # ------------------------------------------------------------------
    # Degrés-jours et phénologie
    # ------------------------------------------------------------------

    def _update_gdd(self, hourly: list[HourlySample]) -> None:
        """Cumule les degrés-jours des journées complètes disponibles."""
        days: list[tuple[date, float | None, float | None]] = []
        for day, samples in complete_days(hourly):
            temps = [s.temp for s in samples if s.temp is not None]
            if not temps:
                continue
            days.append((day, min(temps), max(temps)))
        if days:
            self.gdd = phenology.accumulate(self.gdd, days)

    def _advance_stages(self, now: datetime) -> None:
        """Applique l'avancement automatique des stades.

        L'avancement est monotone et ne s'applique qu'aux arbres dont
        l'utilisateur n'a pas désactivé l'automatisme.
        """
        self.pending_advances = []
        for tree in self.trees.values():
            if not tree.auto_advance:
                continue
            proposed = phenology.propose_advance(
                tree.crop, tree.stage, self.gdd.total, tree.gdd_offset
            )
            if proposed is None:
                continue

            previous = tree.stage
            tree.stage = proposed
            tree.stage_auto_applied = True
            tree.stage_changed_at = now
            if proposed in phenology.BLOOM_STAGES and tree.bloom_date is None:
                tree.bloom_date = now

            self.pending_advances.append(
                {
                    "subentry_id": tree.subentry_id,
                    "tree": tree.display_name,
                    "crop": tree.crop,
                    "previous_stage": previous,
                    "stage": proposed,
                    "gdd": round(self.gdd.total, 1),
                }
            )

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        entry_data = {**self.entry.data, **self.entry.options}
        enabled = entry_data.get(CONF_ENABLED_MODELS, [MODEL_FROST])
        now = dt_util.utcnow()

        self.load_trees()

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

        # Une seule lecture d'historique, assez profonde pour les
        # degrés-jours, réutilisée par tous les modèles et tous les arbres.
        hourly = await self._async_get_hourly(
            entry_data, max(HISTORY_HOURS, GDD_HISTORY_DAYS * 24)
        )
        self._update_gdd(hourly)
        self._advance_stages(now)

        # Fenêtre courte pour les modèles maladie.
        recent_cutoff = dt_util.utcnow() - timedelta(hours=HISTORY_HOURS)
        recent = [s for s in hourly if s.time >= recent_cutoff]

        blight_shared = (
            evaluate_late_blight_risk(recent) if MODEL_LATE_BLIGHT in enabled else None
        )
        rain_penalty = entry_data.get(CONF_RAIN_PENALTY, True)

        results: dict[str, dict] = {}
        self.protection = {}

        for subentry_id, tree in self.trees.items():
            tree_results: dict[str, object] = {}

            if MODEL_FROST in enabled and MODEL_FROST in tree.models:
                tree_results[MODEL_FROST] = evaluate_frost_risk(
                    values["temperature"],
                    values["humidity"],
                    values["wind_speed"],
                    cloud_cover,
                    forecast,
                    crop=tree.crop,
                    stage=tree.stage,
                )

            if (
                MODEL_LATE_BLIGHT in enabled
                and MODEL_LATE_BLIGHT in tree.models
                and blight_shared is not None
            ):
                # Le risque météo est identique pour tout le site ; seule
                # la protection diffère d'un arbre à l'autre.
                tree_results[MODEL_LATE_BLIGHT] = evaluate_late_blight_risk(recent)

            if MODEL_POWDERY_MILDEW in enabled and MODEL_POWDERY_MILDEW in tree.models:
                mildew = evaluate_powdery_mildew_risk(
                    recent,
                    index=tree.mildew_index,
                    epidemic_started=tree.mildew_started,
                    last_processed_day=tree.mildew_last_day,
                    apply_rain_penalty=rain_penalty,
                )
                tree.mildew_index = mildew.index
                tree.mildew_started = mildew.epidemic_started
                tree.mildew_last_day = mildew.last_processed_day
                tree_results[MODEL_POWDERY_MILDEW] = mildew

            # Protection en cours : rétrograde le niveau affiché.
            tree_protection: dict[str, dict] = {}
            for target in (MODEL_LATE_BLIGHT, MODEL_POWDERY_MILDEW):
                if target not in tree_results:
                    continue
                treatment = self.treatments.get((subentry_id, target))
                tree_protection[target] = protection_state(treatment, now)
                if treatment is not None:
                    tree_results[target].level = adjusted_level(
                        tree_results[target].level, treatment, now
                    )

            self.protection[subentry_id] = tree_protection
            results[subentry_id] = tree_results

        await self.async_save_state()
        return results

    # ------------------------------------------------------------------
    # Accès pratique pour les entités
    # ------------------------------------------------------------------

    def result(self, subentry_id: str, model: str):
        return (self.data or {}).get(subentry_id, {}).get(model)

    def tree_protection(self, subentry_id: str, model: str) -> dict:
        return (self.protection.get(subentry_id) or {}).get(model, {})
