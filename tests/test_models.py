"""Tests des modèles agronomiques, exécutables sans Home Assistant.

Les modèles sont des fonctions pures : on peut donc vérifier qu'ils
reproduisent bien les critères publiés (Hutton, Smith, Gubler-Thomas,
tables T10/T90) sans instancier Home Assistant.

Lancement : python3 tests/test_models.py
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT / "custom_components" / "meteo_sentinelle"


def _load():
    """Charge les modules modèles en simulant le package, sans HA."""
    pkg = types.ModuleType("meteo_sentinelle")
    pkg.__path__ = [str(CC)]
    sys.modules["meteo_sentinelle"] = pkg

    models = types.ModuleType("meteo_sentinelle.models")
    models.__path__ = [str(CC / "models")]
    sys.modules["meteo_sentinelle.models"] = models

    loaded = {}
    for name in ("const", "models.hourly", "models.crops", "models.frost",
                 "models.late_blight", "models.powdery_mildew",
                 "models.treatments", "models.phenology", "tree"):
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
hourly = M["models.hourly"]
crops = M["models.crops"]
frost = M["models.frost"]
blight = M["models.late_blight"]
mildew = M["models.powdery_mildew"]
treatments = M["models.treatments"]
phenology = M["models.phenology"]
tree_mod = M["tree"]

BASE = datetime(2026, 6, 1, 0, 0)
_checks = 0


def check(condition, label):
    global _checks
    _checks += 1
    if not condition:
        raise AssertionError(f"ÉCHEC : {label}")
    print(f"  ok  {label}")


def make_day(day_offset, temp_profile, humidity_profile, rain=None):
    """Construit 24 HourlySample. Les profils sont des listes de 24 valeurs."""
    samples = []
    for hour in range(24):
        samples.append(
            hourly.HourlySample(
                time=BASE + timedelta(days=day_offset, hours=hour),
                temp=temp_profile[hour],
                humidity=humidity_profile[hour],
                rain_mm=(rain[hour] if rain else 0.0),
            )
        )
    return samples


def flat(value):
    return [value] * 24


def wet_for(hours, wet=95.0, dry=60.0, start=0):
    """Profil d'humidité avec `hours` heures consécutives humides."""
    profile = [dry] * 24
    for h in range(start, min(start + hours, 24)):
        profile[h] = wet
    return profile


# ======================================================================
print("\n--- hourly : primitives ---")
# ======================================================================

samples = make_day(0, flat(15.0), wet_for(8))
check(hourly.longest_run(samples, lambda s: hourly.is_wet(s)) == 8,
      "longest_run compte 8 heures humides consécutives")

split = wet_for(4, start=0)
for h in range(6, 11):
    split[h] = 95.0
samples_split = make_day(0, flat(15.0), split)
check(hourly.longest_run(samples_split, lambda s: hourly.is_wet(s)) == 5,
      "longest_run ne cumule pas deux séries séparées (5, pas 9)")
check(hourly.count_hours(samples_split, lambda s: hourly.is_wet(s)) == 9,
      "count_hours cumule bien les heures non consécutives (9)")

# Rééchantillonnage : plusieurs relevés dans la même heure -> moyenne
raw = [
    {"time": BASE + timedelta(minutes=5), "temp": 10.0},
    {"time": BASE + timedelta(minutes=35), "temp": 12.0},
    {"time": BASE + timedelta(hours=1, minutes=5), "temp": 20.0},
]
res = hourly.resample_hourly(raw)
check(len(res) == 2, "resample_hourly agrège en 2 heures")
check(abs(res[0].temp - 11.0) < 1e-9, "resample_hourly moyenne 10 et 12 -> 11")

# Réponse thermique : nulle hors bornes, maximale à l'optimum
check(hourly.beta_response(2.0, 3.0, 20.0, 30.0) == 0.0,
      "beta_response nulle sous la température minimale")
check(hourly.beta_response(31.0, 3.0, 20.0, 30.0) == 0.0,
      "beta_response nulle au-dessus de la maximale")
check(abs(hourly.beta_response(20.0, 3.0, 20.0, 30.0) - 1.0) < 1e-6,
      "beta_response vaut 1 à l'optimum")
check(hourly.beta_response(11.0, 3.0, 20.0, 30.0)
      < hourly.beta_response(19.0, 3.0, 20.0, 30.0),
      "beta_response distingue 11 °C de 19 °C (ce qu'un seuil ne fait pas)")

# ======================================================================
print("\n--- mildiou : Hutton vs Smith ---")
# ======================================================================

# 2 jours à 7 h humides, T min 12 °C : Hutton OUI (>=6 h), Smith NON (<11 h).
two_days = []
for d in range(2):
    two_days += make_day(d, flat(12.0), wet_for(7))
