"""Interrupteur : avancement automatique du stade, par arbre.

Permet de reprendre la main sans passer par la reconfiguration : si le
modèle de degrés-jours dérive par rapport au verger réel, on le coupe
pour cet arbre et on pilote le stade à la main.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_AUTO_ADVANCE, DOMAIN
from .entity import MeteoSentinelleTreeEntity
from .models.crops import stage_options
from .tree import Tree


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    for subentry_id, tree in coordinator.trees.items():
        if not stage_options(tree.crop):
            continue
        async_add_entities(
            [AutoAdvanceSwitch(coordinator, entry, tree)],
            config_subentry_id=subentry_id,
        )


class AutoAdvanceSwitch(MeteoSentinelleTreeEntity, SwitchEntity):
    """Active ou non l'avancement automatique du stade."""

    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree) -> None:
        super().__init__(coordinator, entry, tree)
        self._attr_unique_id = f"{entry.entry_id}_{tree.subentry_id}_auto_advance"
        self._attr_translation_key = "auto_advance"

    @property
    def is_on(self) -> bool:
        tree = self.tree
        return bool(tree and tree.auto_advance)

    async def _async_set(self, value: bool) -> None:
        """Écrit dans la sous-entrée : le réglage doit survivre au redémarrage."""
        subentry = self._entry.subentries.get(self._subentry_id)
        if subentry is None:
            return
        self.hass.config_entries.async_update_subentry(
            self._entry, subentry, data={**subentry.data, CONF_AUTO_ADVANCE: value}
        )
        tree = self.tree
        if tree is not None:
            tree.auto_advance = value
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
