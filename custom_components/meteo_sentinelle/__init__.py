"""Intégration Météo Sentinelle."""
from __future__ import annotations

import logging
from types import MappingProxyType

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv

from .alerting import process_risk_changes, process_stage_advances
from .const import (
    ATTR_DATE,
    ATTR_PEST,
    ATTR_PRODUCT,
    ATTR_RAINFAST_MM,
    ATTR_RESIDUAL_DAYS,
    ATTR_STAGE,
    ATTR_TARGET,
    ATTR_TREE,
    CONF_ASSIST_SENTENCES,
    CONF_ENABLED_MODELS,
    CONF_NOTIFICATIONS,
    DEFAULT_ASSIST_SENTENCES,
    DEFAULT_ENABLED_MODELS,
    DEFAULT_NOTIFICATIONS,
    DOMAIN,
    PEST_MODELS,
    SERVICE_CLEAR_BIOFIX,
    SERVICE_CLEAR_TREATMENT,
    SERVICE_LOG_TREATMENT,
    SERVICE_RESET_MILDEW_INDEX,
    SERVICE_SET_BIOFIX,
    SERVICE_SET_STAGE,
    SUBENTRY_TYPE_TREE,
    TREATABLE_MODELS,
)
from .coordinator import MeteoSentinelleCoordinator
from .frontend import async_register_card
from .history_check import async_check_history, async_clear_issues
from .intents import async_setup_intents
from .localize import async_preload
from .models.treatments import DEFAULT_RAINFAST_MM, DEFAULT_RESIDUAL_DAYS
from .sentences import async_install_sentences
from .tree import legacy_tree_data, match_trees, strip_legacy_keys

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "select", "switch"]

#: `tree` accepte un nom d'arbre ou un identifiant de sous-entrée ;
#: omis, l'action s'applique à tous les arbres concernés.
_TREE_SELECTOR = vol.Any(cv.string, [cv.string])

LOG_TREATMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TARGET): vol.In(TREATABLE_MODELS),
        vol.Optional(ATTR_TREE): _TREE_SELECTOR,
        vol.Optional(ATTR_PRODUCT, default=""): cv.string,
        vol.Optional(ATTR_RESIDUAL_DAYS, default=DEFAULT_RESIDUAL_DAYS): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=90)
        ),
        vol.Optional(ATTR_RAINFAST_MM, default=DEFAULT_RAINFAST_MM): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=500)
        ),
    }
)

CLEAR_TREATMENT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_TARGET): vol.In(TREATABLE_MODELS),
        vol.Optional(ATTR_TREE): _TREE_SELECTOR,
    }
)

RESET_MILDEW_SCHEMA = vol.Schema({vol.Optional(ATTR_TREE): _TREE_SELECTOR})

SET_STAGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TREE): _TREE_SELECTOR,
        vol.Required(ATTR_STAGE): cv.string,
    }
)

SET_BIOFIX_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PEST): vol.In(PEST_MODELS),
        vol.Optional(ATTR_TREE): _TREE_SELECTOR,
        vol.Optional(ATTR_DATE): cv.date,
    }
)