r = blight.evaluate_late_blight_risk(two_days)
check(r.hutton_met is True, "Hutton déclenché à 7 h d'humidité sur 2 jours")
check(r.smith_met is False, "Smith non déclenché à 7 h (il en exige 11)")
check(r.level == const.RISK_SEVERE, "niveau severe piloté par Hutton")

# C'est précisément le cas que Smith manquait :
check(r.hutton_met and not r.smith_met,
      "cas de sous-détection de Smith correctement capturé")

# 2 jours à 12 h humides : les deux critères sont remplis.
wet_days = []
for d in range(2):
    wet_days += make_day(d, flat(12.0), wet_for(12))
r2 = blight.evaluate_late_blight_risk(wet_days)
check(r2.hutton_met and r2.smith_met, "12 h d'humidité : Hutton et Smith remplis")

# Température trop basse : aucun critère, même très humide.
cold = []
for d in range(3):
    cold += make_day(d, flat(8.0), flat(98.0))
r3 = blight.evaluate_late_blight_risk(cold)
check(r3.hutton_met is False and r3.level == const.RISK_NONE,
      "T min 8 °C : pas de risque malgré 100 % d'humidité")

# Une seule journée favorable -> pas severe
one_day = make_day(0, flat(12.0), wet_for(7)) + make_day(1, flat(12.0), flat(50.0))
r4 = blight.evaluate_late_blight_risk(one_day)
check(r4.hutton_consecutive_days == 1, "une seule journée favorable détectée")
check(r4.level in (const.RISK_WATCH, const.RISK_WARNING),
      "une journée favorable ne donne pas severe")

# Deux jours favorables non consécutifs -> pas de période
gap = (make_day(0, flat(12.0), wet_for(7))
       + make_day(1, flat(12.0), flat(50.0))
       + make_day(2, flat(12.0), wet_for(7)))
r5 = blight.evaluate_late_blight_risk(gap)
check(r5.hutton_met is False,
      "deux journées favorables séparées ne forment pas une période")
check(r5.favourable_days == 2, "les deux journées favorables sont comptées")

check(blight.evaluate_late_blight_risk([]).level == const.RISK_NONE,
      "série vide : aucun risque, pas d'erreur")

# Journée incomplète ignorée (évite un faux négatif de bord d'historique)
partial = make_day(0, flat(12.0), wet_for(7))[:10]
check(blight.evaluate_late_blight_risk(partial).evaluated_days == 0,
      "journée trop partielle écartée de l'évaluation")

# Le capteur d'humectation foliaire prime sur l'humidité relative
leafy = make_day(0, flat(12.0), flat(40.0))
for s in leafy[:8]:
    s.leaf_wet = True
leafy2 = make_day(1, flat(12.0), flat(40.0))
for s in leafy2[:8]:
    s.leaf_wet = True
r6 = blight.evaluate_late_blight_risk(leafy + leafy2)
check(r6.hutton_met is True,
      "humectation foliaire prise en compte même à 40 % d'HR")

# ======================================================================
print("\n--- oïdium : indice Gubler-Thomas ---")
# ======================================================================

def optimal_day(offset, hours=8, rain=None, peak=None):
    """Journée avec `hours` heures continues dans 21,1-29,4 °C."""
    temps = [15.0] * 24
    for h in range(hours):
        temps[h] = 25.0
    if peak is not None:
        temps[20] = peak
    return make_day(offset, temps, flat(50.0), rain)

# Phase d'initiation : 3 journées consécutives -> 60, épidémie lancée
init = []
for d in range(3):
    init += optimal_day(d)
r = mildew.evaluate_powdery_mildew_risk(init)
check(r.index == 60, f"3 journées optimales -> indice 60 (obtenu {r.index})")
check(r.epidemic_started is True, "épidémie déclarée lancée à 60")

# Une journée manquée pendant l'initiation remet à zéro
broken = optimal_day(0) + make_day(1, flat(15.0), flat(50.0)) + optimal_day(2)
r = mildew.evaluate_powdery_mildew_risk(broken)
check(r.index == 20, f"remise à zéro puis +20 -> 20 (obtenu {r.index})")
check(r.epidemic_started is False, "épidémie non lancée si l'initiation est cassée")

# Phase de suivi : +20 par journée favorable
r = mildew.evaluate_powdery_mildew_risk(
    optimal_day(10), index=60, epidemic_started=True)
check(r.index == 80, f"suivi : +20 -> 80 (obtenu {r.index})")

# Journée défavorable : -10
r = mildew.evaluate_powdery_mildew_risk(
    make_day(10, flat(15.0), flat(50.0)), index=60, epidemic_started=True)
