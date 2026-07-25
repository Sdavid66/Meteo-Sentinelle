"""Entité select : stade phénologique, un par arbre.

Le stade évolue au fil de la saison. Il est avancé automatiquement par
les degrés-jours, mais reste corrigible à la main : l'observation du
verger fait toujours autorité sur un modèle calibré ailleurs.

Les options proposées sont préfixées par l'espèce (« Pommier — Pleine
floraison »), de sorte qu'un stade reste identifiable même sorti de son
contexte : dans une liste d'entités, une carte, ou l'historique.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import SentinelleTreeEntity
from .models.crops import STAGE_LABELS, stage_options
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
            [PhenologyStageSelect(coordinator, entry, tree)],
            config_subentry_id=subentry_id,
        )


class PhenologyStageSelect(SentinelleTreeEntity, SelectEntity):
    """Stade phénologique courant d'un arbre."""

    _attr_icon = "mdi:sprout-outline"

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree) -> None:
        super().__init__(coordinator, entry, tree)
        self._attr_unique_id = f"{entry.entry_id}_{tree.subentry_id}_stage"
        self._attr_name = "Stade phénologique"
        self._crop_label = tree.crop_label
        self._stages = stage_options(tree.crop)
        self._attr_options = [self._decorate(key) for key, _ in self._stages]

    def _decorate(self, stage_key: str) -> str:
        """« Pommier — Pleine floraison » plutôt que « Pleine floraison »."""
        label = STAGE_LABELS.get(stage_key, stage_key)
        return f"{self._crop_label} — {label}"

    def _key_for(self, option: str) -> str | None:
        for key, _ in self._stages:
            if self._decorate(key) == option:
                return key
        return None

    @property
    def current_option(self) -> str | None:
        tree = self.tree
        if tree is None or tree.stage is None:
            return None
        option = self._decorate(tree.stage)
        return option if option in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        key = self._key_for(option)
        if key is not None:
            await self.coordinator.async_set_stage(self._subentry_id, key)

    @property
    def extra_state_attributes(self) -> dict:
        tree = self.tree
        if tree is None:
            return {}
        return {
            "tree": tree.display_name,
            "crop": tree.crop,
            "crop_label": tree.crop_label,
            "stage_key": tree.stage,
            "auto_advance": tree.auto_advance,
            "last_change_automatic": tree.stage_auto_applied,
            "changed_at": (
                tree.stage_changed_at.isoformat() if tree.stage_changed_at else None
            ),
        }