CLEAR_BIOFIX_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_PEST): vol.In(PEST_MODELS),
        vol.Optional(ATTR_TREE): _TREE_SELECTOR,
    }
)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Fait évoluer une entrée créée par une version antérieure.

    Jusqu'à la v0.3, une entrée portait **une seule** culture, décrite
    directement par les clés `crop` et `stage`. Depuis la v0.4, chaque
    arbre est une sous-entrée distincte.

    La migration convertit donc l'ancienne culture unique en un premier
    arbre, afin qu'une installation existante retrouve ses capteurs au
    lieu de repartir de zéro. Un arbre est créé même si aucune culture
    n'était configurée : sans arbre, l'intégration ne produirait plus
    aucune entité de risque.
    """
    if entry.version > 4:
        # Entrée écrite par une version plus récente : on ne sait pas la
        # rétrograder, et écraser ses données serait pire que d'échouer.
        _LOGGER.error(
            "Entrée créée par une version plus récente de Météo Sentinelle "
            "(version %s) : rétrogradation impossible",
            entry.version,
        )
        return False

    if entry.version == 4:
        return True

    _LOGGER.info(
        "Migration de Météo Sentinelle depuis la version %s vers la version 4",
        entry.version,
    )

    already_has_tree = any(
        subentry.subentry_type == SUBENTRY_TYPE_TREE
        for subentry in entry.subentries.values()
    )

    if not already_has_tree:
        tree_data = legacy_tree_data(dict(entry.data))
        subentry = ConfigSubentry(
            data=MappingProxyType(tree_data),
            subentry_type=SUBENTRY_TYPE_TREE,
            title=tree_data["tree_name"],
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(entry, subentry)
        _LOGGER.info(
            "Culture « %s » convertie en arbre surveillé « %s »",
            tree_data["crop"],
            tree_data["tree_name"],
        )

    hass.config_entries.async_update_entry(
        entry, data=strip_legacy_keys(dict(entry.data)), version=4
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Les notifications se composent dans un callback synchrone : les
    # traductions doivent déjà être en cache à ce moment-là.
    await async_preload(hass)

    coordinator = MeteoSentinelleCoordinator(hass, entry)
    await coordinator.async_load_state()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    _async_register_services(hass)

    # La carte Lovelace et les intents ne dépendent pas de l'entrée :
    # ils sont enregistrés une fois pour l'instance, et les fonctions
    # concernées sont idempotentes.
    await async_register_card(hass)
    async_setup_intents(hass)

    data = {**entry.data, **entry.options}
    if data.get(CONF_ASSIST_SENTENCES, DEFAULT_ASSIST_SENTENCES):
        await async_install_sentences(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # L'alerting s'accroche après le premier rafraîchissement, pour ne pas
    # notifier en rafale au démarrage sur des niveaux déjà connus.
    _async_setup_alerting(hass, entry, coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_clear_issues(hass, entry.entry_id)
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_LOG_TREATMENT,
                SERVICE_CLEAR_TREATMENT,
                SERVICE_RESET_MILDEW_INDEX,
                SERVICE_SET_STAGE,
                SERVICE_SET_BIOFIX,
                SERVICE_CLEAR_BIOFIX,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_setup_alerting(
    hass: HomeAssistant, entry: ConfigEntry, coordinator
) -> None:
    """Branche l'émission d'alertes sur chaque mise à jour du coordinator."""
    # Amorce les niveaux connus sans notifier : au démarrage, un risque
    # déjà en cours n'est pas une nouveauté.
    for subentry_id, results in (coordinator.data or {}).items():
        tree = coordinator.tree(subentry_id)
        if tree is None:
            continue
        for model, result in results.items():
            level = getattr(result, "level", None)
            if level is not None:
                tree.last_levels.setdefault(model, level)
    coordinator.pending_advances = []

    @callback
    def _handle_update() -> None:
        data = {**entry.data, **entry.options}
        enabled = data.get(CONF_NOTIFICATIONS, DEFAULT_NOTIFICATIONS)
        process_stage_advances(hass, coordinator, enabled)
        process_risk_changes(hass, coordinator, enabled)
        # Une dégradation silencieuse des modèles vaut d'être signalée
        # au même moment que les risques : c'est le même cycle.
        async_check_history(
            hass,
            entry.entry_id,
            coordinator,
            data.get(CONF_ENABLED_MODELS, DEFAULT_ENABLED_MODELS),
        )

    entry.async_on_unload(coordinator.async_add_listener(_handle_update))


def _coordinators(hass: HomeAssistant) -> list[MeteoSentinelleCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


def _resolve_trees(coordinator, requested) -> list[str] | None:
    """Traduit un nom ou un identifiant d'arbre en identifiants de sous-entrée.

    Renvoie None si rien n'est demandé (= tous les arbres). La logique de
    rapprochement vit dans `tree.match_trees`, partagée avec les intents
    Assist : un nom dicté et un nom saisi méritent la même tolérance.
    """
    return match_trees(coordinator.trees, requested)


def _async_register_services(hass: HomeAssistant) -> None:
    """Enregistre les services une seule fois, quel que soit le nombre d'entrées."""
    if hass.services.has_service(DOMAIN, SERVICE_LOG_TREATMENT):
        return

    async def _log_treatment(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_log_treatment(
                target=call.data[ATTR_TARGET],
                product=call.data.get(ATTR_PRODUCT, ""),
                residual_days=call.data.get(ATTR_RESIDUAL_DAYS, DEFAULT_RESIDUAL_DAYS),
                rainfast_mm=call.data.get(ATTR_RAINFAST_MM, DEFAULT_RAINFAST_MM),
                subentry_ids=_resolve_trees(coordinator, call.data.get(ATTR_TREE)),
            )

    async def _clear_treatment(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_clear_treatment(
                target=call.data.get(ATTR_TARGET),
                subentry_ids=_resolve_trees(coordinator, call.data.get(ATTR_TREE)),
            )

    async def _reset_mildew(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_reset_mildew_index(
                subentry_ids=_resolve_trees(coordinator, call.data.get(ATTR_TREE))
            )

    async def _set_stage(call: ServiceCall) -> None:
        stage = call.data[ATTR_STAGE]
        for coordinator in _coordinators(hass):
            for subentry_id in _resolve_trees(coordinator, call.data[ATTR_TREE]) or []:
                await coordinator.async_set_stage(subentry_id, stage)

    hass.services.async_register(
        DOMAIN, SERVICE_LOG_TREATMENT, _log_treatment, schema=LOG_TREATMENT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_TREATMENT, _clear_treatment, schema=CLEAR_TREATMENT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_MILDEW_INDEX, _reset_mildew, schema=RESET_MILDEW_SCHEMA
    )
    async def _set_biofix(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_set_biofix(
                pest=call.data[ATTR_PEST],
                when=call.data.get(ATTR_DATE),
                subentry_ids=_resolve_trees(coordinator, call.data.get(ATTR_TREE)),
            )

    async def _clear_biofix(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_clear_biofix(
                pest=call.data.get(ATTR_PEST),
                subentry_ids=_resolve_trees(coordinator, call.data.get(ATTR_TREE)),
            )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_STAGE, _set_stage, schema=SET_STAGE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_BIOFIX, _set_biofix, schema=SET_BIOFIX_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_BIOFIX, _clear_biofix, schema=CLEAR_BIOFIX_SCHEMA
    )