check(r.index == 50, f"journée défavorable : -10 -> 50 (obtenu {r.index})")

# Pic léthal seul (>=35 °C) : -10
hot = make_day(10, flat(15.0), flat(50.0))
hot[20].temp = 36.0
r = mildew.evaluate_powdery_mildew_risk(hot, index=60, epidemic_started=True)
check(r.index == 50, f"pic à 36 °C : -10 -> 50 (obtenu {r.index})")

# Plage favorable ET pic léthal : +10 net
r = mildew.evaluate_powdery_mildew_risk(
    optimal_day(10, peak=36.0), index=60, epidemic_started=True)
check(r.index == 70, f"favorable + pic léthal : +10 -> 70 (obtenu {r.index})")

# Bornes 0 et 100
r = mildew.evaluate_powdery_mildew_risk(
    optimal_day(10), index=95, epidemic_started=True)
check(r.index == 100, "indice plafonné à 100")
r = mildew.evaluate_powdery_mildew_risk(
    make_day(10, flat(15.0), flat(50.0)), index=5, epidemic_started=True)
check(r.index == 0, "indice plancher à 0")

# Correction pluie : l'eau libre inhibe l'oïdium
rainy = [0.0] * 24
rainy[12] = 4.0
r_rain = mildew.evaluate_powdery_mildew_risk(
    optimal_day(10, rain=rainy), index=60, epidemic_started=True,
    apply_rain_penalty=True)
r_dry = mildew.evaluate_powdery_mildew_risk(
    optimal_day(10), index=60, epidemic_started=True, apply_rain_penalty=True)
check(r_rain.index < r_dry.index,
      f"pluie pénalise l'indice ({r_rain.index} < {r_dry.index})")
check(r_rain.index == 70, f"4 mm de pluie : +20-10 -> 70 (obtenu {r_rain.index})")

# La pénalité est désactivable
r_off = mildew.evaluate_powdery_mildew_risk(
    optimal_day(10, rain=rainy), index=60, epidemic_started=True,
    apply_rain_penalty=False)
check(r_off.index == 80, "pénalité pluie désactivable")

# Idempotence : une journée déjà intégrée n'est pas recomptée
day = optimal_day(10)
first = mildew.evaluate_powdery_mildew_risk(day, index=60, epidemic_started=True)
second = mildew.evaluate_powdery_mildew_risk(
    day, index=first.index, epidemic_started=True,
    last_processed_day=first.last_processed_day)
check(second.index == first.index,
      "journée déjà traitée non recomptée (indice cumulatif stable)")

# Bandes de risque
check(mildew.risk_level(20, True) == const.RISK_NONE, "indice 20 -> aucun risque")
check(mildew.risk_level(50, True) == const.RISK_WATCH, "indice 50 -> à surveiller")
check(mildew.risk_level(70, True) == const.RISK_WARNING, "indice 70 -> alerte")
check(mildew.risk_level(90, True) == const.RISK_SEVERE, "indice 90 -> sévère")
check(mildew.spray_interval(80) == 14, "indice > 60 -> intervalle 14 jours")
check(mildew.spray_interval(30) == 21, "indice bas -> intervalle 21 jours")

# ======================================================================
print("\n--- gel : seuils phénologiques ---")
# ======================================================================

def fc(temps, start=20):
    return [(BASE + timedelta(hours=start + i), t) for i, t in enumerate(temps)]

# Table WSU : pommier en pleine floraison, T10 = -2,2 / T90 = -3,9
t10, t90 = crops.thresholds("apple", "full_bloom")
check(abs(t10 - (-2.2)) < 0.05 and abs(t90 - (-3.9)) < 0.05,
      "table WSU pommier pleine floraison : T10 -2,2 / T90 -3,9 °C")

# Le même -3 °C : anodin en dormance, grave en floraison
cold = fc([2, 0, -3, -1])
dormant = frost.evaluate_frost_risk(3, 70, 15, 80, cold, "apple", "silver_tip")
bloom = frost.evaluate_frost_risk(3, 70, 15, 80, cold, "apple", "full_bloom")
check(dormant.level == const.RISK_NONE,
      "-3 °C sans risque au stade pointe argentée (T10 -9,4 °C)")
check(bloom.level == const.RISK_WARNING,
      "-3 °C en alerte en pleine floraison (sous T10)")
check(dormant.level != bloom.level,
      "le stade change le diagnostic à température identique")

# Sous T90 : perte massive
severe = frost.evaluate_frost_risk(3, 70, 15, 80, fc([0, -5, -2]),
                                   "apple", "full_bloom")
check(severe.level == const.RISK_SEVERE, "-5 °C en floraison : perte massive")
check(severe.expected_damage == "severe_loss", "dégâts qualifiés de massifs")

