"""Entité select : stade phénologique, un par arbre.

Le stade évolue au fil de la saison. Il est avancé automatiquement par
les degrés-jours, mais reste corrigible à la main : l'observation du
verger fait toujours autorité sur un modèle calibré ailleurs.

Les options exposées sont les **clés techniques** des stades
(`full_bloom`, `petal_fall`…). Home Assistant les traduit à l'affichage
selon la langue de l'utilisateur, via la section « entity » de
strings.json. Composer le libellé en Python le figerait en français.

La distinction entre arbres ne passe donc plus par un préfixe d'espèce
dans l'option, mais par le nom de l'appareil : chaque arbre est un
appareil distinct, et `_attr_has_entity_name` fait afficher
« Pommier Golden du fond — Stade phénologique ».
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
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
            [PhenologyStageSelect(coordinator, entry, tree)],
            config_subentry_id=subentry_id,
        )


class PhenologyStageSelect(MeteoSentinelleTreeEntity, SelectEntity):
    """Stade phénologique courant d'un arbre."""

    _attr_icon = "mdi:sprout-outline"
    #: Relie l'entité à « entity.select.phenology_stage » de strings.json,
    #: qui fournit à la fois son nom et le libellé de chaque stade.
    _attr_translation_key = "phenology_stage"

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree) -> None:
        super().__init__(coordinator, entry, tree)
        self._attr_unique_id = f"{entry.entry_id}_{tree.subentry_id}_stage"
        self._attr_options = stage_options(tree.crop)

    @property
    def current_option(self) -> str | None:
        tree = self.tree
        if tree is None or tree.stage is None:
            return None
        return tree.stage if tree.stage in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        if option in self._attr_options:
            await self.coordinator.async_set_stage(self._subentry_id, option)

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
