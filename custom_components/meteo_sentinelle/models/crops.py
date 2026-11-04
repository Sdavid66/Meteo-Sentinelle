"""Températures critiques de gel par culture et stade phénologique.

Il n'existe pas *un* seuil de gel : un pommier supporte −25 °C en
dormance et souffre à −2 °C en pleine floraison. Annoncer « il va faire
−2 °C » n'informe pas ; annoncer « −2 °C alors que vos pommiers sont en
pleine floraison » informe.

Les valeurs des espèces fruitières proviennent des tables de
Washington State University (T10 / T90 : températures provoquant
respectivement 10 % et 90 % de mortalité des bourgeons après 30 minutes
d'exposition), reprises et publiées par Utah State University Extension
(IPM-012-11). Elles sont converties des °F d'origine en °C.

Les cultures potagères ne figurent pas dans ces tables : leurs seuils
sont des ordres de grandeur horticoles usuels, explicitement marqués
comme tels (`source="generic"`).
"""
from __future__ import annotations

from dataclasses import dataclass

# (T10, T90) en °C. T90 vaut None quand la source ne la documente pas.
StageThresholds = tuple[float, float | None]

#: Stades de repos : la plante n'est pas en activité, les modèles maladie
#: et ravageurs n'ont rien à évaluer.
#: - « dormant » : bois vivant, seul un froid extrême le menace ;
#: - « off_season » : culture annuelle, rien en terre, plus rien à geler.
DORMANT = "dormant"
OFF_SEASON = "off_season"
REST_STAGES = {DORMANT, OFF_SEASON}


@dataclass(frozen=True)
class Crop:
    """Une culture surveillée."""

    key: str
    label: str
    stages: dict[str, StageThresholds]
    #: Les cultures basses subissent le refroidissement radiatif du sol :
    #: leur risque s'évalue sur la température de surface estimée, pas sur
    #: la température de l'air à 2 m.
    ground_level: bool = False
    source: str = "WSU / USU Extension IPM-012-11"
    #: Stade appliqué pendant le repos hivernal. None : la culture reste
    #: en place l'hiver sans s'arrêter (légumes rustiques) ou n'est pas
    #: connue (culture générique), et continue d'être surveillée.
    rest_stage: str | None = None


_TREE_FRUIT: dict[str, dict[str, StageThresholds]] = {
    "apple": {
        "silver_tip": (-9.4, -16.7),
        "green_tip": (-7.8, -12.2),
        "half_inch_green": (-5.0, -9.4),
        "tight_cluster": (-2.8, -6.1),
        "first_pink": (-2.2, -4.4),
        "full_pink": (-2.2, -3.9),
        "first_bloom": (-2.2, -3.9),
        "full_bloom": (-2.2, -3.9),
    },
    "pear": {
        "swollen_bud": (-9.4, -17.8),
        "bud_burst": (-6.7, -14.4),
        "green_cluster": (-4.4, -9.4),
        "white_bud": (-3.9, -7.2),
        "full_white": (-3.3, -5.6),
        "first_bloom": (-2.8, -5.0),
        "full_bloom": (-2.2, -4.4),
        "petal_fall": (-2.2, -4.4),
    },
    "apricot": {
        "first_swell": (-9.4, None),
        "tip_separation": (-6.7, -17.8),
        "first_white": (-4.4, -10.0),
        "first_bloom": (-3.9, -7.2),
        "full_bloom": (-2.8, -5.6),
        "in_the_shuck": (-2.8, -4.4),
        "shuck_split": (-2.2, -3.9),
    },
    "plum": {
        "swollen_bud": (-10.0, -17.8),
        "side_white": (-8.3, -16.1),
        "green_tip": (-6.7, -13.9),
        "tight_cluster": (-4.4, -8.9),
        "first_white": (-3.3, -5.6),
        "first_bloom": (-2.8, -5.0),
        "full_bloom": (-2.2, -5.0),
        "post_bloom": (-2.2, -5.0),
    },
    "peach": {
        "swollen_bud": (-7.8, -17.2),
        "calyx_green": (-6.1, -15.0),
        "quarter_inch_green": (-5.0, -12.8),
        "pink": (-3.9, -9.4),
        "first_bloom": (-3.3, -6.1),
        "full_bloom": (-2.8, -4.4),
        "post_bloom": (-2.2, -3.9),
    },
    "sweet_cherry": {
        "swollen_bud": (-8.3, -15.0),
        "bud_burst": (-3.9, -10.0),
        "tight_cluster": (-3.3, -8.3),
        "white_bud": (-2.8, -4.4),
        "first_bloom": (-2.2, -3.9),
        "full_bloom": (-2.2, -3.9),
        "post_bloom": (-2.2, -3.9),
    },
}

#: Rusticité du bois en repos (T10, T90). Absente des tables WSU, qui
#: commencent au gonflement : ce sont des ordres de grandeur horticoles,
#: très dépendants de la variété et de l'endurcissement. Ils ne servent
#: qu'à signaler un froid exceptionnel.
_DORMANT_HARDINESS: dict[str, StageThresholds] = {
    "apple": (-25.0, -30.0),
    "pear": (-25.0, -30.0),
    "apricot": (-21.0, -26.0),
    "plum": (-24.0, -29.0),
    "peach": (-19.0, -24.0),
    "sweet_cherry": (-23.0, -28.0),
}

_LABELS = {
    "apple": "Pommier",
    "pear": "Poirier",
    "apricot": "Abricotier",
    "plum": "Prunier",
    "peach": "Pêcher / nectarinier",
    "sweet_cherry": "Cerisier doux",
}