# Juste au-dessus de T10 : vigilance
near = frost.evaluate_frost_risk(3, 70, 15, 80, fc([1, -1, 0]),
                                 "apple", "full_bloom")
check(near.level == const.RISK_WATCH, "-1 °C en floraison : vigilance")

# Refroidissement radiatif : ciel dégagé + vent nul
clear_calm = frost.radiative_offset(0, 0)
overcast_windy = frost.radiative_offset(100, 30)
check(abs(clear_calm - 5.0) < 1e-9, "ciel dégagé, vent nul : écart de 5 °C")
check(overcast_windy == 0.0, "ciel couvert et vent fort : écart nul")
check(frost.radiative_offset(0, 10) < clear_calm, "le vent réduit l'écart")

# Gelée blanche : +2 °C dans l'air, mais 0 °C au sol
ground = frost.evaluate_frost_risk(4, 80, 0, 0, fc([5, 3, 2]),
                                   "tender_annual", "growing")
check(ground.reference == "surface",
      "culture basse évaluée sur la température de surface")
check(ground.air_min == 2 and ground.surface_min is not None
      and ground.surface_min < 0,
      f"air +2 °C mais surface {ground.surface_min} °C")
check(ground.level != const.RISK_NONE,
      "gelée blanche détectée alors que l'air reste positif")

# Un arbre au même moment est jugé sur l'air, pas sur le sol
tree = frost.evaluate_frost_risk(4, 80, 0, 0, fc([5, 3, 2]),
                                 "apple", "full_bloom")
check(tree.reference == "air", "arbre évalué sur la température de l'air")

# Culture générique : comportement historique conservé
generic = frost.evaluate_frost_risk(4, 70, 20, 90, fc([5, 3, 1, -3, -5]))
check(generic.level == const.RISK_SEVERE, "culture générique : seuils fixes")
check(generic.t10 is None, "culture générique : pas de seuil phénologique")

# Robustesse : aucune donnée
empty = frost.evaluate_frost_risk(None, None, None, None, [])
check(empty.level == const.RISK_NONE, "absence totale de données : pas d'erreur")

# Point de rosée cohérent (saturation -> point de rosée = température)
check(abs(frost.dew_point(20.0, 100.0) - 20.0) < 0.3,
      "point de rosée à 100 % d'HR ≈ température de l'air")
check(frost.dew_point(20.0, 50.0) < 20.0, "point de rosée < température si HR < 100 %")

# Stade inconnu : on retient le stade le plus sensible (choix prudent)
unknown = crops.thresholds("apple", "stade_inexistant")
check(unknown == min(crops.CROPS["apple"].stages.values(), key=lambda t: t[0]),
      "stade inconnu : repli sur le stade le plus sensible")

# ======================================================================
print("\n--- traitements : protégé jusqu'à ---")
# ======================================================================

now = datetime(2026, 6, 10, 12, 0)
t = treatments.Treatment(target="late_blight", product="Bouillie",
                         applied_at=now - timedelta(days=2),
                         residual_days=7, rainfast_mm=20)
check(t.is_active(now), "traitement de 7 j appliqué il y a 2 j : actif")
check(abs(t.remaining_hours(now) - 120) < 1e-6, "120 h de protection restantes")

expired = treatments.Treatment(target="late_blight", product="X",
                               applied_at=now - timedelta(days=10),
                               residual_days=7)
check(not expired.is_active(now), "rémanence écoulée : protection terminée")
check(expired.status(now) == "expired", "statut « expired »")

washed = treatments.Treatment(target="late_blight", product="X",
                              applied_at=now - timedelta(days=1),
                              residual_days=7, rainfast_mm=20)
washed.add_rain(25)
check(washed.washed_off, "25 mm > 20 mm : produit lessivé")
check(not washed.is_active(now), "lessivage annule la protection avant l'échéance")
check(washed.status(now) == "washed_off", "statut « washed_off »")

no_wash = treatments.Treatment(target="x", product="y", applied_at=now,
                               residual_days=7, rainfast_mm=0)
no_wash.add_rain(200)
check(not no_wash.washed_off, "rainfast_mm = 0 désactive le lessivage")

# Rétrogradation du niveau sous protection
check(treatments.adjusted_level(const.RISK_SEVERE, t, now) == const.RISK_WARNING,
      "sous protection, severe rétrogradé en warning")
check(treatments.adjusted_level(const.RISK_WARNING, t, now) == const.RISK_WATCH,
      "sous protection, warning rétrogradé en watch")
check(treatments.adjusted_level(const.RISK_SEVERE, None, now) == const.RISK_SEVERE,
      "sans traitement, le niveau est inchangé")
