"""Base commune des entités : rattachement au bon appareil.

Chaque arbre est un appareil distinct, ce qui règle la question de la
lisibilité : dans n'importe quelle liste Home Assistant, une entité
apparaît sous « Pommier Golden », « Cerisier du fond », etc. Le stade
phénologique d'un arbre n'est donc jamais confondu avec celui d'un
autre, même si l'entité s'appelle « Stade phénologique » pour tous.

Les appareils « arbre » sont rattachés à l'appareil « site » par
`via_device_id`. Home Assistant a déprécié `via_device` (qui désignait
le parent par ses `identifiers`) : ceux-ci ne sont uniques qu'au sein
d'une entrée de configuration et ne désignent plus un appareil unique.
La clé `via_device_id` attend l'identifiant de registre du parent, donc
l'appareil site doit exister **avant** que les plateformes n'ajoutent
leurs entités — d'où `async_ensure_site_device`, appelée au setup.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .tree import Tree

MANUFACTURER = "Météo Sentinelle"
SITE_MODEL = "Station et moteur de prédiction"

#: `via_device_id` n'est apparu dans le TypedDict `DeviceInfo` qu'en
#: Home Assistant 2026.8, alors que hacs.json accepte encore 2026.3. On
#: choisit donc la clé à l'exécution plutôt que d'imposer une montée de
#: version : `via_device_id` dès qu'elle existe, `via_device` avant.
_SUPPORTS_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


@callback
def async_ensure_site_device(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Crée (ou retrouve) l'appareil « site » et renvoie son id de registre.

    Appelée au setup de l'entrée, avant le transfert vers les plateformes :
    `via_device_id` ne peut référencer qu'un appareil déjà enregistré, et
    `select`/`switch` peuvent créer leurs entités d'arbre avant `sensor`.
    """
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=SITE_MODEL,
    )
    return device.id


class MeteoSentinelleTreeEntity(CoordinatorEntity):
    """Entité rattachée à un arbre précis."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, tree: Tree) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._subentry_id = tree.subentry_id
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{tree.subentry_id}")},
            name=tree.display_name,
            manufacturer=MANUFACTURER,
            model=tree.crop_label,
        )
        site_device_id = getattr(coordinator, "site_device_id", None)
        if not _SUPPORTS_VIA_DEVICE_ID:
            device_info["via_device"] = (DOMAIN, entry.entry_id)
        elif site_device_id is not None:
            device_info["via_device_id"] = site_device_id
        self._attr_device_info = device_info

    @property
    def tree(self) -> Tree | None:
        return self.coordinator.tree(self._subentry_id)

    @property
    def available(self) -> bool:
        return super().available and self.tree is not None


class MeteoSentinelleSiteEntity(CoordinatorEntity):
    """Entité rattachée au site (capteurs partagés, diagnostic)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=SITE_MODEL,
        )
