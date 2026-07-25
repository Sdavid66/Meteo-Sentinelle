"""Intégration Sentinelle Ecowitt."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_PRODUCT,
    ATTR_RAINFAST_MM,
    ATTR_RESIDUAL_DAYS,
    ATTR_TARGET,
    DOMAIN,
    SERVICE_CLEAR_TREATMENT,
    SERVICE_LOG_TREATMENT,
    SERVICE_RESET_MILDEW_INDEX,
    TREATABLE_MODELS,
)
from .coordinator import SentinelleEcowittCoordinator
from .models.treatments import DEFAULT_RAINFAST_MM, DEFAULT_RESIDUAL_DAYS

PLATFORMS = ["sensor", "select"]

LOG_TREATMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TARGET): vol.In(TREATABLE_MODELS),
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
    {vol.Optional(ATTR_TARGET): vol.In(TREATABLE_MODELS)}
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SentinelleEcowittCoordinator(hass, entry)
    await coordinator.async_load_state()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_LOG_TREATMENT,
                SERVICE_CLEAR_TREATMENT,
                SERVICE_RESET_MILDEW_INDEX,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinators(hass: HomeAssistant) -> list[SentinelleEcowittCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


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
            )

    async def _clear_treatment(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_clear_treatment(call.data.get(ATTR_TARGET))

    async def _reset_mildew(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_reset_mildew_index()

    hass.services.async_register(
        DOMAIN, SERVICE_LOG_TREATMENT, _log_treatment, schema=LOG_TREATMENT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_TREATMENT, _clear_treatment, schema=CLEAR_TREATMENT_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_RESET_MILDEW_INDEX, _reset_mildew)