check(treatments.adjusted_level(const.RISK_SEVERE, expired, now) == const.RISK_SEVERE,
      "traitement expiré : plus de rétrogradation")
check(treatments.adjusted_level(const.RISK_WATCH, t, now) == const.RISK_WATCH,
      "la rétrogradation ne descend jamais sous watch")

state = treatments.protection_state(t, now)
check(state["status"] == "protected", "état exposé : protected")
check(state["protected_until"] is not None, "échéance « protégé jusqu'à » fournie")
check(treatments.protection_state(None, now)["status"] == "none",
      "aucun traitement : statut none")

# Aller-retour de sérialisation (persistance entre redémarrages)
restored = treatments.Treatment.from_dict(t.to_dict())
check(restored is not None and restored.applied_at == t.applied_at,
      "sérialisation/désérialisation fidèle")
check(treatments.Treatment.from_dict({"bogus": 1}) is None,
      "données corrompues : rejet propre sans exception")

# ======================================================================
print("\n--- phénologie : degrés-jours et avancement de stade ---")
# ======================================================================

from datetime import date as _date

# Formule des degrés-jours (base 5,6 °C)
check(abs(phenology.daily_gdd(5.0, 15.0) - (10.0 - 5.6)) < 1e-9,
      "GDD = moyenne - base (10 - 5,6 = 4,4)")
check(phenology.daily_gdd(-5.0, 2.0) == 0.0,
      "journée froide : GDD nul, jamais négatif")
check(phenology.daily_gdd(None, 12.0) == 0.0,
      "donnée manquante : GDD nul plutôt qu'erreur")

# Cumul idempotent
state = phenology.GddState(season_year=2026)
days = [(_date(2026, 3, d), 5.0, 15.0) for d in range(1, 11)]
state = phenology.accumulate(state, days)
check(abs(state.total - 44.0) < 1e-6, f"10 jours à 4,4 GDD = 44 (obtenu {state.total})")
again = phenology.accumulate(state, days)
check(abs(again.total - state.total) < 1e-9,
      "journées déjà comptées non recomptées (cumul idempotent)")

# Nouvelle saison : remise à zéro au changement d'année
next_season = phenology.accumulate(state, [(_date(2027, 1, 5), 5.0, 15.0)])
check(next_season.season_year == 2027 and abs(next_season.total - 4.4) < 1e-6,
      "changement d'année : le cumul repart de zéro")

# Ordre phénologique respecté
stages = phenology.ordered_stages("apple")
check(stages[0] == "silver_tip" and stages[-1] == "full_bloom",
      "stades pommier ordonnés de pointe argentée à pleine floraison")
check(all(x in crops.CROPS["apple"].stages for x in stages),
      "tous les stades GDD existent dans la table de gel WSU")

# Cohérence croisée : chaque espèce a les mêmes stades des deux côtés
for crop_key, table in phenology.STAGE_GDD.items():
    if crop_key in crops.CROPS:
        missing = set(table) - set(crops.CROPS[crop_key].stages)
        check(not missing,
              f"{crop_key} : stades GDD tous présents dans la table de gel")

# Stade attendu selon le cumul
check(phenology.stage_for_gdd("apple", 50) is None,
      "cumul insuffisant : aucun stade atteint")
check(phenology.stage_for_gdd("apple", 300) == "tight_cluster",
      "300 °C·j -> bouquet serré")
check(phenology.stage_for_gdd("apple", 5000) == "full_bloom",
      "cumul très élevé : dernier stade, pas de débordement")

# Décalage régional
# 300 + 100 = 400 -> full_pink (seuil 370), pas first_pink (330)
check(phenology.stage_for_gdd("apple", 300, offset=100) == "full_pink",
      "décalage positif : verger en avance")
check(phenology.stage_for_gdd("apple", 300, offset=-100) == "half_inch_green",
      "décalage négatif : verger en retard")

# Avancement monotone : jamais de retour en arrière
check(phenology.propose_advance("apple", "green_tip", 300) == "tight_cluster",
      "avancement proposé quand le seuil est franchi")
check(phenology.propose_advance("apple", "full_bloom", 300) is None,
      "pas de recul : un stade acquis n'est jamais défait")
check(phenology.propose_advance("apple", "tight_cluster", 300) is None,
      "aucun changement si le stade est déjà le bon")
check(phenology.propose_advance("apple", None, 300) == "tight_cluster",
      "stade initial déduit du cumul si non renseigné")
check(phenology.propose_advance("generic", "x", 300) is None,
      "espèce sans table GDD : aucun avancement")

# Une correction manuelle sert de nouvelle référence
check(phenology.propose_advance("apple", "first_pink", 300) is None,
      "correction manuelle en avance respectée, pas ramenée en arrière")

