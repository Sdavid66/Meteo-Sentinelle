"""Tests des modèles ravageurs et des fenêtres de pulvérisation.

Comme les modèles agronomiques, ce sont des fonctions pures : on vérifie
qu'elles reproduisent les seuils publiés sans instancier Home Assistant.

Lancement : python3 tests/test_pests.py
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT / "custom_components" / "meteo_sentinelle"


def _load():
    pkg = types.ModuleType("meteo_sentinelle")
    pkg.__path__ = [str(CC)]
    sys.modules["meteo_sentinelle"] = pkg

    models = types.ModuleType("meteo_sentinelle.models")
    models.__path__ = [str(CC / "models")]
    sys.modules["meteo_sentinelle.models"] = models

    loaded = {}
    for name in ("const", "models.phenology", "models.pests", "models.spray"):
        full = f"meteo_sentinelle.{name}"
        path = CC / (name.replace(".", "/") + ".py")
        spec = importlib.util.spec_from_file_location(full, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


M = _load()
const = M["const"]
phenology = M["models.phenology"]
pests = M["models.pests"]
spray = M["models.spray"]

_checks = 0


def check(condition, label):
    global _checks
    _checks += 1
    if not condition:
        raise AssertionError(f"ÉCHEC : {label}")
    print(f"  ok  {label}")


# ======================================================================
print("\n--- degrés-jours : base et plafond ---")
# ======================================================================

check(
    phenology.daily_gdd(10.0, 20.0, base=10.0) == 5.0,
    "base 10 °C : (10+20)/2 - 10 = 5 °C·j",
)
check(
    phenology.daily_gdd(10.0, 20.0, base=5.0) == 10.0,
    "base 5 °C sur la même journée : 10 °C·j",
)
check(
    phenology.daily_gdd(-5.0, 2.0, base=10.0) == 0.0,
    "une journée froide ne produit jamais de cumul négatif",
)

# Horizontal cutoff : la canicule ne fait plus accélérer le développement.
without_cap = phenology.daily_gdd(20.0, 40.0, base=10.0)
with_cap = phenology.daily_gdd(20.0, 40.0, base=10.0, upper=31.1)
check(without_cap == 20.0, "sans plafond, (20+40)/2 - 10 = 20 °C·j")
check(
    abs(with_cap - 15.55) < 0.01,
    "avec plafond 31,1 °C, la maximale est écrêtée : 15,55 °C·j",
)
check(
    phenology.daily_gdd(35.0, 40.0, base=10.0, upper=31.1) == 21.1,
    "journée entièrement au-dessus du plafond : les deux bornes sont écrêtées",
)


# ======================================================================
print("\n--- cumul : idempotence, saison, complétude ---")
# ======================================================================

days = [(date(2026, 3, day), 5.0, 15.0) for day in range(1, 11)]
state = phenology.accumulate(phenology.GddState(season_year=2026), days, base=10.0)
check(abs(state.total - 0.0) < 0.001, "base 10 °C : dix journées à 10 °C moyens ne cumulent rien")

state = phenology.accumulate(phenology.GddState(season_year=2026), days, base=5.0)
check(abs(state.total - 50.0) < 0.001, "base 5 °C : les mêmes journées cumulent 50 °C·j")

again = phenology.accumulate(state, days, base=5.0)
check(abs(again.total - 50.0) < 0.001, "recompter les mêmes journées ne double pas le cumul")

check(state.first_day == "2026-03-01", "le premier jour compté est mémorisé")
check(
    state.complete_season is False,
    "un cumul démarré en mars ne couvre pas la saison depuis janvier",
)

early = phenology.accumulate(
    phenology.GddState(season_year=2026),
    [(date(2026, 1, 5), 5.0, 15.0)],
    base=5.0,
)
check(early.complete_season is True, "un cumul démarré début janvier couvre la saison")

# Changement d'année : la saison repart de zéro, drapeau compris.
new_year = phenology.accumulate(
    state, [(date(2027, 1, 2), 5.0, 15.0)], base=5.0
)
check(new_year.season_year == 2027, "le passage d'année ouvre une nouvelle saison")
check(abs(new_year.total - 5.0) < 0.001, "la nouvelle saison repart de zéro")
check(new_year.complete_season is True, "et couvre bien le début de la nouvelle saison")


# ======================================================================
print("\n--- carpocapse : seuils UC IPM convertis ---")
# ======================================================================

moth = pests.PESTS[pests.PEST_CODLING_MOTH]
check(moth.base == 10.0 and moth.upper == 31.1, "base 50 °F et plafond 88 °F en °C")
check(moth.origin == pests.ORIGIN_BIOFIX, "le cumul part du biofix, pas du 1er janvier")

thresholds = {stage.key: stage.dd for stage in moth.stages}
check(thresholds["egg_laying"] == 55.6, "100 DD °F = 55,6 °C·j (premières pontes)")
check(thresholds["hatch_start"] == 122.2, "220 DD °F = 122,2 °C·j (début d'éclosion)")
check(thresholds["hatch_peak"] == 138.9, "250 DD °F = 138,9 °C·j (éclosion généralisée)")
check(
    thresholds["second_generation"] == 588.9,
    "1060 DD °F = 588,9 °C·j (seconde génération)",
)

# Sans biofix, aucun niveau n'est calculé : le modèle le dit.
waiting = pests.evaluate_pest_risk(pests.PEST_CODLING_MOTH, 500.0)
check(waiting.awaiting_biofix is True, "sans biofix, le carpocapse annonce son incomplétude")
check(waiting.level == const.RISK_NONE, "et ne prétend à aucun niveau de risque")
check(waiting.cycle_stage is None, "ni à aucun jalon")

with_biofix = pests.evaluate_pest_risk(
    pests.PEST_CODLING_MOTH, 140.0, biofix_date="2026-05-01"
)
check(with_biofix.cycle_stage == "hatch_peak", "140 °C·j après biofix : éclosion généralisée")
check(with_biofix.level == const.RISK_SEVERE, "c'est la fenêtre d'intervention optimale")
check(
    with_biofix.next_cycle_stage == "oviposition_peak",
    "le jalon suivant annoncé est le pic de ponte",
)
check(
    abs(with_biofix.dd_to_next_cycle_stage - 165.6) < 0.01,
    "305,6 - 140 = 165,6 °C·j avant le pic de ponte",
)

# Juste sous un seuil, on reste au jalon précédent.
just_under = pests.evaluate_pest_risk(
    pests.PEST_CODLING_MOTH, 138.8, biofix_date="2026-05-01"
)
check(just_under.cycle_stage == "hatch_start", "un dixième sous le seuil ne fait pas franchir le jalon")


# ======================================================================
print("\n--- mouche de la cerise : 430 °C·j base 5 °C ---")
# ======================================================================

fly = pests.PESTS[pests.PEST_CHERRY_FRUIT_FLY]
check(fly.base == 5.0 and fly.upper is None, "base 5 °C, sans plafond (Boller & Remund)")
check(fly.origin == pests.ORIGIN_SEASON, "le cumul part du 1er janvier, sans observation")

before = pests.evaluate_pest_risk(pests.PEST_CHERRY_FRUIT_FLY, 300.0)
check(
    before.cycle_stage is None and before.level == const.RISK_NONE,
    "300 °C·j : rien encore",
)

approach = pests.evaluate_pest_risk(pests.PEST_CHERRY_FRUIT_FLY, 400.0)
check(approach.cycle_stage == "approach", "400 °C·j : approche de l'émergence")
check(approach.extrapolated is True, "ce jalon est signalé comme extrapolé, pas publié")

emerged = pests.evaluate_pest_risk(pests.PEST_CHERRY_FRUIT_FLY, 430.0)
check(emerged.cycle_stage == "emergence", "430 °C·j exactement : seuil publié atteint")
check(emerged.extrapolated is False, "le seuil publié n'est pas marqué comme extrapolé")
check(emerged.level == const.RISK_WARNING, "l'émergence déclenche une alerte")

partial = pests.evaluate_pest_risk(
    pests.PEST_CHERRY_FRUIT_FLY, 430.0, complete_season=False
)
check(
    partial.incomplete_season is True,
    "un cumul saisonnier partiel est signalé comme sous-estimé",
)
biofix_partial = pests.evaluate_pest_risk(
    pests.PEST_CODLING_MOTH, 140.0, biofix_date="2026-05-01", complete_season=False
)
check(
    biofix_partial.incomplete_season is False,
    "un cumul relatif à un biofix reste juste malgré une saison partielle",
)


# ======================================================================
print("\n--- doryphore et tordeuse ---")
# ======================================================================

beetle = pests.PESTS[pests.PEST_COLORADO_POTATO_BEETLE]
beetle_thresholds = {stage.key: stage.dd for stage in beetle.stages}
check(beetle_thresholds["instar_1"] == 102.8, "185 DD °F = 102,8 °C·j (larve L1)")
check(beetle_thresholds["pupation"] == 375.0, "675 DD °F = 375,0 °C·j (nymphose)")

l2 = pests.evaluate_pest_risk(
    pests.PEST_COLORADO_POTATO_BEETLE, 140.0, biofix_date="2026-05-20"
)
check(l2.cycle_stage == "instar_2", "140 °C·j après les premières pontes : stade L2")
check(l2.level == const.RISK_SEVERE, "L2 est la fenêtre d'intervention la plus efficace")

late = pests.evaluate_pest_risk(
    pests.PEST_COLORADO_POTATO_BEETLE, 400.0, biofix_date="2026-05-20"
)
check(late.cycle_stage == "pupation", "400 °C·j : nymphose")
check(
    late.level == const.RISK_NONE,
    "à la nymphose l'intervention n'a plus d'intérêt : niveau nul",
)

lobesia = pests.evaluate_pest_risk(pests.PEST_GRAPEVINE_MOTH, 300.0)
check(lobesia.cycle_stage == "first_flight", "300 °C·j base 7 : premier vol en cours")
check(lobesia.level == const.RISK_WARNING, "un vol en cours justifie une alerte")
between = pests.evaluate_pest_risk(pests.PEST_GRAPEVINE_MOTH, 600.0)
check(between.cycle_stage == "first_generation", "600 °C·j : entre deux vols")
check(between.level == const.RISK_WATCH, "hors vol, le niveau retombe à la vigilance")


# ======================================================================
print("\n--- cohérence des définitions ---")
# ======================================================================

for key, pest in pests.PESTS.items():
    dds = [stage.dd for stage in pest.stages]
    check(dds == sorted(dds), f"{key} : les jalons sont ordonnés par cumul croissant")
    check(
        all(stage.level in const.RISK_LEVELS for stage in pest.stages),
        f"{key} : tous les niveaux sont des niveaux connus",
    )
    check(bool(pest.source), f"{key} : la source est renseignée")

check(
    set(pests.PESTS) == set(const.PEST_MODELS),
    "const.PEST_MODELS et models.pests.PESTS décrivent le même ensemble",
)
for crop, models in const.CROP_PEST_MODELS.items():
    check(
        all(model in pests.PESTS for model in models),
        f"{crop} : les ravageurs associés existent tous",
    )

# Le regroupement par barème évite de cumuler deux fois la même série.
accumulators = pests.required_accumulators()
check(
    len(accumulators) == 4,
    "quatre ravageurs, quatre barèmes : carpocapse et doryphore partagent la "
    "base 10 °C mais pas le plafond, donc pas le cumulateur",
)
check(
    pests.accumulator_key(pests.PESTS[pests.PEST_CODLING_MOTH])
    != pests.accumulator_key(pests.PESTS[pests.PEST_COLORADO_POTATO_BEETLE]),
    "le plafond fait bien partie de l'identité du barème",
)


# ======================================================================
print("\n--- fenêtres de pulvérisation ---")
# ======================================================================

BASE = datetime(2026, 6, 1, 6, 0)


def hours(count, wind=5.0, rain=0.0, temp=18.0, start=0):
    return [
        spray.ForecastHour(
            time=BASE + timedelta(hours=start + i),
            temperature=temp,
            wind_speed=wind,
            precipitation=rain,
        )
        for i in range(count)
    ]


calm = hours(12)
advice = spray.find_spray_windows(calm, now=BASE)
check(advice.current is not None, "douze heures calmes et sèches : créneau ouvert")
check(
    advice.current.start == BASE,
    "le créneau démarre à la première heure favorable",
)

windy = hours(12, wind=35.0)
advice = spray.find_spray_windows(windy, now=BASE)
check(advice.current is None, "vent à 35 km/h : aucun créneau")
check("wind" in advice.blocking, "et la raison donnée est le vent")

# Le seuil réglementaire est bien à 19 km/h.
check(
    spray.find_spray_windows(hours(6, wind=18.0), now=BASE).current is not None,
    "18 km/h reste sous le seuil de 19 km/h",
)
check(
    spray.find_spray_windows(hours(6, wind=20.0), now=BASE).current is None,
    "20 km/h le dépasse",
)

rainy = hours(12, rain=1.0)
advice = spray.find_spray_windows(rainy, now=BASE)
check(advice.current is None, "pluie continue : aucun créneau")
check("rain" in advice.blocking, "et la raison donnée est la pluie")

cold = hours(12, temp=1.0)
advice = spray.find_spray_windows(cold, now=BASE)
check("temperature" in advice.blocking, "1 °C : hors de la plage utile")

# Une averse en fin de fenêtre invalide les heures qui la précèdent,
# à hauteur du délai de résistance au lavage.
mixed = hours(6) + hours(4, rain=2.0, start=6)
advice = spray.find_spray_windows(mixed, now=BASE, rainfast_hours=2)
check(
    advice.current is not None and advice.current.hours == 4,
    "avec 2 h de rémanence, les deux heures précédant l'averse sont écartées",
)

# Une donnée manquante n'est jamais interprétée comme favorable.
unknown_wind = [
    spray.ForecastHour(time=BASE + timedelta(hours=i), temperature=18.0, precipitation=0.0)
    for i in range(6)
]
advice = spray.find_spray_windows(unknown_wind, now=BASE)
check(advice.current is None, "vent inconnu : on ne propose pas de créneau")
check("wind_unknown" in advice.blocking, "et on dit que c'est le vent qui manque")

# Un créneau trop court n'est pas proposé.
short = hours(1) + hours(5, wind=40.0, start=1)
advice = spray.find_spray_windows(short, now=BASE, min_window_hours=2)
check(advice.current is None, "une heure isolée ne fait pas un créneau exploitable")

# Créneau à venir plutôt qu'en cours.
later = hours(3, wind=40.0) + hours(5, start=3)
advice = spray.find_spray_windows(later, now=BASE)
check(advice.current is None, "les premières heures sont trop ventées")
check(
    advice.upcoming is not None and advice.upcoming.start == BASE + timedelta(hours=3),
    "le prochain créneau annoncé démarre à la quatrième heure",
)

advice = spray.find_spray_windows([], now=BASE)
check(advice.current is None and "no_forecast" in advice.blocking,
      "sans prévision, le modèle le dit au lieu de conclure")


print(f"\n{_checks} vérifications passées.")