CROPS: dict[str, Crop] = {
    key: Crop(
        key=key,
        label=_LABELS[key],
        stages={DORMANT: _DORMANT_HARDINESS[key], **stages},
        rest_stage=DORMANT,
    )
    for key, stages in _TREE_FRUIT.items()
}

# --- Cultures basses : ordres de grandeur horticoles, pas des tables WSU ---
CROPS["tender_annual"] = Crop(
    key="tender_annual",
    label="Annuelles gélives (tomate, courgette, basilic, haricot)",
    stages={
        "growing": (0.0, -2.0),
    },
    ground_level=True,
    source="generic",
    rest_stage=OFF_SEASON,
)
CROPS["potato"] = Crop(
    key="potato",
    label="Pomme de terre (feuillage)",
    stages={
        "emerged": (-1.0, -3.0),
    },
    ground_level=True,
    source="generic",
    rest_stage=OFF_SEASON,
)
CROPS["hardy_vegetable"] = Crop(
    key="hardy_vegetable",
    label="Légumes rustiques (chou, poireau, épinard)",
    stages={
        "growing": (-6.0, -10.0),
    },
    ground_level=True,
    source="generic",
)
CROPS["vine"] = Crop(
    key="vine",
    label="Vigne",
    stages={
        "dormant": (-15.0, -20.0),
        "bud_swell": (-6.0, -9.0),
        "bud_burst": (-3.0, -5.0),
        "first_leaves": (-1.5, -2.5),
        "shoots_10cm": (-1.0, -2.0),
    },
    source="generic",
    rest_stage=DORMANT,
)

#: Culture générique : conserve le comportement historique (seuils fixes)
#: pour l'utilisateur qui ne veut rien paramétrer.
GENERIC_CROP = "generic"

STAGE_LABELS = {
    # Pommier / poirier / cerisier...
    "silver_tip": "Pointe argentée",
    "green_tip": "Pointe verte",
    "half_inch_green": "Pousse de 1 cm",
    "tight_cluster": "Bouquet serré",
    "first_pink": "Début rose",
    "full_pink": "Pleine floraison rose",
    "first_bloom": "Début floraison",
    "full_bloom": "Pleine floraison",
    "post_bloom": "Après floraison",
    "petal_fall": "Chute des pétales",
    "swollen_bud": "Bourgeon gonflé",
    "bud_burst": "Débourrement",
    "green_cluster": "Bouquet vert",
    "white_bud": "Bouton blanc",
    "full_white": "Plein blanc",
    "first_swell": "Premier gonflement",
    "tip_separation": "Écartement des écailles",
    "first_white": "Début blanc",
    "in_the_shuck": "Jeune fruit engainé",
    "shuck_split": "Sortie de l'engainement",
    "side_white": "Blanc latéral",
    "calyx_green": "Calice vert",
    "quarter_inch_green": "Pousse de 0,5 cm",
    "pink": "Stade rose",
    # Vigne
    "dormant": "Dormance",
    "bud_swell": "Bourgeon gonflé",
    "first_leaves": "Premières feuilles",
    "shoots_10cm": "Rameaux 10 cm",
    # Cultures basses
    "growing": "En végétation",
    "emerged": "Levée effectuée",
    "off_season": "Hors saison",
}


def crop_options() -> list[str]:
    """Clés des cultures pour le config flow, culture générique incluse.

    Ce sont des **clés techniques**, pas des libellés : Home Assistant les
    traduit à l'affichage via la section « selector » de strings.json, en
    fonction de la langue de l'utilisateur. Renvoyer du texte ici le
    figerait dans une seule langue.
    """
    return [GENERIC_CROP] + [crop.key for crop in CROPS.values()]


def stage_options(crop_key: str) -> list[str]:
    """Clés des stades d'une culture, dans l'ordre phénologique."""
    crop = CROPS.get(crop_key)
    if crop is None:
        return []
    if crop.rest_stage and crop.rest_stage not in crop.stages:
        return [crop.rest_stage, *crop.stages]
    return list(crop.stages)


def default_stage(crop_key: str) -> str | None:
    """Stade proposé pour un nouvel arbre : le premier stade d'activité."""
    stages = stage_options(crop_key)
    active = [stage for stage in stages if stage not in REST_STAGES]
    return (active or stages or [None])[0]


def rest_stage(crop_key: str) -> str | None:
    """Stade de repos hivernal d'une culture, si elle en a un."""
    crop = CROPS.get(crop_key)
    return crop.rest_stage if crop else None


def all_stage_keys() -> list[str]:
    """Tous les stades connus, toutes cultures confondues.

    Sert à déclarer les options d'un capteur d'énumération, qui doit
    annoncer l'ensemble des valeurs qu'il peut prendre.
    """
    seen: list[str] = []
    for crop_key in CROPS:
        for stage in stage_options(crop_key):
            if stage not in seen:
                seen.append(stage)
    return seen


def thresholds(crop_key: str, stage_key: str | None) -> StageThresholds | None:
    """(T10, T90) pour une culture et un stade, ou None si inconnu."""
    crop = CROPS.get(crop_key)
    if crop is None:
        return None
    if stage_key in crop.stages:
        return crop.stages[stage_key]
    # Stade absent (culture changée en cours de route) : on prend le stade
    # le plus sensible, choix prudent.
    if crop.stages:
        return max(
            crop.stages.values(),
            key=lambda t: (t[0], t[0] if t[1] is None else t[1]),
        )
    return None


def is_ground_level(crop_key: str) -> bool:
    crop = CROPS.get(crop_key)
    return bool(crop and crop.ground_level)