# Seuil suivant
nxt = phenology.next_stage_threshold("apple", "green_tip")
check(nxt is not None and nxt[0] == "half_inch_green",
      "stade suivant correctement identifié")
check(phenology.next_stage_threshold("apple", "full_bloom") is None,
      "dernier stade : pas de suivant")

# Jours avant récolte
d2h = phenology.days_to_harvest("apple", _date(2026, 5, 1), _date(2026, 6, 1))
check(d2h == 145 - 31, f"jours avant récolte décomptés (obtenu {d2h})")
check(phenology.days_to_harvest("apple", None, _date(2026, 6, 1)) is None,
      "sans date de floraison : pas d'estimation")
check(phenology.days_to_harvest("apple", _date(2025, 1, 1), _date(2026, 6, 1)) == 0,
      "récolte dépassée : borné à 0, jamais négatif")

# ======================================================================
print("\n--- multi-arbres : modèles pertinents par espèce ---")
# ======================================================================

check(const.MODEL_LATE_BLIGHT not in const.CROP_DISEASE_MODELS["apple"],
      "le mildiou de la pomme de terre ne s'applique pas au pommier")
check(const.MODEL_POWDERY_MILDEW in const.CROP_DISEASE_MODELS["apple"],
      "l'oïdium s'applique au pommier")
check(const.MODEL_LATE_BLIGHT in const.CROP_DISEASE_MODELS["potato"],
      "le mildiou s'applique à la pomme de terre")
for crop_key in crops.CROPS:
    check(crop_key in const.CROP_DISEASE_MODELS,
          f"{crop_key} : modèles maladie définis")

# ======================================================================
print("\n--- migration : une culture unique devient un arbre ---")
# ======================================================================

# Cas réel qui a cassé : une entrée v3 avec culture et stade configurés.
legacy = {
    "temperature_entity": "sensor.ecowitt_temp",
    "humidity_entity": "sensor.ecowitt_hum",
    "weather_entity": "weather.meteoswiss",
    "enabled_models": ["frost"],
    "crop": "apple",
    "stage": "full_bloom",
}
migrated = tree_mod.legacy_tree_data(legacy)
check(migrated["crop"] == "apple", "l'espèce configurée est conservée")
check(migrated["stage"] == "full_bloom", "le stade en cours n'est pas perdu")
check(migrated["tree_name"] == "Pommier", "l'arbre reçoit le nom de l'espèce")
check(migrated["auto_advance"] is True, "avancement automatique activé par défaut")

# Le reste de la configuration du site est préservé, sans les clés migrées.
stripped = tree_mod.strip_legacy_keys(legacy)
check("crop" not in stripped and "stage" not in stripped,
      "les clés migrées sont retirées de l'entrée")
check(stripped["temperature_entity"] == "sensor.ecowitt_temp",
      "les capteurs du site sont préservés")
check(stripped["enabled_models"] == ["frost"],
      "les modèles activés sont préservés")

# Ancienne entrée sans culture (v1 / v2) : on crée quand même un arbre,
# sinon l'intégration ne produirait plus aucune entité de risque.
bare = tree_mod.legacy_tree_data({"temperature_entity": "sensor.t"})
check(bare["crop"] == crops.GENERIC_CROP,
      "sans culture configurée : repli sur la culture générique")
check("stage" not in bare, "pas de stade inventé quand il n'y en avait pas")
check(bare["tree_name"], "un nom d'arbre est toujours fourni")

# Idempotence : migrer deux fois ne dénature pas les données.
check(tree_mod.strip_legacy_keys(stripped) == stripped,
      "retirer les clés déjà retirées ne change rien")

# Les données produites sont acceptées par le constructeur d'arbre.
built = tree_mod.Tree.from_subentry("abc123", migrated)
check(built.crop == "apple" and built.stage == "full_bloom",
      "l'arbre reconstruit depuis la migration est cohérent")
check(built.display_name == "Pommier", "nom affiché sans doublon d'espèce")
check(const.MODEL_FROST in built.models, "le modèle de gel reste actif")

# Un nom personnalisé se combine avec l'espèce sans la répéter.
custom = tree_mod.Tree.from_subentry("x", {"crop": "apple", "tree_name": "Golden"})
check(custom.display_name == "Pommier Golden",
      "nom personnalisé préfixé par l'espèce")
already = tree_mod.Tree.from_subentry("y", {"crop": "apple", "tree_name": "Pommier Golden"})
check(already.display_name == "Pommier Golden",
      "espèce non répétée si le nom la contient déjà")

