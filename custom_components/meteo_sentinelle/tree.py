"""Représentation d'un arbre (ou d'une culture) surveillé.

Chaque arbre correspond à une **sous-entrée** de la configuration, et
donc à un appareil distinct dans Home Assistant. Il porte son espèce,
son stade phénologique courant, et l'état qui lui est propre : indice
oïdium, traitements, historique d'avancement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .const import (
    CONF_AUTO_ADVANCE,
    CONF_CROP,
    CONF_GDD_OFFSET,
    CONF_STAGE,
    CONF_TREE_NAME,
    CROP_DISEASE_MODELS,
    CROP_PEST_MODELS,
    DEFAULT_AUTO_ADVANCE,
    DEFAULT_GDD_OFFSET,
    MODEL_FROST,
)
from .models.crops import CROPS, GENERIC_CROP, STAGE_LABELS


@dataclass
class Tree:
    """Un arbre surveillé, tel que configuré par l'utilisateur."""

    subentry_id: str
    name: str
    crop: str
    stage: str | None = None
    auto_advance: bool = DEFAULT_AUTO_ADVANCE
    gdd_offset: float = DEFAULT_GDD_OFFSET

    # --- État dérivé, rafraîchi à chaque cycle ---
    stage_auto_applied: bool = False
    stage_changed_at: datetime | None = None
    bloom_date: datetime | None = None
    #: Indice Gubler-Thomas propre à cet arbre.
    mildew_index: int = 0
    mildew_started: bool = False
    mildew_last_day: str | None = None
    #: Dernier niveau connu par modèle, pour ne notifier qu'aux changements.
    last_levels: dict[str, str] = field(default_factory=dict)
    #: Biofix par ravageur : {modèle: {"date", "gdd", "estimated"}}.
    #: `gdd` mémorise le cumul saisonnier au moment du biofix, ce qui
    #: permet d'en déduire le cumul depuis le biofix par simple
    #: soustraction, sans jamais relire l'historique.
    biofix: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_subentry(cls, subentry_id: str, data: dict) -> "Tree":
        crop = data.get(CONF_CROP, GENERIC_CROP)
        return cls(
            subentry_id=subentry_id,
            name=data.get(CONF_TREE_NAME) or crop_label(crop),
            crop=crop,
            stage=data.get(CONF_STAGE),
            auto_advance=bool(data.get(CONF_AUTO_ADVANCE, DEFAULT_AUTO_ADVANCE)),
            gdd_offset=float(data.get(CONF_GDD_OFFSET, DEFAULT_GDD_OFFSET)),
        )

    # --- Persistance de l'état volatil ---

    def state_dict(self) -> dict:
        return {
            "stage": self.stage,
            "stage_auto_applied": self.stage_auto_applied,
            "stage_changed_at": (
                self.stage_changed_at.isoformat() if self.stage_changed_at else None
            ),
            "bloom_date": self.bloom_date.isoformat() if self.bloom_date else None,
            "mildew_index": self.mildew_index,
            "mildew_started": self.mildew_started,
            "mildew_last_day": self.mildew_last_day,
            "last_levels": dict(self.last_levels),
            "biofix": {key: dict(value) for key, value in self.biofix.items()},
        }

    def restore_state(self, data: dict) -> None:
        if not data:
            return
        # Le stade mémorisé prime : il peut avoir été corrigé à la main
        # ou avancé automatiquement depuis la configuration initiale.
        if data.get("stage"):
            self.stage = data["stage"]
        self.stage_auto_applied = bool(data.get("stage_auto_applied", False))
        self.stage_changed_at = _parse(data.get("stage_changed_at"))
        self.bloom_date = _parse(data.get("bloom_date"))
        self.mildew_index = int(data.get("mildew_index", 0))
        self.mildew_started = bool(data.get("mildew_started", False))
        self.mildew_last_day = data.get("mildew_last_day")
        self.last_levels = dict(data.get("last_levels") or {})
        self.biofix = {
            key: dict(value)
            for key, value in (data.get("biofix") or {}).items()
            if isinstance(value, dict)
        }

    # --- Présentation ---

    @property
    def crop_label(self) -> str:
        return crop_label(self.crop)

    @property
    def stage_label(self) -> str | None:
        if self.stage is None:
            return None
        return STAGE_LABELS.get(self.stage, self.stage)

    @property
    def display_name(self) -> str:
        """Nom lisible incluant l'espèce, pour distinguer les arbres.

        Si l'utilisateur a nommé son arbre « Golden », l'appareil
        s'appelle « Pommier Golden » : dans une liste de stades
        phénologiques, on voit immédiatement de quelle espèce il s'agit.
        """
        if self.name.lower().startswith(self.crop_label.lower()):
            return self.name
        return f"{self.crop_label} {self.name}".strip()

    @property
    def models(self) -> list[str]:
        """Modèles pertinents : le gel, les maladies et les ravageurs de l'espèce."""
        return (
            [MODEL_FROST]
            + list(CROP_DISEASE_MODELS.get(self.crop, []))
            + list(CROP_PEST_MODELS.get(self.crop, []))
        )

    @property
    def pests(self) -> list[str]:
        """Ravageurs suivis pour cette espèce."""
        return list(CROP_PEST_MODELS.get(self.crop, []))

    def slug(self) -> str:
        return self.subentry_id


