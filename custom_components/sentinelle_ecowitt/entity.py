"""Base commune des entités : rattachement au bon appareil.

Chaque arbre est un appareil distinct, ce qui règle la question de la
lisibilité : dans n'importe quelle liste Home Assistant, une entité
apparaît sous « Pommier Golden », « Cerisier du fond », etc. Le stade
phénologique d'un arbre n'est donc jamais confondu avec celui d'un
autre, même si l'entité s'appelle « Stade phénologique » pour tous.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .tree import Tree


class SentinelleTreeEntity(CoordinatorEntity):
    """Entité rattachée à un arbre précis."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._subentry_id = tree.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{tree.subentry_id}")},
            name=tree.display_name,
            manufacturer="Sentinelle Ecowitt",
            model=tree.crop_label,
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def tree(self) -> Tree | None:
        return self.coordinator.tree(self._subentry_id)

    @property
    def available(self) -> bool:
        return super().available and self.tree is not None


class SentinelleSiteEntity(CoordinatorEntity):
    """Entité rattachée au site (capteurs partagés, diagnostic)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Sentinelle Ecowitt",
            model="Station et moteur de prédiction",
        )