# ----------------------------------------------------------------------
# Traductions : toute clé exposée à l'interface doit être traduite
# ----------------------------------------------------------------------
#
# Une clé sans traduction ne provoque aucune erreur : Home Assistant
# affiche simplement « full_bloom » à l'utilisateur. C'est exactement le
# genre de régression qu'on ne voit qu'en production, d'où ce contrôle.

print("\n--- traductions des libellés ---")

import json as _json

_TR_DIR = ROOT / "custom_components" / "meteo_sentinelle"
_LANGS = {
    path.stem: _json.loads(path.read_text(encoding="utf-8"))
    for path in sorted((_TR_DIR / "translations").glob("*.json"))
}
check(set(_LANGS) >= {"en", "fr"}, "les traductions anglaise et française existent")

_RISK_LEVELS = list(const.RISK_LEVELS)
_STAGES = crops.all_stage_keys()
_CROPS = crops.crop_options()

for _lang, _data in sorted(_LANGS.items()):
    _sel = _data.get("selector", {})
    _ent = _data.get("entity", {})

    _crop_opts = set(_sel.get("crop", {}).get("options", {}))
    check(set(_CROPS) <= _crop_opts,
          f"{_lang} : toutes les espèces sont traduites")

    _stage_opts = set(_sel.get("stage", {}).get("options", {}))
    check(set(_STAGES) <= _stage_opts,
          f"{_lang} : tous les stades sont traduits dans le sélecteur")

    _select_states = set(
        _ent.get("select", {}).get("phenology_stage", {}).get("state", {})
    )
    check(set(_STAGES) <= _select_states,
          f"{_lang} : tous les stades sont traduits pour l'entité select")

    _sensor = _ent.get("sensor", {})
    for _key in ("frost_risk", "late_blight_risk", "powdery_mildew_risk"):
        check(set(_RISK_LEVELS) <= set(_sensor.get(_key, {}).get("state", {})),
              f"{_lang} : niveaux de risque traduits pour {_key}")

    # Un nom manquant afficherait la clé technique dans l'interface.
    for _key in (
        "frost_risk", "late_blight_risk", "powdery_mildew_risk",
        "phenology_stage", "powdery_mildew_index", "late_blight_protection",
        "powdery_mildew_protection", "growing_degree_days", "data_source",
    ):
        check(bool(_sensor.get(_key, {}).get("name")),
              f"{_lang} : le capteur {_key} a un nom traduit")

# Les fichiers doivent exposer exactement les mêmes clés : une clé
# présente en français mais absente en anglais passerait inaperçue.
def _flat(data, prefix=""):
    out = set()
    for key, value in data.items():
        out.add(prefix + key)
        if isinstance(value, dict):
            out |= _flat(value, prefix + key + ".")
    return out

_reference = _flat(_LANGS["en"])
for _lang, _data in sorted(_LANGS.items()):
    check(_flat(_data) == _reference,
          f"{_lang} : mêmes clés de traduction que l'anglais")

_strings = _json.loads((_TR_DIR / "strings.json").read_text(encoding="utf-8"))
check(_flat(_strings) == _reference,
      "strings.json expose les mêmes clés que les traductions")

# Aucun libellé lisible ne doit subsister dans les options renvoyées par
# le code : ce sont des clés techniques, pas du texte affichable.
check(all(" " not in key for key in _CROPS + _STAGES),
      "les options exposées sont des clés techniques, pas des libellés")


# ----------------------------------------------------------------------
# Blueprints : structure et cohérence des entrées
# ----------------------------------------------------------------------
#
# Un blueprint cassé ne se voit qu'au moment où l'utilisateur tente de
# l'importer. Ces contrôles sont donc purement structurels, mais ils
# attrapent les fautes les plus coûteuses : une entrée référencée mais
# jamais déclarée, ou repliée sans valeur par défaut (Home Assistant
# refuse alors le blueprint).

print("\n--- blueprints ---")

try:
    import yaml as _yaml
except ImportError:
    print("  (PyYAML absent : contrôle des blueprints ignoré)")
