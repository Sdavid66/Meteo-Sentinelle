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
    TREATABLE_MODELS,
)
from .models import pests as pest_models
from .models import phenology
from .models.frost import evaluate_frost_risk
from .models.hourly import HourlySample, complete_days, resample_hourly
from .models.late_blight import evaluate_late_blight_risk
from .models.phenology import GddState
from .models.powdery_mildew import evaluate_powdery_mildew_risk
from .models.spray import ForecastHour, SprayAdvice, find_spray_windows
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
        #: Cumuls thermiques des ravageurs, indexés par barème
        #: (base, plafond) : deux ravageurs de même barème partagent la
        #: même série plutôt que de la recalculer chacun de leur côté.
        self.pest_gdd: dict[str, GddState] = {}
        #: Avancements de stade appliqués au dernier cycle, à notifier.
        self.pending_advances: list[dict] = []
        #: Couverture réelle de l'historique horaire, pour le diagnostic.
        self.history_coverage: dict = {}
        #: Créneaux de pulvérisation trouvés dans les prévisions.
        self.spray: SprayAdvice = SprayAdvice()
        self._recorder_available = True
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
                    # Un biofix de carpocapse n'a aucun sens sur un
                    # cerisier : on repart de zéro plutôt que de traîner
                    # une origine de cumul héritée d'une autre espèce.
                    tree.biofix = {}
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
            first_day=gdd.get("first_day"),
            recent=list(gdd.get("recent") or []),
        )

        self.pest_gdd = {
            key: GddState(
                season_year=int(data.get("season_year", dt_util.now().year)),
                total=float(data.get("total", 0.0)),
                last_day=data.get("last_day"),
                first_day=data.get("first_day"),
                recent=list(data.get("recent") or []),
            )
            for key, data in (stored.get("pest_gdd") or {}).items()
            if isinstance(data, dict)
        }

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
                    "first_day": self.gdd.first_day,
                    "recent": self.gdd.recent,
                },
                "pest_gdd": {
                    key: {
                        "season_year": state.season_year,
                        "total": state.total,
                        "last_day": state.last_day,
                        "first_day": state.first_day,
                        # Le détail journalier n'a d'intérêt que pour le
                        # cumul phénologique, affiché à l'utilisateur.
                        "recent": [],
                    }
                    for key, state in self.pest_gdd.items()
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

    async def async_set_biofix(
        self,
        pest: str,
        when: date | None = None,
        subentry_ids: list[str] | None = None,
    ) -> None:
        """Déclare l'événement qui donne son origine au cumul d'un ravageur.

        Première capture au piège à phéromone pour le carpocapse,
        premières pontes pour le doryphore. C'est l'observation de
        l'utilisateur, elle fait donc autorité sur le biofix estimé à
        partir du stade phénologique.

        Le cumul depuis le biofix se déduit ensuite par soustraction du
        cumul saisonnier. Un biofix daté d'avant le début de la série
        connue ne peut pas être reconstitué : on le rattache alors au
        début de la série, avec l'écart que cela implique — c'est plus
        honnête que de refuser silencieusement la déclaration.
        """
        definition = pest_models.PESTS.get(pest)
        if definition is None:
            return

        state = self.pest_gdd.get(pest_models.accumulator_key(definition))
        reference = state.total if state is not None else 0.0
        day = when or dt_util.now().date()

        ids = subentry_ids if subentry_ids is not None else list(self.trees)
        for subentry_id in ids:
            tree = self.trees.get(subentry_id)
            if tree is None or pest not in tree.pests:
                continue
            tree.biofix[pest] = {
                "date": day.isoformat(),
                "gdd": round(reference, 1),
                "estimated": False,
            }
        await self.async_save_state()
        await self.async_request_refresh()

    async def async_clear_biofix(
        self, pest: str | None = None, subentry_ids: list[str] | None = None
    ) -> None:
        """Efface un biofix : le modèle revient en attente d'observation."""
        ids = subentry_ids if subentry_ids is not None else list(self.trees)
        for subentry_id in ids:
            tree = self.trees.get(subentry_id)
            if tree is None:
                continue
            if pest is None:
                tree.biofix = {}
            else:
                tree.biofix.pop(pest, None)
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
    ) -> list[ForecastHour]:
        """Prévisions horaires, réduites aux grandeurs que les modèles utilisent.

        La même requête sert au gel (température) et aux fenêtres de
        pulvérisation (vent, pluie) : les extraire ensemble évite un
        second appel pour les mêmes données.
        """
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
        result: list[ForecastHour] = []
        for item in forecasts:
            when = item.get("datetime")
            if when is None:
                continue
            if isinstance(when, datetime):
                when_dt = when
            else:
                try:
                    when_dt = datetime.fromisoformat(when)
                except (TypeError, ValueError):
                    continue
            # Le capteur de fenêtre de traitement porte un device_class
            # « timestamp », qui exige un fuseau. Les prévisions en
            # fournissent un, mais un filet de sécurité coûte moins cher
            # qu'une entité en erreur.
            if when_dt.tzinfo is None:
                when_dt = when_dt.replace(tzinfo=dt_util.UTC)
            result.append(
                ForecastHour(
                    time=when_dt,
                    temperature=item.get("temperature"),
                    wind_speed=item.get("wind_speed"),
                    precipitation=item.get("precipitation"),
                )
            )
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
            # `state_changes_during_period` ne prend qu'**une** entité
            # (`entity_id`, au singulier) et lui applique `.lower()` :
            # lui passer une liste lève une AttributeError. La fonction
            # multi-entités est `get_significant_states`, avec
            # `significant_changes_only=False` pour ne rien filtrer —
            # sur des mesures numériques, le filtrage « changements
            # significatifs » trouerait les séries horaires.
            return history.get_significant_states(
                self.hass,
                start,
                None,
                entity_ids=entity_ids,
                include_start_time_state=True,
                significant_changes_only=False,
                minimal_response=False,
                no_attributes=True,
            )

        try:
            raw = await get_instance(self.hass).async_add_executor_job(_fetch)
        except Exception as err:  # noqa: BLE001 - l'historique est optionnel
            # Première bascule seulement : répéter l'avertissement toutes
            # les 15 minutes noierait le journal. La réparation, elle,
            # reste visible tant que le problème dure.
            if self._recorder_available:
                _LOGGER.warning(
                    "Lecture de l'historique impossible, les modèles maladie "
                    "vont rester sans données : %s",
                    err,
                    exc_info=True,
                )
            self._recorder_available = False
            return []

        if not self._recorder_available:
            _LOGGER.info("Lecture de l'historique rétablie")
        self._recorder_available = True

        def _numeric(state: State) -> float | None:
            try:
                return float(state.state)
            except (TypeError, ValueError):
                return None

        def _when(state: State) -> datetime:
            """Horodatage ramené dans la fenêtre interrogée.

            `include_start_time_state` renvoie l'état **en vigueur** au
            début de la fenêtre, dont la date de changement peut être
            bien antérieure — un capteur stable depuis trois semaines
            porte une date vieille de trois semaines. Sans recadrage, le
            rééchantillonnage créerait une heure isolée très ancienne,
            qui fausserait le comptage des journées complètes.
            """
            return max(state.last_changed, start)

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
                    records.append({"time": _when(state), key: value})

        if leaf_entity:
            for state in raw.get(leaf_entity, []):
                value = _numeric(state)
                wet = value > 0 if value is not None else state.state == "on"
                records.append({"time": _when(state), "leaf_wet": wet})

        return resample_hourly(records)

    # ------------------------------------------------------------------
    # Diagnostic de l'historique
    # ------------------------------------------------------------------

    def _update_history_coverage(self, recent: list[HourlySample]) -> None:
        """Mesure ce que le recorder a réellement fourni.

        Les modèles maladie exigent des séries horaires continues sur
        plusieurs jours. Si les capteurs sont exclus du recorder, ou si
        l'instance vient d'être installée, ces modèles ne trouvent rien
        et renvoient « aucun risque » — un faux négatif indiscernable
        d'une vraie absence de risque. Cette mesure permet de le dire
        plutôt que de le laisser passer.
        """
        temp_hours = sum(1 for sample in recent if sample.temp is not None)
        humidity_hours = sum(1 for sample in recent if sample.humidity is not None)

        self.history_coverage = {
            "window_hours": HISTORY_HOURS,
            "hours": len(recent),
            "temperature_hours": temp_hours,
            "humidity_hours": humidity_hours,
            # Le facteur limitant est la mesure la moins bien couverte :
            # un critère « 6 h continues à HR ≥ 90 % » ne vaut rien si
            # l'humidité manque, même avec une température complète.
            "usable_hours": min(temp_hours, humidity_hours),
            "recorder_available": self._recorder_available,
        }

    # ------------------------------------------------------------------
    # Degrés-jours et phénologie
    # ------------------------------------------------------------------

    def _update_gdd(self, hourly: list[HourlySample]) -> None:
        """Cumule les degrés-jours des journées complètes disponibles.

        Une seule lecture des journées alimente tous les barèmes : celui
        de la phénologie (base 5,6 °C) et ceux des ravageurs. Chaque
        cumulateur reste idempotent de son côté, donc un barème ajouté
        en cours de saison démarre simplement plus tard, sans fausser
        les autres.
        """
        days: list[tuple[date, float | None, float | None]] = []
        for day, samples in complete_days(hourly):
            temps = [s.temp for s in samples if s.temp is not None]
            if not temps:
                continue
            days.append((day, min(temps), max(temps)))
        if not days:
            return

        self.gdd = phenology.accumulate(self.gdd, days)

        for key, (base, upper) in pest_models.required_accumulators().items():
            state = self.pest_gdd.get(key) or GddState(season_year=days[0][0].year)
            self.pest_gdd[key] = phenology.accumulate(state, days, base, upper)

    def _pest_total(self, pest: str) -> float | None:
        """Cumul saisonnier courant pour le barème d'un ravageur."""
        definition = pest_models.PESTS.get(pest)
        if definition is None:
            return None
        state = self.pest_gdd.get(pest_models.accumulator_key(definition))
        return state.total if state is not None else None

    def _auto_biofix(self, tree: Tree, now: datetime) -> None:
        """Pose un biofix approché à partir du stade phénologique.

        Certains modèles n'ont de sens qu'à partir d'un événement
        observé. Exiger un piège à phéromone pour que le capteur affiche
        quelque chose rendrait la fonction inutilisable pour la plupart
        des jardiniers ; inventer une origine sans le dire serait pire.

        Compromis retenu : quand un stade d'ancrage est documenté (le
        premier vol du carpocapse coïncide en gros avec la floraison),
        le biofix est posé automatiquement et **marqué comme estimé**.
        Une déclaration manuelle l'écrase et n'est jamais réécrasée,
        exactement comme une correction de stade.
        """
        for pest in tree.pests:
            definition = pest_models.PESTS.get(pest)
            if definition is None or not definition.needs_biofix:
                continue
            if definition.biofix_anchor is None:
                continue
            existing = tree.biofix.get(pest)
            if existing is not None:
                continue
            stages = phenology.ordered_stages(tree.crop)
            anchor = definition.biofix_anchor
            if tree.stage is None or anchor not in stages:
                continue
            if tree.stage not in stages:
                continue
            if stages.index(tree.stage) < stages.index(anchor):
                continue

            total = self._pest_total(pest)
            tree.biofix[pest] = {
                "date": now.date().isoformat(),
                "gdd": round(total or 0.0, 1),
                "estimated": True,
            }
            _LOGGER.debug(
                "Biofix %s estimé pour « %s » au stade %s",
                pest,
                tree.display_name,
                tree.stage,
            )

    def _evaluate_pests(self, tree: Tree, enabled: list[str]) -> dict[str, object]:
        """Évalue les ravageurs pertinents pour un arbre."""
        results: dict[str, object] = {}
        for pest in tree.pests:
            if pest not in enabled:
                continue
            definition = pest_models.PESTS.get(pest)
            if definition is None:
                continue

            total = self._pest_total(pest)
            biofix = tree.biofix.get(pest)

            if definition.origin == pest_models.ORIGIN_BIOFIX:
                if biofix is None:
                    since = None
                else:
                    since = max(0.0, (total or 0.0) - float(biofix.get("gdd", 0.0)))
            else:
                since = total

            state = self.pest_gdd.get(pest_models.accumulator_key(definition))
            risk = pest_models.evaluate_pest_risk(
                pest,
                since,
                biofix_date=(biofix or {}).get("date"),
                biofix_estimated=bool((biofix or {}).get("estimated")),
                complete_season=bool(state and state.complete_season),
            )
            if risk is not None:
                results[pest] = risk
        return results

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

        # Le modèle de gel ne demande que (heure, température) ; les
        # fenêtres de pulvérisation exploitent la prévision complète.
        temperatures = [
            (hour.time, hour.temperature)
            for hour in forecast
            if hour.temperature is not None
        ]
        self.spray = find_spray_windows(forecast, now=now)

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
        self._update_history_coverage(recent)

        blight_shared = (
            evaluate_late_blight_risk(recent) if MODEL_LATE_BLIGHT in enabled else None
        )
        rain_penalty = entry_data.get(CONF_RAIN_PENALTY, True)

        results: dict[str, dict] = {}
        self.protection = {}

        for subentry_id, tree in self.trees.items():
            self._auto_biofix(tree, now)
            tree_results: dict[str, object] = self._evaluate_pests(tree, enabled)

            if MODEL_FROST in enabled and MODEL_FROST in tree.models:
                tree_results[MODEL_FROST] = evaluate_frost_risk(
                    values["temperature"],
                    values["humidity"],
                    values["wind_speed"],
                    cloud_cover,
                    temperatures,
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
            for target in TREATABLE_MODELS:
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