def legacy_tree_data(entry_data: dict) -> dict:
    """Convertit une configuration mono-culture (v1 à v3) en données d'arbre.

    Jusqu'à la v0.3, l'entrée de configuration portait directement une
    culture et un stade. Depuis la v0.4, chaque arbre est une sous-entrée.
    Cette fonction fabrique les données de l'arbre correspondant, afin
    qu'une installation existante retrouve ses capteurs après migration
    plutôt que de repartir de zéro.
    """
    crop = entry_data.get(CONF_CROP) or GENERIC_CROP
    data = {
        CONF_TREE_NAME: crop_label(crop),
        CONF_CROP: crop,
        CONF_AUTO_ADVANCE: DEFAULT_AUTO_ADVANCE,
        CONF_GDD_OFFSET: DEFAULT_GDD_OFFSET,
    }
    stage = entry_data.get(CONF_STAGE)
    if stage:
        data[CONF_STAGE] = stage
    return data


def strip_legacy_keys(entry_data: dict) -> dict:
    """Retire de l'entrée les clés désormais portées par les sous-entrées."""
    return {
        key: value
        for key, value in entry_data.items()
        if key not in (CONF_CROP, CONF_STAGE)
    }


def match_trees(trees: dict[str, "Tree"], requested) -> list[str] | None:
    """Traduit un nom ou un identifiant d'arbre en identifiants de sous-entrée.

    Renvoie None si rien n'est demandé (= tous les arbres). Le rapprochement
    est volontairement tolérant : le nom saisi dans un service ou dicté à
    Assist correspond rarement au caractère près à celui de l'appareil.
    Trois formes sont acceptées — l'identifiant technique, le nom donné
    par l'utilisateur (« Golden »), et le nom affiché (« Pommier
    Golden ») — puis, à défaut, une correspondance par inclusion.
    """
    if requested is None:
        return None
    names = [requested] if isinstance(requested, str) else list(requested)
    wanted = {name.strip().casefold() for name in names if name}
    wanted.discard("")
    if not wanted:
        return None

    matched: list[str] = []
    for subentry_id, tree in trees.items():
        candidates = {
            subentry_id.casefold(),
            tree.name.casefold(),
            tree.display_name.casefold(),
        }
        if candidates & wanted:
            matched.append(subentry_id)

    if matched:
        return matched

    # Repli par inclusion : « le pommier » doit retrouver « Pommier
    # Golden du fond » sans que l'utilisateur ait à le nommer en entier.
    for subentry_id, tree in trees.items():
        haystack = f"{tree.display_name} {tree.name}".casefold()
        if any(word and (word in haystack or haystack in word) for word in wanted):
            matched.append(subentry_id)
    return matched


def crop_label(crop: str) -> str:
    entry = CROPS.get(crop)
    return entry.label if entry else "Culture"


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