else:
    class _BlueprintLoader(_yaml.SafeLoader):
        """!input n'est pas du YAML standard : lui donner un constructeur."""

    _BlueprintLoader.add_constructor(
        "!input", lambda loader, node: {"__input__": loader.construct_scalar(node)}
    )

    _BP_DIR = ROOT / "blueprints" / "automation" / "meteo_sentinelle"
    _blueprints = sorted(_BP_DIR.glob("*.yaml"))
    check(len(_blueprints) >= 2, "au moins deux blueprints sont fournis")

    _KNOWN_EVENTS = {"meteo_sentinelle_risk_changed", "meteo_sentinelle_stage_advanced"}

    for _path in _blueprints:
        _doc = _yaml.load(_path.read_text(encoding="utf-8"), Loader=_BlueprintLoader)
        _meta = _doc.get("blueprint", {})
        _label = _path.name

        check(_meta.get("domain") == "automation", f"{_label} : domaine automation")
        check(bool(_meta.get("name")), f"{_label} : le blueprint est nommé")
        check(bool(_meta.get("description")), f"{_label} : le blueprint est décrit")

        # Les entrées peuvent être groupées en sections : une section se
        # reconnaît à la présence d'une clé « input » imbriquée.
        _declared = {}
        _sections = {}
        for _key, _value in (_meta.get("input") or {}).items():
            if isinstance(_value, dict) and "input" in _value:
                for _sub, _cfg in _value["input"].items():
                    _declared[_sub] = _cfg
                    _sections[_sub] = _value
            else:
                _declared[_key] = _value or {}

        _used = set()

        def _walk(node):
            if isinstance(node, dict):
                if set(node) == {"__input__"}:
                    _used.add(node["__input__"])
                    return
                for _v in node.values():
                    _walk(_v)
            elif isinstance(node, list):
                for _v in node:
                    _walk(_v)

        _walk({k: v for k, v in _doc.items() if k != "blueprint"})

        check(_used <= set(_declared),
              f"{_label} : toute entrée utilisée est déclarée")
        check(set(_declared) <= _used,
              f"{_label} : aucune entrée déclarée mais inutilisée")

        # Home Assistant refuse une entrée repliée sans valeur par défaut.
        for _name, _cfg in _declared.items():
            if _sections.get(_name, {}).get("collapsed"):
                check("default" in _cfg,
                      f"{_label} : « {_name} » repliée a une valeur par défaut")

        # Les sections exigent Home Assistant 2024.6 : sans min_version,
        # le blueprint échoue silencieusement sur les versions antérieures.
        if _sections:
            check(bool(_meta.get("homeassistant", {}).get("min_version")),
                  f"{_label} : min_version déclaré puisqu'il utilise des sections")

        # Un blueprint qui écoute un événement inexistant ne se déclenche
        # jamais, sans le moindre message.
        _events = {
            t.get("event_type")
            for t in (_doc.get("triggers") or [])
            if isinstance(t, dict) and t.get("trigger") == "event"
        }
        check(_events <= _KNOWN_EVENTS,
              f"{_label} : n'écoute que des événements réellement émis")


    # Les blueprints existent en paires anglais/français. La duplication
    # n'est tenable que si les deux versions restent structurellement
    # identiques : mêmes entrées, mêmes valeurs par défaut, mêmes
    # déclencheurs. Seul le texte doit différer.
    _PAIRS = [
        ("frost_protection.yaml", "protection_gel.yaml"),
        ("risk_alerts.yaml", "alerte_meteo_sentinelle.yaml"),
    ]

    def _structure(doc):
        meta = doc.get("blueprint", {})
        inputs = {}
        for key, value in (meta.get("input") or {}).items():
            if isinstance(value, dict) and "input" in value:
                for sub, cfg in value["input"].items():
                    inputs[sub] = (cfg or {}).get("default", "__required__")
            else:
                inputs[key] = (value or {}).get("default", "__required__")
        events = sorted(
            t.get("event_type")
            for t in (doc.get("triggers") or [])
            if isinstance(t, dict) and t.get("trigger") == "event"
        )
        return inputs, events, doc.get("mode")

    for _en_name, _fr_name in _PAIRS:
        _en_path, _fr_path = _BP_DIR / _en_name, _BP_DIR / _fr_name
        check(_en_path.exists() and _fr_path.exists(),
              f"{_en_name} et {_fr_name} existent tous les deux")
        if not (_en_path.exists() and _fr_path.exists()):
            continue

        _en = _yaml.load(_en_path.read_text(encoding="utf-8"), Loader=_BlueprintLoader)
        _fr = _yaml.load(_fr_path.read_text(encoding="utf-8"), Loader=_BlueprintLoader)
        _en_struct, _fr_struct = _structure(_en), _structure(_fr)

        check(_en_struct[0] == _fr_struct[0],
              f"{_en_name} / {_fr_name} : mêmes entrées et mêmes valeurs par défaut")
        check(_en_struct[1] == _fr_struct[1],
              f"{_en_name} / {_fr_name} : mêmes événements écoutés")
        check(_en_struct[2] == _fr_struct[2],
              f"{_en_name} / {_fr_name} : même mode d'exécution")

    # Les événements écoutés doivent correspondre aux constantes du code.
    check({const.EVENT_RISK_CHANGED, const.EVENT_STAGE_ADVANCED} == _KNOWN_EVENTS,
          "les événements des blueprints correspondent à ceux de const.py")


print(f"\n=== {_checks} vérifications passées ===")
