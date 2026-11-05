/**
 * Carte Météo Sentinelle — le verger, d'un coup d'œil.
 *
 * Une question d'abord : « est-ce que je dois faire quelque chose, et
 * quand ? ». La carte y répond en trois temps :
 *
 *   1. un bandeau dit en une phrase ce qui presse, et quand agir ;
 *   2. chaque arbre est une petite scène dessinée, qui suit son stade (bois
 *      nu, bourgeons, fleurs, fruits) et montre ce qui le menace : neige pour
 *      le gel, champignons au pied pour les maladies, insectes pour les
 *      ravageurs ;
 *   3. toucher un arbre ouvre son détail : où il en est de sa saison, à quels
 *      stades il faut se méfier, et les gestes à déclarer.
 *
 * Aucune dépendance, aucun build : le fichier est servi tel quel par
 * l'intégration, ce qui évite à l'utilisateur d'installer un dépôt frontend
 * séparé et d'ajouter une ressource à la main.
 */

(function () {
"use strict";

//: Ce fichier est servi tel quel, sans compilation : il doit donc s'en tenir à
//: ce que comprennent les appareils qui l'affichent. Le WebView d'un écran mural
//: sous Android 8 (NSPanel Pro) rejette le fichier entier au premier `?.` ou `??`,
//: et la carte « n'existe pas ». D'où une syntaxe limitée à ES2017, contrôlée par
//: la CI, et une feuille de style sans `color-mix`, `aspect-ratio` ni `gap` de
//: flexbox. La fonction englobante évite tout conflit de noms quand le fichier
//: est chargé comme script classique.

const CARD_TYPE = "meteo-sentinelle-card";
const DOMAIN = "meteo_sentinelle";

const LEVELS = ["none", "watch", "warning", "severe"];
const TREATABLE = [
  "late_blight",
  "powdery_mildew",
  "codling_moth",
  "cherry_fruit_fly",
  "colorado_potato_beetle",
  "grapevine_moth",
];
const DISEASES = ["powdery_mildew", "late_blight"];
const REST_STAGES = ["dormant", "off_season"];
//: Base des degrés-jours phénologiques, pour estimer un délai en jours.
const GDD_BASE = 5.6;

const STRINGS = {
  fr: {
    title: "Mon verger",
    levels: { none: "RAS", watch: "Vigilance", warning: "Alerte", severe: "Danger" },
    models: {
      frost: "Gel",
      powdery_mildew: "Oïdium",
      late_blight: "Mildiou",
      codling_moth: "Carpocapse",
      cherry_fruit_fly: "Mouche de la cerise",
      colorado_potato_beetle: "Doryphore",
      grapevine_moth: "Eudémis",
    },
    crops: {
      apple: "Pommier",
      pear: "Poirier",
      apricot: "Abricotier",
      plum: "Prunier",
      peach: "Pêcher",
      sweet_cherry: "Cerisier",
      vine: "Vigne",
      tender_annual: "Annuelles",
      potato: "Pomme de terre",
      hardy_vegetable: "Légumes rustiques",
      generic: "Culture",
    },
    phases: {
      growing: "En saison",
      winter_rest: "Repos hivernal",
      no_winter: "Pas d'hiver",
      disabled: "Saisons désactivées",
    },
    cycle: {
      flight: "Vol en cours",
      egg_laying: "Pontes",
      hatch_start: "Début d'éclosion",
      hatch_peak: "Éclosion généralisée",
      oviposition_peak: "Pic de ponte",
      second_generation: "2e génération",
      approach: "Émergence proche",
      emergence: "Émergence",
      oviposition: "Ponte en cours",
      eggs: "Pontes déposées",
      instar_1: "Larves L1",
      instar_2: "Larves L2",
      instar_3: "Larves L3",
      instar_4: "Larves L4",
      pupation: "Nymphose",
      first_flight: "1er vol",
      first_generation: "Larves G1",
      second_flight: "2e vol",
      third_flight: "3e vol",
      third_generation: "Larves G3",
    },
    growth: {
      fruitlet: "Jeunes fruits",
      fruit: "Fruits en croissance",
      ripe: "Fruits à maturité",
      harvest: "Récolte",
      autumn: "Après récolte",
      leafy: "Pleine végétation",
    },
    harvestIn: "récolte dans ~{days} j",
    all_good: "Tout va bien au verger",
    all_good_text: "Aucun risque à signaler pour le moment.",
    next_meeting: "Prochaine étape pour {tree} : {what}, {when}.",
    resting: "Le verger se repose",
    resting_text: "Maladies et ravageurs sont en pause jusqu'au printemps.",
    first_wake: "{tree} repartira le premier, {when}.",
    when_days: "dans ~{days} j",
    when_days_one: "demain environ",
    when_dd: "dans {dd} °C·j",
    when_cold: "quand il fera plus doux",
    when_spring: "au printemps",
    frost_title: "Gel attendu",
    frost_text: "{temp} °C prévus{when}. Dégâts dès {t10} °C à ce stade.",
    frost_near: "{temp} °C prévus{when}, tout près du seuil de {t10} °C.",
    frost_plain: "{temp} °C prévus{when}.",
    frost_do: "Protégez cette nuit : voile d'hivernage ou aspersion.",
    frost_watch: "Gardez un œil sur la prochaine nuit.",
    disease_title: "{model} : conditions favorables",
    mildew_text: "Indice {index}/100.",
    mildew_interval: " Traitement conseillé tous les {days} j.",
    blight_hutton: "Deux jours doux et humides d'affilée.",
    blight_one: "Un jour doux et humide, le second déclencherait l'alerte.",
    pest_title: "{model} : {stage}",
    pest_estimated: "Date estimée d'après la floraison.",
    act_now: "C'est le moment d'intervenir.",
    keep_watch: "À surveiller.",
    do_treat_at: "Prochaine fenêtre de traitement : {when}.",
    do_treat_open: "Vous pouvez traiter maintenant, jusqu'à {time}.",
    do_treat_none: "Pas de fenêtre de traitement dans les prévisions.",
    protected_until: "Protégé jusqu'au {date}",
    protected_short: "Protégé",
    others: "+{count} autres",
    others_one: "+1 autre",
    min_forecast: "Min. prévu",
    spray_title: "Fenêtres de traitement",
    spray_open: "Ouverte jusqu'à {time}",
    spray_next: "Prochaine : {when}",
    spray_none: "Aucune dans les prévisions",
    block_wind: "trop de vent",
    block_rain: "pluie",
    block_temperature: "température",
    today: "aujourd'hui",
    tomorrow: "demain",
    tonight: "cette nuit",
    at: "{day} à {time}",
    season_path: "Parcours de la saison",
    frost_sensitivity: "Plus la barre est haute, plus le gel fait de dégâts à ce stade.",
    stage_here: "Dégâts de gel dès {t10} °C.",
    stage_safe: "Pas de risque de gel à ce stade.",
    next_stage: "Ensuite : {stage}, {when}.",
    observed_stage: "Stade observé",
    observed_help: "Votre arbre n'en est pas là ? Choisissez le bon stade : le suivi repart de là.",
    frost_gauge: "Gel : minimum prévu et seuils",
    gauge_min: "Prévu {temp} °C",
    gauge_t10: "10 % de dégâts",
    gauge_t90: "90 % de dégâts",
    risks: "Risques",
    now_label: "maintenant",
    frost_calm: "Rien à craindre, {temp} °C au plus bas.",
    end_rest: "Repos",
    treat: "J'ai traité",
    treat_confirm: "Confirmer ?",
    clear_treat: "Effacer",
    first_catch: "Première capture aujourd'hui",
    waiting_biofix: "En attente de la première observation au piège.",
    estimated_biofix: "Départ estimé le {date}, d'après la floraison.",
    declared_biofix: "Départ observé le {date}.",
    diapause: "En diapause jusqu'au printemps.",
    paused: "En pause pendant le repos.",
    next_cycle: "Ensuite : {stage}, {when}.",
    index_band: "Indice oïdium {index}/100.",
    wet_days: "{days}/2 jours favorables",
    close: "Fermer",
    empty_title: "Votre verger est vide",
    empty_text: "Ajoutez un arbre depuis la page de l'intégration Météo Sentinelle.",
    unavailable: "Données momentanément indisponibles.",
    fields: {
      title: "Titre",
      devices: "Arbres affichés (tous si vide)",
      show_spray: "Afficher les fenêtres de traitement",
    },
    call_failed: "Action impossible : {message}",
  },
  en: {
    title: "My orchard",
    levels: { none: "OK", watch: "Watch", warning: "Warning", severe: "Danger" },
    models: {
      frost: "Frost",
      powdery_mildew: "Powdery mildew",
      late_blight: "Late blight",
      codling_moth: "Codling moth",
      cherry_fruit_fly: "Cherry fruit fly",
      colorado_potato_beetle: "Colorado beetle",
      grapevine_moth: "Grape moth",
    },
    crops: {
      apple: "Apple",
      pear: "Pear",
      apricot: "Apricot",
      plum: "Plum",
      peach: "Peach",
      sweet_cherry: "Cherry",
      vine: "Grapevine",
      tender_annual: "Annuals",
      potato: "Potato",
      hardy_vegetable: "Hardy vegetables",
      generic: "Crop",
    },
    phases: {
      growing: "In season",
      winter_rest: "Winter rest",
      no_winter: "No winter",
      disabled: "Seasons off",
    },
    cycle: {
      flight: "Flight under way",
      egg_laying: "Egg laying",
      hatch_start: "Hatch starting",
      hatch_peak: "Peak hatch",
      oviposition_peak: "Peak egg laying",
      second_generation: "2nd generation",
      approach: "Emergence near",
      emergence: "Emergence",
      oviposition: "Egg laying",
      eggs: "Eggs laid",
      instar_1: "1st instar",
      instar_2: "2nd instar",
      instar_3: "3rd instar",
      instar_4: "4th instar",
      pupation: "Pupation",
      first_flight: "1st flight",
      first_generation: "1st gen. larvae",
      second_flight: "2nd flight",
      third_flight: "3rd flight",
      third_generation: "3rd gen. larvae",
    },
    growth: {
      fruitlet: "Young fruit",
      fruit: "Fruit growing",
      ripe: "Fruit ripening",
      harvest: "Harvest",
      autumn: "After harvest",
      leafy: "Full leaf",
    },
    harvestIn: "harvest in ~{days} d",
    all_good: "All is well in the orchard",
    all_good_text: "No risk to report right now.",
    next_meeting: "Next step for {tree}: {what}, {when}.",
    resting: "The orchard is resting",
    resting_text: "Diseases and pests are paused until spring.",
    first_wake: "{tree} will wake first, {when}.",
    when_days: "in ~{days} d",
    when_days_one: "around tomorrow",
    when_dd: "in {dd} °C·d",
    when_cold: "once it warms up",
    when_spring: "in spring",
    frost_title: "Frost expected",
    frost_text: "{temp} °C forecast{when}. Damage from {t10} °C at this stage.",
    frost_near: "{temp} °C forecast{when}, close to the {t10} °C threshold.",
    frost_plain: "{temp} °C forecast{when}.",
    frost_do: "Protect tonight: frost fleece or sprinklers.",
    frost_watch: "Keep an eye on the next night.",
    disease_title: "{model}: favourable conditions",
    mildew_text: "Index {index}/100.",
    mildew_interval: " Spray every {days} d.",
    blight_hutton: "Two mild, humid days in a row.",
    blight_one: "One mild, humid day; a second would trigger the alert.",
    pest_title: "{model}: {stage}",
    pest_estimated: "Date estimated from bloom.",
    act_now: "Time to act.",
    keep_watch: "Keep watching.",
    do_treat_at: "Next spray window: {when}.",
    do_treat_open: "You can spray now, until {time}.",
    do_treat_none: "No spray window in the forecast.",
    protected_until: "Protected until {date}",
    protected_short: "Protected",
    others: "+{count} more",
    others_one: "+1 more",
    min_forecast: "Forecast low",
    spray_title: "Spray windows",
    spray_open: "Open until {time}",
    spray_next: "Next: {when}",
    spray_none: "None in the forecast",
    block_wind: "too windy",
    block_rain: "rain",
    block_temperature: "temperature",
    today: "today",
    tomorrow: "tomorrow",
    tonight: "tonight",
    at: "{day} at {time}",
    season_path: "Season path",
    frost_sensitivity: "The taller the bar, the more damage frost does at that stage.",
    stage_here: "Frost damage from {t10} °C.",
    stage_safe: "No frost risk at this stage.",
    next_stage: "Next: {stage}, {when}.",
    observed_stage: "Observed stage",
    observed_help: "Tree not there yet? Pick the right stage: tracking resumes from there.",
    frost_gauge: "Frost: forecast low and thresholds",
    gauge_min: "Forecast {temp} °C",
    gauge_t10: "10% damage",
    gauge_t90: "90% damage",
    risks: "Risks",
    now_label: "now",
    frost_calm: "Nothing to fear, low of {temp} °C.",
    end_rest: "Rest",
    treat: "I sprayed",
    treat_confirm: "Confirm?",
    clear_treat: "Clear",
    first_catch: "First catch today",
    waiting_biofix: "Waiting for the first trap observation.",
    estimated_biofix: "Start estimated on {date}, from bloom.",
    declared_biofix: "Start observed on {date}.",
    diapause: "In diapause until spring.",
    paused: "Paused during rest.",
    next_cycle: "Next: {stage}, {when}.",
    index_band: "Powdery mildew index {index}/100.",
    wet_days: "{days}/2 favourable days",
    close: "Close",
    empty_title: "Your orchard is empty",
    empty_text: "Add a tree from the Météo Sentinelle integration page.",
    unavailable: "Data temporarily unavailable.",
    fields: {
      title: "Title",
      devices: "Trees shown (all if empty)",
      show_spray: "Show spray windows",
    },
    call_failed: "Action failed: {message}",
  },
};

// ---------------------------------------------------------------------
// Outils
// ---------------------------------------------------------------------

function strings(hass) {
  return STRINGS[language(hass).slice(0, 2)] || STRINGS.en;
}

/** Valeur, ou repli si elle est absente : 0 et "" restent des valeurs. */
function orElse(value, fallback) {
  return value === undefined || value === null ? fallback : value;
}

/** Attributs d'un état, sans erreur s'il n'existe pas. */
function attrs(state) {
  return (state && state.attributes) || {};
}

function allRisks(trees) {
  return trees.reduce((all, tree) => all.concat(tree.risks), []);
}

function fill(template, values = {}) {
  return template.replace(/\{(\w+)\}/g, (_, key) => orElse(values[key], ""));
}

function esc(value) {
  return String(orElse(value, "")).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

function rank(level) {
  return Math.max(0, LEVELS.indexOf(level));
}

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

function isNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function language(hass) {
  return (hass && hass.locale && hass.locale.language) || (hass && hass.language) || "en";
}

function formatNumber(hass, value, digits = 1) {
  if (!isNumber(value)) return "—";
  return new Intl.NumberFormat(language(hass), { maximumFractionDigits: digits })
    .format(value)
    .replace("-", "−");
}

function zone(hass) {
  return (hass && hass.config && hass.config.time_zone) || undefined;
}

function dayKey(hass, date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: zone(hass),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function formatTime(hass, date) {
  return new Intl.DateTimeFormat(language(hass), {
    timeZone: zone(hass),
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDate(hass, value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(language(hass), {
    timeZone: zone(hass),
    day: "numeric",
    month: "short",
  }).format(date);
}

function hourOf(hass, date) {
  return Number(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: zone(hass),
      hour: "2-digit",
      hourCycle: "h23",
    }).format(date)
  );
}

/** « cette nuit à 04:00 », « demain à 07:00 », « mar. à 07:00 ». */
function formatWhen(hass, s, value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const today = dayKey(hass, now);
  const tomorrow = dayKey(hass, new Date(now.getTime() + 86400000));
  const key = dayKey(hass, date);
  const hour = hourOf(hass, date);
  const nowHour = hourOf(hass, now);
  let day;
  if (
    (key === today && hour < 8 && nowHour < 8) ||
    (key === tomorrow && hour < 8 && nowHour >= 16)
  ) {
    day = s.tonight;
  } else if (key === today) {
    day = s.today;
  } else if (key === tomorrow) {
    day = s.tomorrow;
  } else {
    day = new Intl.DateTimeFormat(language(hass), {
      timeZone: zone(hass),
      weekday: "short",
    }).format(date);
  }
  return fill(s.at, { day, time: formatTime(hass, date) });
}

/** Libellé traduit d'un stade, par les traductions de l'intégration. */
function stageLabel(hass, stateObj, key) {
  if (!key) return "";
  if (stateObj && hass && hass.formatEntityState) {
    try {
      const label = hass.formatEntityState(stateObj, key);
      if (label) return label;
    } catch (err) {
      // Repli ci-dessous : une clé lisible vaut mieux qu'une carte en erreur.
    }
  }
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// ---------------------------------------------------------------------
// Données : des entités à une vue du verger
// ---------------------------------------------------------------------

/** Répertorie les entités de l'intégration, par nature. */
function discover(hass) {
  const registry = hass.entities || {};
  let ids = Object.keys(registry).filter((id) => registry[id] && registry[id].platform === DOMAIN);
  // Le registre n'est pas toujours exposé au frontend : l'attribut prend
  // alors le relais.
  if (!ids.length) {
    ids = Object.keys(hass.states || {}).filter(
      (id) => id.startsWith("sensor.") && attrs(hass.states[id]).site_id
    );
  }
  const found = { risks: [], stages: [], spray: [], season: [], gdd: [] };
  for (const id of ids) {
    if (!id.startsWith("sensor.")) continue;
    if (!hass.states[id] || !hass.states[id].attributes) continue;
    const attributes = hass.states[id].attributes;
    if (attributes.model) found.risks.push(id);
    else if (attributes.stages && attributes.subentry_id) found.stages.push(id);
    else if (attributes.windows !== undefined) found.spray.push(id);
    else if (attributes.hemisphere !== undefined) found.season.push(id);
    else if (attributes.base_temperature !== undefined && attributes.season_year) {
      found.gdd.push(id);
    }
  }
  return found;
}

/** Degrés-jours quotidiens récents pour une base donnée, ou null. */
function dailySpeed(gddState, base) {
  const recent = (attrs(gddState).recent_days || []).slice(-7);
  if (!recent.length) return null;
  const mean = recent.reduce((sum, day) => sum + (day.gdd || 0), 0) / recent.length;
  return Math.max(0, mean + GDD_BASE - base);
}

function formatDelay(hass, s, degreeDays, speed) {
  if (!isNumber(degreeDays)) return "";
  if (isNumber(speed) && speed >= 0.5) {
    const days = Math.max(1, Math.ceil(degreeDays / speed));
    return days <= 1 ? s.when_days_one : fill(s.when_days, { days });
  }
  if (isNumber(speed)) return s.when_cold;
  return fill(s.when_dd, { dd: formatNumber(hass, degreeDays, 0) });
}

/** Phase dessinée d'une plante à partir de son stade et de sa floraison. */
const STAGE_PHASES = {
  dormant: "rest",
  off_season: "rest",
  silver_tip: "bud",
  swollen_bud: "bud",
  first_swell: "bud",
  bud_swell: "bud",
  tip_separation: "bud",
  side_white: "bud",
  calyx_green: "bud",
  green_tip: "leaf",
  half_inch_green: "leaf",
  quarter_inch_green: "leaf",
  bud_burst: "leaf",
  green_cluster: "leaf",
  tight_cluster: "leaf",
  first_leaves: "leaf",
  shoots_10cm: "leaf",
  first_pink: "flowerbud",
  full_pink: "flowerbud",
  pink: "flowerbud",
  white_bud: "flowerbud",
  full_white: "flowerbud",
  first_white: "flowerbud",
  first_bloom: "bloom",
  full_bloom: "bloom",
  petal_fall: "fruitlet",
  post_bloom: "fruitlet",
  in_the_shuck: "fruitlet",
  shuck_split: "fruitlet",
  growing: "plant",
  emerged: "plant",
};

//: Après le dernier stade suivi, la croissance est estimée d'après la chaleur
//: reçue. Cette valeur ne sert qu'à faire avancer le dessin.
const VISUAL_SEASON_GDD = 1500;

function computeGrowth(stageKey, attributes) {
  const phase = STAGE_PHASES[stageKey] || "plant";
  const path = attributes.stages || [];
  const gdd =
    (attributes.gdd_total || 0) + (attributes.gdd_offset || 0) + (attributes.gdd_shift || 0);
  const ranked = path.filter((step) => isNumber(step.gdd));
  const lastGdd = ranked.length ? ranked[ranked.length - 1].gdd : null;
  const isLast = ranked.length && ranked[ranked.length - 1].key === stageKey;

  // Annuelles : un seul stade, la plante pousse avec la chaleur.
  if (phase === "plant") {
    return { phase, ripeness: clamp((gdd - 100) / 1100, 0, 1) };
  }
  if (phase === "rest") return { phase, ripeness: 0 };

  // Floraison passée : la suite se lit sur la date de floraison.
  const remaining = attributes.days_to_harvest;
  const total = attributes.bloom_to_harvest_days;
  if (attributes.bloom_date && isNumber(remaining) && isNumber(total) && total > 0) {
    const elapsed = (Date.now() - new Date(attributes.bloom_date).getTime()) / 86400000;
    if (elapsed > total + 21) return { phase: "autumn", ripeness: 1, growth: "autumn" };
    if (remaining <= 0) return { phase: "ripe", ripeness: 1, growth: "harvest" };
    const ratio = elapsed / total;
    if (elapsed < 10 && (phase === "bloom" || phase === "flowerbud")) return { phase: "bloom", ripeness: 0 };
    if (ratio < 0.2) return { phase: "fruitlet", ripeness: ratio, growth: "fruitlet" };
    if (ratio < 0.85) return { phase: "fruit", ripeness: ratio, growth: "fruit", remaining };
    return { phase: "ripe", ripeness: ratio, growth: "ripe", remaining };
  }

  // Sans date de floraison (vigne, stade saisi à la main) : le dernier stade
  // suivi est dépassé depuis longtemps si la chaleur a continué d'arriver.
  if (isLast && isNumber(lastGdd) && gdd - lastGdd > 150) {
    const ratio = clamp((gdd - lastGdd) / VISUAL_SEASON_GDD, 0, 1);
    if (ratio > 0.8) return { phase: "ripe", ripeness: ratio, growth: "leafy" };
    return { phase: ratio > 0.25 ? "fruit" : "fruitlet", ripeness: ratio, growth: "leafy" };
  }
  return { phase, ripeness: 0 };
}

function computeTitle(s, attributes) {
  const crop = attributes.crop || "generic";
  const short = s.crops[crop] || s.crops.generic;
  const raw = String(attributes.tree_name || "").replace(/_/g, " ").trim();
  if (!raw || raw === attributes.crop_label) return { title: short, crop: short, showCrop: false };
  const includesCrop = raw.toLowerCase().includes(short.split(" ")[0].toLowerCase());
  return { title: raw, crop: short, showCrop: !includesCrop };
}

/** Construit la vue complète à partir de l'état Home Assistant. */
function buildView(hass, config, ids) {
  const s = strings(hass);
  const byTree = new Map();

  const ensure = (key) => {
    if (!byTree.has(key)) byTree.set(key, { key, risks: [], stage: null });
    return byTree.get(key);
  };
  for (const id of ids.stages) {
    const state = hass.states[id];
    if (state) ensure(state.attributes.subentry_id).stage = state;
  }
  for (const id of ids.risks) {
    const state = hass.states[id];
    if (state) ensure(state.attributes.subentry_id || state.attributes.tree).risks.push(state);
  }

  // Filtre par appareils, s'il est configuré.
  const wanted = config && config.devices && config.devices.length ? new Set(config.devices) : null;
  const registry = hass.entities || {};
  const keep = (entry) => {
    if (!wanted) return true;
    const any = entry.stage || entry.risks[0];
    return any && wanted.has((registry[any.entity_id] || {}).device_id);
  };

  const entries = [...byTree.values()].filter(keep);
  const firstEntry = entries[0] || { risks: [] };
  const siteId = attrs(firstEntry.stage).site_id || attrs(firstEntry.risks[0]).site_id;
  const siteEntity = (list) => {
    const states = list.map((id) => hass.states[id]).filter(Boolean);
    return states.find((state) => state.attributes.site_id === siteId) || states[0] || null;
  };
  const gddState = siteEntity(ids.gdd);
  const seasonState = siteEntity(ids.season);
  const sprayState = siteEntity(ids.spray);
  // La date de repos est passée et la saison suivante n'a pas commencé : le cumul
  // ne dit encore rien du délai avant la reprise.
  const beforeSeason = Boolean(attrs(seasonState).in_rest);

  const trees = entries.map((entry) => {
    const stageAttributes = attrs(entry.stage);
    const attributes = entry.stage ? stageAttributes : attrs(entry.risks[0]);
    const stageKey = orElse(orElse(attributes.stage_key, attributes.stage), null);
    const growth = computeGrowth(stageKey, stageAttributes);
    const names = computeTitle(s, attributes);
    const resting = REST_STAGES.includes(stageKey);
    const risks = entry.risks
      .map((state) => ({
        entityId: state.entity_id,
        model: state.attributes.model,
        level: LEVELS.includes(state.state) ? state.state : "none",
        attributes: state.attributes,
        protection: state.attributes.protection || null,
        protectedNow: (state.attributes.protection || {}).status === "protected",
      }))
      .sort((a, b) => rank(b.level) - rank(a.level));

    const label = growth.growth
      ? s.growth[growth.growth]
      : stageLabel(hass, entry.stage, stageKey) || s.crops[attributes.crop] || "";
    const speed = dailySpeed(gddState, GDD_BASE);
    const next = stageAttributes.next_stage_key;
    const toNext = stageAttributes.gdd_to_next_stage;

    return {
      key: entry.key,
      subentryId: attributes.subentry_id || entry.key,
      crop: attributes.crop || "generic",
      title: names.title,
      cropLabel: names.crop,
      showCrop: names.showCrop,
      stageKey,
      stageState: entry.stage,
      stageLabel: label,
      growth,
      resting,
      path: stageAttributes.stages || [],
      t10: stageAttributes.t10,
      gdd: stageAttributes.gdd_total,
      next:
        next && isNumber(toNext)
          ? {
              key: next,
              label: stageLabel(hass, entry.stage, next),
              dd: toNext,
              speed,
              when: beforeSeason ? s.when_spring : formatDelay(hass, s, toNext, speed),
            }
          : null,
      risks,
      worst: risks.reduce((worst, risk) => Math.max(worst, rank(risk.level)), 0),
      seasonWinter: Boolean(seasonState) && seasonState.state === "winter_rest",
    };
  });

  trees.sort((a, b) => b.worst - a.worst || a.title.localeCompare(b.title));

  const alerts = buildAlerts(hass, s, trees, sprayState);
  const frostLows = allRisks(trees)
    .filter((risk) => risk.model === "frost" && isNumber(risk.attributes.air_min))
    .map((risk) => risk.attributes.air_min);

  return {
    s,
    trees,
    alerts,
    spray: sprayState,
    season: seasonState,
    gddState,
    minForecast: frostLows.length ? Math.min(...frostLows) : null,
    calm: alerts.length ? null : buildCalm(hass, s, trees, gddState),
    entitiesFound: ids.risks.length + ids.stages.length,
  };
}

//: Le modèle cherche quand le temps permet de traiter, de jour comme de nuit.
//: Conseiller de sortir à 1 h du matin n'aiderait personne : le message retient
//: le premier moment de jour, la bande des fenêtres montrant le reste.
const DAY_START_HOUR = 7;
const DAY_END_HOUR = 21;

/** Premier moment de jour dans une fenêtre, ou null si elle est toute de nuit. */
function firstDaylight(hass, window, now) {
  const end = Date.parse(window.end);
  let t = Math.max(Date.parse(window.start), now);
  while (t < end) {
    const hour = hourOf(hass, new Date(t));
    if (hour >= DAY_START_HOUR && hour < DAY_END_HOUR) return { from: t, to: end };
    t = (Math.floor(t / 3600000) + 1) * 3600000;
  }
  return null;
}

function nextDaylightWindow(hass, sprayState) {
  const now = Date.now();
  for (const window of attrs(sprayState).windows || []) {
    const found = firstDaylight(hass, window, now);
    if (found) return { from: found.from, to: found.to, open: found.from <= now };
  }
  return null;
}

function sprayAdvice(hass, s, sprayState) {
  if (!sprayState || !sprayState.attributes) return "";
  const window = nextDaylightWindow(hass, sprayState);
  if (!window) return s.do_treat_none;
  if (window.open) return fill(s.do_treat_open, { time: formatTime(hass, new Date(window.to)) });
  return fill(s.do_treat_at, { when: formatWhen(hass, s, window.from) });
}

/** Regroupe les risques actifs en messages, du plus urgent au moins urgent. */
function buildAlerts(hass, s, trees, sprayState) {
  const groups = new Map();
  for (const tree of trees) {
    for (const risk of tree.risks) {
      if (risk.level === "none") continue;
      // Le même risque sur plusieurs arbres fait un seul message, au niveau
      // du plus exposé. Seul un ravageur à deux stades différents en fait deux.
      const key = `${risk.model}|${risk.attributes.cycle_stage || ""}`;
      if (!groups.has(key)) {
        groups.set(key, { key, model: risk.model, level: risk.level, trees: [], risks: [] });
      }
      const group = groups.get(key);
      if (rank(risk.level) > rank(group.level)) group.level = risk.level;
      group.trees.push(tree);
      group.risks.push(risk);
    }
  }

  const alerts = [...groups.values()].map((group) => {
    const order = group.risks
      .map((item, i) => ({ item, tree: group.trees[i] }))
      .sort((x, y) => rank(y.item.level) - rank(x.item.level));
    const a = order[0].item.attributes;
    const model = s.models[group.model] || group.model;
    const names = order.map(({ tree }) => tree.title).join(", ");
    let title = model;
    let text = "";
    let action = "";

    if (group.model === "frost") {
      const coldest = group.risks.reduce((best, item) =>
        orElse(item.attributes.reference_min, 99) < orElse(best.attributes.reference_min, 99) ? item : best
      );
      const when = coldest.attributes.next_frost_time
        ? ` ${formatWhen(hass, s, coldest.attributes.next_frost_time)}`
        : "";
      const values = {
        temp: formatNumber(hass, coldest.attributes.reference_min),
        t10: formatNumber(hass, coldest.attributes.t10),
        when,
      };
      title = s.frost_title;
      if (isNumber(coldest.attributes.t10)) {
        text = fill(group.level === "watch" ? s.frost_near : s.frost_text, values);
      } else {
        text = fill(s.frost_plain, values);
      }
      action = group.level === "watch" ? s.frost_watch : s.frost_do;
    } else if (DISEASES.includes(group.model)) {
      title = fill(s.disease_title, { model });
      if (group.model === "powdery_mildew") {
        text = fill(s.mildew_text, { index: a.index || 0 });
        if (a.spray_interval_days) {
          text += fill(s.mildew_interval, { days: a.spray_interval_days });
        }
      } else {
        text = a.hutton_met ? s.blight_hutton : s.blight_one;
      }
    } else {
      const stage = s.cycle[a.cycle_stage] || a.cycle_stage || "";
      title = fill(s.pest_title, { model, stage: stage.charAt(0).toLowerCase() + stage.slice(1) });
      text = group.level === "watch" ? s.keep_watch : s.act_now;
      if (a.biofix_estimated) text += ` ${s.pest_estimated}`;
    }

    const allProtected = group.risks.every((item) => item.protectedNow);
    if (allProtected) {
      const until = group.risks
        .map((item) => (item.protection || {}).protected_until)
        .filter(Boolean)
        .sort()[0];
      action = until ? fill(s.protected_until, { date: formatDate(hass, until) }) : s.protected_short;
    } else if (group.model !== "frost" && group.level !== "watch") {
      action = sprayAdvice(hass, s, sprayState);
    }

    return {
      key: group.key,
      model: group.model,
      level: group.level,
      title,
      names,
      text,
      action,
      protected: allProtected,
    };
  });

  return alerts.sort(
    (a, b) =>
      rank(b.level) - rank(a.level) ||
      Number(a.protected) - Number(b.protected) ||
      Number(b.model === "frost") - Number(a.model === "frost")
  );
}

/** Le message quand rien ne presse : ce qui vient ensuite. */
function buildCalm(hass, s, trees, gddState) {
  if (!trees.length) return null;
  const candidates = [];
  for (const tree of trees) {
    if (tree.next) {
      candidates.push({
        tree: tree.title,
        what: tree.next.label.charAt(0).toLowerCase() + tree.next.label.slice(1),
        dd: tree.next.dd,
        speed: tree.next.speed,
        when: tree.next.when,
      });
    }
    for (const risk of tree.risks) {
      const a = risk.attributes;
      if (tree.resting || !isNumber(a.dd_to_next_cycle_stage) || !a.next_cycle_stage) continue;
      const upcoming = (a.stages || []).find((step) => step.stage === a.next_cycle_stage);
      if (!upcoming || upcoming.level === "none") continue;
      candidates.push({
        tree: tree.title,
        what: `${s.models[risk.model]} (${(s.cycle[a.next_cycle_stage] || "").toLowerCase()})`,
        dd: a.dd_to_next_cycle_stage,
        speed: dailySpeed(gddState, orElse(a.base_temperature, GDD_BASE)),
        when: formatDelay(
          hass,
          s,
          a.dd_to_next_cycle_stage,
          dailySpeed(gddState, orElse(a.base_temperature, GDD_BASE))
        ),
      });
    }
  }
  const soonest = candidates
    .map((item) =>
      Object.assign({}, item, {
        days: isNumber(item.speed) && item.speed >= 0.5 ? item.dd / item.speed : Infinity,
      })
    )
    .sort((a, b) => a.days - b.days || a.dd - b.dd)[0];

  const allResting = trees.every((tree) => tree.resting);
  if (allResting) {
    return {
      kind: "rest",
      title: s.resting,
      text: s.resting_text,
      next: soonest
        ? fill(s.first_wake, {
            tree: soonest.tree,
            when: soonest.when,
          })
        : "",
    };
  }
  return {
    kind: "ok",
    title: s.all_good,
    text: s.all_good_text,
    next: soonest
      ? fill(s.next_meeting, {
          what: soonest.what,
          tree: soonest.tree,
          when: soonest.when,
        })
      : "",
  };
}

// ---------------------------------------------------------------------
// Icônes
// ---------------------------------------------------------------------

const ICONS = {
  frost:
    '<g fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9"/><path d="M12 6.5 9.8 4.6M12 6.5l2.2-1.9M12 17.5l-2.2 1.9M12 17.5l2.2 1.9M6.9 9.1 4 8.5M6.9 9.1l-1 2.8M17.1 14.9l2.9.6M17.1 14.9l1 -2.8M6.9 14.9 4 15.5M6.9 14.9l-1-2.8M17.1 9.1l2.9-.6M17.1 9.1l1 2.8"/></g>',
  mushroom:
    '<path fill="currentColor" d="M12 3C7 3 3 6.7 3 11.2c0 .9.7 1.6 1.6 1.6h14.8c.9 0 1.6-.7 1.6-1.6C21 6.7 17 3 12 3Z"/><path fill="currentColor" opacity=".62" d="M9.2 14.2h5.6l.7 5.2A1.8 1.8 0 0 1 13.7 21h-3.4a1.8 1.8 0 0 1-1.8-1.6l.7-5.2Z"/><circle cx="9" cy="8" r="1.3" fill="var(--icon-hole,#fff)"/><circle cx="14.6" cy="7" r="1" fill="var(--icon-hole,#fff)"/>',
  moth:
    '<path fill="currentColor" d="M11.2 12 3.6 6.3C2.5 5.5 1.3 6.4 1.7 7.7l1.7 5.4c.4 1.3 1.7 2 3 1.6L11.2 13V12Zm1.6 0 7.6-5.7c1.1-.8 2.3.1 1.9 1.4l-1.7 5.4c-.4 1.3-1.7 2-3 1.6L12.8 13V12Z"/><path fill="currentColor" opacity=".7" d="m11 14.2-4 1.3 1.6 3.1c.5.9 1.8.8 2.2-.2l.2-4.2Zm2 0 4 1.3-1.6 3.1c-.5.9-1.8.8-2.2-.2l-.2-4.2Z"/><ellipse cx="12" cy="13" rx="1.2" ry="5" fill="currentColor"/>',
  fly:
    '<ellipse cx="12" cy="14.5" rx="3.4" ry="5.5" fill="currentColor"/><circle cx="12" cy="7.5" r="2.5" fill="currentColor"/><path fill="currentColor" opacity=".45" d="M9.5 11.5 2.6 8.6c-1-.4-1.9.7-1.3 1.6l3 4.5c.6.9 1.9 1 2.6.2l3.1-3.1Zm5 0 6.9-2.9c1-.4 1.9.7 1.3 1.6l-3 4.5c-.6.9-1.9 1-2.6.2l-3.1-3.1Z"/>',
  beetle:
    '<ellipse cx="12" cy="13.5" rx="6.4" ry="7.5" fill="currentColor"/><circle cx="12" cy="5.5" r="2.6" fill="currentColor"/><path d="M12 6.5v14.5M4 9.5 1.5 8M20 9.5 22.500 8M3.500 14H1M20.500 14H23M4.500 18 2.500 20M19.500 18l2 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/><path d="M12 7v14" stroke="var(--icon-hole,#fff)" stroke-width="1.100"/>',
  shield:
    '<path fill="currentColor" d="M12 2.500 4 5.500v6c0 5 3.300 9 8 10.500 4.700-1.500 8-5.500 8-10.500v-6l-8-3Z"/><path d="m8.300 12 2.600 2.600 4.800-5" fill="none" stroke="var(--icon-hole,#fff)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  check:
    '<path d="m5 12.500 4.500 4.500L19 7" fill="none" stroke="currentColor" stroke-width="2.600" stroke-linecap="round" stroke-linejoin="round"/>',
  moon:
    '<path fill="currentColor" d="M20 14.500A8.500 8.500 0 0 1 9.500 4a8.500 8.500 0 1 0 10.500 10.500Z"/>',
  leaf:
    '<path fill="currentColor" d="M20.500 3.500C11 3.500 4 8 4 15c0 1.600.5 3 1.300 4.200C7 14.500 10.500 11 15 9c-3.500 2.800-6.300 6.200-8.200 11.500l1.900.5c.4-1.100.8-2.100 1.300-3.100 1 .4 2 .6 3 .6 5.500 0 7.500-5.500 7.500-14.500Z"/>',
  spray:
    '<path fill="currentColor" d="M9 8h5a1 1 0 0 1 1 1v1.500c1.800.8 3 2.600 3 4.600V20a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2v-4.900c0-2 1.200-3.800 3-4.600V9a1 1 0 0 1-1-1Z"/><path fill="currentColor" d="M9.500 3h5.500l-1 3.500H9.500V3Z"/><circle cx="4" cy="3.500" r="1.100" fill="currentColor"/><circle cx="6.800" cy="5" r="1" fill="currentColor"/><circle cx="3.500" cy="6.800" r="1" fill="currentColor"/>',
  close:
    '<path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2.200" stroke-linecap="round"/>',
};

const MODEL_ICON = {
  frost: "frost",
  powdery_mildew: "mushroom",
  late_blight: "mushroom",
  codling_moth: "moth",
  cherry_fruit_fly: "fly",
  colorado_potato_beetle: "beetle",
  grapevine_moth: "moth",
};

function icon(name, size = 16) {
  return `<svg class="ic" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">${
    ICONS[name] || ""
  }</svg>`;
}

// ---------------------------------------------------------------------
// Scènes dessinées
// ---------------------------------------------------------------------

const PALETTES = {
  light: {
    winter: { sky: ["#cfdfeb", "#f1f6fa"], hill: "#b9cad6", ground: "#f4f7fa", shade: "#dfe7ed" },
    spring: { sky: ["#b4dff7", "#eefafd"], hill: "#b2daa0", ground: "#a2d373", shade: "#88c05a" },
    summer: { sky: ["#9ed8f7", "#e5f6fc"], hill: "#8fc77f", ground: "#7bbb55", shade: "#64a744" },
    autumn: { sky: ["#f4d4aa", "#fdf2e0"], hill: "#d6ba7e", ground: "#bdb058", shade: "#a49848" },
    cold: { sky: ["#94b8d4", "#d8e7f2"], hill: "#9db5c7", ground: "#e2ebf1", shade: "#c5d4de" },
    night: { sky: ["#101f38", "#2f4c78"], hill: "#1c3253", ground: "#a7bdd3", shade: "#83a0bb" },
  },
  dark: {
    winter: { sky: ["#18232d", "#2b3a47"], hill: "#222f3a", ground: "#4b5a64", shade: "#3a4851" },
    spring: { sky: ["#152c3b", "#2a4f60"], hill: "#244636", ground: "#4a7a41", shade: "#3b6535" },
    summer: { sky: ["#122b3b", "#27505e"], hill: "#204130", ground: "#41733a", shade: "#346030" },
    autumn: { sky: ["#2f2519", "#54412a"], hill: "#463a25", ground: "#6d6230", shade: "#595028" },
    cold: { sky: ["#16263a", "#33506d"], hill: "#1e3247", ground: "#5e7385", shade: "#4b5e6f" },
    night: { sky: ["#0b1526", "#253d61"], hill: "#14253f", ground: "#7d93a9", shade: "#62788f" },
  },
};

const FOLIAGE = {
  spring: ["#6fa83f", "#8cc34a", "#b0d96a"],
  summer: ["#3f7f32", "#559a3c", "#79b552"],
  autumn: ["#b8652a", "#d68e32", "#e8b84e"],
};

const TREE_SHAPES = {
  apple: { rx: 42, ry: 27, cy: 46, blossom: ["#ffffff", "#fbd5df", "#f39db4"], fruit: "#d8352f" },
  pear: { rx: 31, ry: 30, cy: 44, blossom: ["#ffffff", "#f6f4ea", "#d9d38d"], fruit: "#c9c544" },
  apricot: { rx: 43, ry: 25, cy: 48, blossom: ["#fff6f7", "#fbdfe4", "#f4a9ba"], fruit: "#f4932f" },
  plum: { rx: 37, ry: 29, cy: 45, blossom: ["#ffffff", "#f3f4ec", "#cfe0a6"], fruit: "#6a3a93" },
  peach: { rx: 43, ry: 24, cy: 49, blossom: ["#fbd3e0", "#f7a9c4", "#e96e9a"], fruit: "#f27a4e" },
  sweet_cherry: { rx: 38, ry: 30, cy: 44, blossom: ["#ffffff", "#fdeef2", "#f7c9d6"], fruit: "#a3122a" },
  generic: { rx: 30, ry: 26, cy: 50, blossom: ["#ffffff", "#f4f4f4", "#dddddd"], fruit: "#d8352f" },
};

const BARK = "#7a5a43";
const BARK_DARK = "#5e4432";

function rng(seed) {
  let state = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    state ^= seed.charCodeAt(i);
    state = Math.imul(state, 16777619);
  }
  return () => {
    state += 0x6d2b79f5;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const n1 = (value) => Math.round(value * 10) / 10;

function mixColor(from, to, ratio) {
  const parse = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const a = parse(from);
  const b = parse(to);
  const mixed = a.map((value, i) => Math.round(value + (b[i] - value) * clamp(ratio, 0, 1)));
  return `#${mixed.map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

/** Tronc et charpentière, avec l'extrémité des rameaux pour y poser le reste. */
function drawSkeleton(shape, rand) {
  const top = { x: 80, y: 74 };
  const tips = [];
  let branches = "";
  let twigs = "";
  for (const degrees of [-168, -132, -92, -52, -14]) {
    const angle = ((degrees + (rand() - 0.5) * 16) * Math.PI) / 180;
    const end = {
      x: 80 + shape.rx * 0.84 * Math.cos(angle),
      y: shape.cy + shape.ry * 0.84 * Math.sin(angle),
    };
    const control = {
      x: top.x + (end.x - top.x) * 0.3,
      y: top.y + (end.y - top.y) * 0.62,
    };
    branches += `M${top.x} ${top.y}Q${n1(control.x)} ${n1(control.y)} ${n1(end.x)} ${n1(end.y)}`;
    tips.push(end);
    for (const t of [0.55, 0.78]) {
      const px = (1 - t) ** 2 * top.x + 2 * (1 - t) * t * control.x + t ** 2 * end.x;
      const py = (1 - t) ** 2 * top.y + 2 * (1 - t) * t * control.y + t ** 2 * end.y;
      for (const side of [-1, 1]) {
        const spread = angle + side * (0.55 + rand() * 0.4);
        const length = 9 + rand() * 9;
        const tip = { x: px + Math.cos(spread) * length, y: py + Math.sin(spread) * length * 0.85 };
        twigs += `M${n1(px)} ${n1(py)}L${n1(tip.x)} ${n1(tip.y)}`;
        tips.push(tip);
      }
    }
  }
  const svg = `
    <ellipse cx="80" cy="98" rx="30" ry="4.500" fill="#000" opacity=".12"/>
    <path d="${twigs}" fill="none" stroke="${BARK}" stroke-width="1.700" stroke-linecap="round"/>
    <path d="${branches}" fill="none" stroke="${BARK}" stroke-width="3.600" stroke-linecap="round"/>
    <path d="M72.500 99C75.500 90 76 82 75 72.500 76.500 71 83.500 71 85 72.500 84 82 84.500 90 87.500 99 83 100.500 77 100.500 72.500 99Z" fill="${BARK}"/>
    <path d="M80.500 99C81 91 81 82 80.500 73 83 73 84 73 85 72.500 84 82 84.500 90 87.500 99 85 99.800 82.500 99.900 80.500 99Z" fill="${BARK_DARK}" opacity=".55"/>`;
  return { svg, tips };
}

/** Points répartis régulièrement dans la couronne, sans effet de grille. */
function crownPoints(shape, count, rand, tighten = 1) {
  const points = [];
  for (let i = 0; i < count; i += 1) {
    const radius = Math.sqrt((i + 0.5) / count) * tighten;
    const theta = i * 2.39996 + rand() * 0.5;
    points.push({
      x: 80 + shape.rx * radius * Math.cos(theta),
      y: shape.cy + shape.ry * radius * Math.sin(theta),
    });
  }
  return points;
}

function drawCanopy(shape, colors, rand, density = 1) {
  const [dark, mid, light] = colors;
  let out = "";
  if (density >= 0.8) {
    out += `<ellipse cx="80" cy="${shape.cy + 3}" rx="${shape.rx * 0.98}" ry="${shape.ry * 0.96}" fill="${dark}"/>`;
  }
  for (const p of crownPoints(shape, Math.round(16 * density), rand)) {
    out += `<circle cx="${n1(p.x)}" cy="${n1(p.y + 3)}" r="${n1(10 + rand() * 4)}" fill="${dark}"/>`;
  }
  for (const p of crownPoints(shape, Math.round(14 * density), rand, 0.9)) {
    out += `<circle cx="${n1(p.x - 2)}" cy="${n1(p.y - 2)}" r="${n1(8 + rand() * 3.500)}" fill="${mid}"/>`;
  }
  for (const p of crownPoints(shape, Math.round(9 * density), rand, 0.78)) {
    out += `<circle cx="${n1(p.x - 5)}" cy="${n1(p.y - 7)}" r="${n1(4.500 + rand() * 2.500)}" fill="${light}"/>`;
  }
  return out;
}

function drawLeafTips(tips, colors, rand, size = 1) {
  let out = "";
  for (const tip of tips) {
    const pairs = 1 + Math.round(rand());
    for (let i = 0; i < pairs; i += 1) {
      const angle = Math.round(rand() * 180);
      const color = colors[1 + Math.round(rand())];
      out += `<ellipse cx="${n1(tip.x + (rand() - 0.5) * 4)}" cy="${n1(tip.y + (rand() - 0.5) * 4)}" rx="${n1(3.400 * size)}" ry="${n1(1.800 * size)}" transform="rotate(${angle} ${n1(tip.x)} ${n1(tip.y)})" fill="${color}"/>`;
    }
  }
  return out;
}

function drawFlower(x, y, scale, petal, center) {
  let out = `<g transform="translate(${n1(x)} ${n1(y)}) scale(${n1(scale)})">`;
  for (let i = 0; i < 5; i += 1) {
    const angle = (i * 72 * Math.PI) / 180;
    out += `<circle cx="${n1(Math.cos(angle) * 1.800)}" cy="${n1(Math.sin(angle) * 1.800)}" r="1.500" fill="${petal}"/>`;
  }
  return `${out}<circle r=".9" fill="${center}"/></g>`;
}

function drawBlossom(shape, rand, withLeaves) {
  const [pale, tint, deep] = shape.blossom;
  let out = "";
  if (withLeaves) out += drawCanopy(shape, FOLIAGE.spring, rand, 0.5);
  for (const p of crownPoints(shape, 20, rand)) {
    out += `<circle cx="${n1(p.x)}" cy="${n1(p.y + 2)}" r="${n1(5.500 + rand() * 2.500)}" fill="${tint}"/>`;
  }
  for (const p of crownPoints(shape, 34, rand, 0.98)) {
    out += `<circle cx="${n1(p.x)}" cy="${n1(p.y)}" r="${n1(2.600 + rand() * 1.800)}" fill="${pale}"/>`;
  }
  for (const p of crownPoints(shape, 30, rand, 1.04)) {
    out += drawFlower(p.x, p.y, 0.8 + rand() * 0.45, rand() > 0.35 ? pale : tint, "#f0b92c");
  }
  for (const p of crownPoints(shape, 26, rand)) {
    out += `<circle cx="${n1(p.x)}" cy="${n1(p.y)}" r=".8" fill="${deep}"/>`;
  }
  return out;
}

function drawFruit(crop, x, y, size, color) {
  const shine = `<circle cx="${n1(x - size * 0.34)}" cy="${n1(y - size * 0.34)}" r="${n1(size * 0.26)}" fill="#fff" opacity=".55"/>`;
  const stem = `<path d="M${n1(x)} ${n1(y - size * 0.9)}q.6 ${n1(-size * 0.5)} ${n1(size * 0.45)} ${n1(-size * 0.7)}" stroke="${BARK_DARK}" stroke-width=".8" fill="none" stroke-linecap="round"/>`;
  if (crop === "pear") {
    return `${stem}<path d="M${n1(x)} ${n1(y - size * 1.25)}c${n1(size * 0.45)} 0 ${n1(size * 0.45)} ${n1(size * 0.65)} ${n1(size * 0.85)} ${n1(size * 1.15)}c${n1(size * 0.3)} ${n1(size * 0.6)} ${n1(-size * 0.2)} ${n1(size * 1)} ${n1(-size * 0.85)} ${n1(size * 1)}s${n1(-size * 1.15)} ${n1(-size * 0.4)} ${n1(-size * 0.85)} ${n1(-size * 1)}c${n1(size * 0.4)} ${n1(-size * 0.5)} ${n1(size * 0.4)} ${n1(-size * 1.15)} ${n1(size * 0.85)} ${n1(-size * 1.15)}Z" fill="${color}"/>${shine}`;
  }
  if (crop === "plum") {
    return `${stem}<ellipse cx="${n1(x)}" cy="${n1(y)}" rx="${n1(size * 0.82)}" ry="${n1(size * 1.05)}" fill="${color}"/>${shine}`;
  }
  if (crop === "sweet_cherry") {
    const gap = size * 0.85;
    return `<path d="M${n1(x - gap)} ${n1(y)}Q${n1(x - gap * 0.5)} ${n1(y - size * 2)} ${n1(x)} ${n1(y - size * 2.200)}Q${n1(x + gap * 0.6)} ${n1(y - size * 1.700)} ${n1(x + gap)} ${n1(y + size * 0.2)}" stroke="#5f7d33" stroke-width=".8" fill="none"/><circle cx="${n1(x - gap)}" cy="${n1(y)}" r="${n1(size * 0.85)}" fill="${color}"/><circle cx="${n1(x + gap)}" cy="${n1(y + size * 0.2)}" r="${n1(size * 0.85)}" fill="${color}"/><circle cx="${n1(x - gap - size * 0.3)}" cy="${n1(y - size * 0.3)}" r="${n1(size * 0.22)}" fill="#fff" opacity=".6"/>`;
  }
  if (crop === "apricot" || crop === "peach") {
    return `${stem}<circle cx="${n1(x)}" cy="${n1(y)}" r="${n1(size)}" fill="${color}"/><path d="M${n1(x)} ${n1(y - size)}q${n1(size * 0.5)} ${n1(size)} 0 ${n1(size * 2)}" stroke="#000" stroke-opacity=".16" stroke-width=".7" fill="none"/>${shine}`;
  }
  return `${stem}<circle cx="${n1(x)}" cy="${n1(y)}" r="${n1(size)}" fill="${color}"/>${shine}`;
}

function drawFruits(crop, shape, growth, rand) {
  const unripe = "#9fc24f";
  const ripeness = clamp((growth.ripeness - 0.45) / 0.5, 0, 1);
  const color = mixColor(unripe, shape.fruit, ripeness);
  const size = 1.700 + clamp(growth.ripeness, 0, 1) * 2.300;
  let out = "";
  for (const p of crownPoints(shape, crop === "sweet_cherry" ? 9 : 11, rand, 0.88)) {
    out += drawFruit(crop, p.x, p.y + 3, size, color);
  }
  if (growth.phase === "ripe" && growth.ripeness >= 0.95) {
    out += drawFruit(crop, 56 + rand() * 6, 99, size, color);
    out += drawFruit(crop, 101 + rand() * 7, 100, size, color);
  }
  return out;
}

function drawFruitTree(tree, rand) {
  const shape = TREE_SHAPES[tree.crop] || TREE_SHAPES.generic;
  const { svg: skeleton, tips } = drawSkeleton(shape, rand);
  const growth = tree.growth;
  let top = "";
  switch (growth.phase) {
    case "bud":
      for (const tip of tips) {
        top += `<circle cx="${n1(tip.x)}" cy="${n1(tip.y)}" r="1.700" fill="${rand() > 0.5 ? "#a6c26b" : "#c9b98a"}"/>`;
      }
      break;
    case "leaf":
      top += drawLeafTips(tips, FOLIAGE.spring, rand, 1.15);
      break;
    case "flowerbud":
      top += drawLeafTips(tips, FOLIAGE.spring, rand, 1);
      for (const tip of tips) {
        top += `<circle cx="${n1(tip.x + 1.500)}" cy="${n1(tip.y - 1.500)}" r="2.300" fill="${shape.blossom[2]}"/><circle cx="${n1(tip.x + 1)}" cy="${n1(tip.y - 2)}" r="1.100" fill="${shape.blossom[1]}"/>`;
      }
      break;
    case "bloom":
      top += drawBlossom(shape, rand, tree.crop === "apple" || tree.crop === "pear");
      break;
    case "fruitlet":
      top += drawCanopy(shape, FOLIAGE.spring, rand, 0.9);
      top += drawFruits(tree.crop, shape, Object.assign({}, growth, { ripeness: Math.min(growth.ripeness, 0.15) }), rand);
      break;
    case "fruit":
    case "ripe":
      top += drawCanopy(shape, FOLIAGE.summer, rand, 1);
      top += drawFruits(tree.crop, shape, growth, rand);
      break;
    case "autumn":
      top += drawCanopy(shape, FOLIAGE.autumn, rand, 0.5);
      for (let i = 0; i < 7; i += 1) {
        const x = 46 + rand() * 68;
        top += `<ellipse cx="${n1(x)}" cy="${n1(92 + rand() * 11)}" rx="2.400" ry="1.200" fill="${FOLIAGE.autumn[Math.floor(rand() * 3)]}" transform="rotate(${Math.round(rand() * 60 - 30)} ${n1(x)} 96)"/>`;
      }
      break;
    default:
      break;
  }
  return skeleton + top;
}

function drawVine(tree, rand) {
  const growth = tree.growth;
  const post = (x) =>
    `<rect x="${x - 1.800}" y="44" width="3.600" height="56" rx="1" fill="#8f7355"/><rect x="${x - 1.800}" y="44" width="1.400" height="56" rx=".7" fill="#a78c6c"/>`;
  let out = `<ellipse cx="80" cy="99" rx="46" ry="4" fill="#000" opacity=".1"/>${post(30)}${post(130)}
    <path d="M30 56H130M30 72H130" stroke="#8d9aa3" stroke-width=".8"/>
    <path d="M75 100C77 92 79 84 78 73 79 72 82 72 83 73 82 84 83 92 86 100Z" fill="${BARK}"/>
    <path d="M80 75C70 72 56 73 38 72M81 75C92 72 106 73 123 72" fill="none" stroke="${BARK}" stroke-width="3" stroke-linecap="round"/>`;
  const spurs = [44, 56, 68, 92, 104, 116];
  if (growth.phase === "rest") {
    for (const x of spurs) {
      out += `<path d="M${x} 72l-1 -7" stroke="${BARK}" stroke-width="1.700" stroke-linecap="round"/>`;
    }
  } else if (growth.phase === "bud") {
    for (const x of spurs) {
      out += `<path d="M${x} 72l-1 -7" stroke="${BARK}" stroke-width="1.700" stroke-linecap="round"/><circle cx="${x - 1}" cy="64.500" r="2" fill="#a6c26b"/>`;
    }
  } else if (growth.phase === "leaf") {
    for (const x of spurs) {
      out += `<path d="M${x} 72q-1 -9 1 -18" stroke="#7fa13f" stroke-width="1.300" fill="none" stroke-linecap="round"/>`;
      out += `<ellipse cx="${x - 3}" cy="62" rx="4" ry="2.800" fill="${FOLIAGE.spring[1]}" transform="rotate(-25 ${x} 62)"/><ellipse cx="${x + 3.500}" cy="56" rx="4.200" ry="2.900" fill="${FOLIAGE.spring[2]}" transform="rotate(20 ${x} 56)"/>`;
    }
  } else {
    const colors = growth.phase === "autumn" ? FOLIAGE.autumn : FOLIAGE.summer;
    for (let i = 0; i < 26; i += 1) {
      const x = 36 + (i / 25) * 88 + (rand() - 0.5) * 4;
      out += `<circle cx="${n1(x)}" cy="${n1(54 + rand() * 13)}" r="${n1(6 + rand() * 3)}" fill="${colors[Math.floor(rand() * 2)]}"/>`;
    }
    for (let i = 0; i < 18; i += 1) {
      const x = 38 + rand() * 84;
      out += `<circle cx="${n1(x)}" cy="${n1(48 + rand() * 12)}" r="${n1(3 + rand() * 2)}" fill="${colors[2]}"/>`;
    }
    if (growth.phase !== "autumn" && growth.ripeness > 0.1) {
      const color = mixColor("#a5c75a", "#4d2d70", clamp((growth.ripeness - 0.45) / 0.45, 0, 1));
      for (const x of [46, 66, 96, 116]) {
        const y = 73;
        out += `<path d="M${x} ${y - 4}v4" stroke="#6f8a35" stroke-width=".8"/>`;
        for (const [dx, dy] of [[-3, 0], [0, 0], [3, 0], [-1.500, 2.600], [1.500, 2.600], [0, 5.200]]) {
          out += `<circle cx="${x + dx}" cy="${y + dy}" r="1.900" fill="${color}"/>`;
        }
        out += `<circle cx="${x - 1}" cy="${y - 0.6}" r=".6" fill="#fff" opacity=".6"/>`;
      }
    }
  }
  return out;
}

function drawBed() {
  return `<path d="M22 100C34 91 126 91 138 100 124 106 36 106 22 100Z" fill="#6f523d"/>
    <path d="M30 99C46 95 114 95 130 99" fill="none" stroke="#88694f" stroke-width="1.200" stroke-linecap="round"/>`;
}

function drawTomato(tree, rand) {
  const size = tree.growth.ripeness;
  let out = drawBed();
  if (tree.growth.phase === "rest") {
    for (let i = 0; i < 26; i += 1) {
      const x = 32 + rand() * 96;
      const y = 95 + rand() * 7;
      const angle = rand() * 60 - 30;
      out += `<path d="M${n1(x - 4)} ${n1(y)}h8" stroke="${i % 2 ? "#d9c083" : "#c4a968"}" stroke-width="1.100" stroke-linecap="round" transform="rotate(${n1(angle)} ${n1(x)} ${n1(y)})"/>`;
    }
    return `${out}<rect x="111" y="78" width="2.400" height="20" rx="1" fill="#8f7355"/><rect x="104" y="72" width="17" height="10" rx="1.500" fill="#b89b72"/><path d="M107 75.500h11M107 78.500h7" stroke="#8f7355" stroke-width=".9" stroke-linecap="round"/>`;
  }
  for (const x of [56, 104]) {
    const height = 20 + size * 50;
    out += `<rect x="${x - 1}" y="${n1(96 - height - 5)}" width="2" height="${n1(height + 7)}" rx="1" fill="#b89b72"/>`;
    const width = 7 + size * 11;
    for (const [layer, count, radius] of [[0, 15, 5.500], [1, 13, 4.200], [2, 8, 2.800]]) {
      for (let i = 0; i < count; i += 1) {
        const level = (i + 0.5) / count;
        const taper = 0.45 + 0.55 * Math.sin(Math.PI * Math.min(1, level * 1.15 + 0.08));
        const px = x + (rand() * 2 - 1) * width * taper;
        const py = 96 - level * height + (rand() - 0.5) * 3 - layer;
        out += `<circle cx="${n1(px)}" cy="${n1(py)}" r="${n1(radius * (0.65 + size * 0.45))}" fill="${FOLIAGE.summer[layer]}"/>`;
      }
    }
    if (size > 0.45) {
      const color = mixColor("#a7c957", "#e23a28", clamp((size - 0.6) / 0.3, 0, 1));
      for (let i = 0; i < 7; i += 1) {
        const level = (i + 0.5) / 7;
        const px = x + (i % 2 ? 1 : -1) * (2 + rand() * width * 0.7);
        const py = 93 - level * height * 0.85;
        out += `<circle cx="${n1(px)}" cy="${n1(py)}" r="3" fill="${color}"/><circle cx="${n1(px - 1)}" cy="${n1(py - 1)}" r=".8" fill="#fff" opacity=".6"/>`;
      }
    }
  }
  return out;
}

function drawPotato(tree, rand) {
  const size = tree.growth.ripeness;
  let out = "";
  for (const x of [42, 80, 118]) {
    out += `<path d="M${x - 20} 101C${x - 12} 88 ${x + 12} 88 ${x + 20} 101Z" fill="#7a5b43"/><path d="M${x - 12} 95C${x - 6} 90 ${x + 6} 90 ${x + 12} 95" fill="none" stroke="#927258" stroke-width="1.100"/>`;
    if (tree.growth.phase === "rest") continue;
    const radius = 4 + size * 11;
    const top = 86 - size * 8;
    for (const [layer, count, blob] of [[0, 12, 5], [1, 11, 3.800], [2, 7, 2.600]]) {
      for (let i = 0; i < count; i += 1) {
        const angle = rand() * Math.PI * 2;
        const distance = Math.sqrt(rand()) * radius;
        out += `<circle cx="${n1(x + Math.cos(angle) * distance)}" cy="${n1(top + Math.sin(angle) * distance * 0.72 - layer)}" r="${n1(blob * (0.7 + size * 0.5))}" fill="${FOLIAGE.spring[layer]}"/>`;
      }
    }
    if (size > 0.4) {
      for (let i = 0; i < 4; i += 1) {
        out += drawFlower(x + (rand() - 0.5) * 18, top - 8 + rand() * 9, 0.9, "#ffffff", "#f0b92c");
      }
    }
  }
  return out;
}

function drawCabbages(rand) {
  let out = drawBed();
  for (const x of [50, 80, 110]) {
    const y = 88;
    out += `<circle cx="${x}" cy="${y}" r="12.500" fill="${FOLIAGE.summer[0]}"/>`;
    for (let i = 0; i < 6; i += 1) {
      const angle = (i * 60 * Math.PI) / 180 + rand();
      out += `<circle cx="${n1(x + Math.cos(angle) * 6)}" cy="${n1(y + Math.sin(angle) * 5)}" r="6.500" fill="${FOLIAGE.summer[1]}"/>`;
    }
    out += `<circle cx="${x}" cy="${y - 1}" r="6" fill="${FOLIAGE.spring[2]}"/><path d="M${x} ${y - 7}q3 6 0 12" stroke="${FOLIAGE.summer[1]}" stroke-width=".9" fill="none"/>`;
  }
  return out;
}

function drawGeneric(tree, rand) {
  const shape = TREE_SHAPES.generic;
  const { svg, tips } = drawSkeleton(shape, rand);
  if (tree.seasonWinter) return svg;
  return svg + (tips.length ? drawCanopy(shape, FOLIAGE.spring, rand, 0.8) : "");
}

function sceneSeason(tree) {
  const phase = tree.growth.phase;
  if (phase === "rest") return "winter";
  if (phase === "autumn") return "autumn";
  if (phase === "fruit" || phase === "ripe") return "summer";
  if (tree.crop === "generic" || tree.crop === "hardy_vegetable") {
    return tree.seasonWinter ? "winter" : "summer";
  }
  if (phase === "plant") return tree.growth.ripeness > 0.35 ? "summer" : "spring";
  return "spring";
}

function drawFlake(x, y, size, delay, duration) {
  const arms = [0, 60, 120]
    .map((angle) => `<path d="M0 ${-size}V${size}" transform="rotate(${angle})"/>`)
    .join("");
  return `<g transform="translate(${n1(x)} ${n1(y)})"><g class="flake" style="animation-delay:${delay}s;animation-duration:${duration}s" stroke="#fff" stroke-width="1" stroke-linecap="round">${arms}</g></g>`;
}

function drawMushroom(x, y, size, cap) {
  return `<g transform="translate(${x} ${y}) scale(${size})">
    <ellipse cx="0" cy="1" rx="6" ry="1.500" fill="#000" opacity=".16"/>
    <path d="M-2.300 -5C-2 -2-2.700 0-3 1 -1 1.800 1 1.800 3 1 2.700 0 2 -2 2.300 -5Z" fill="#f4ead6"/>
    <path d="M-7.500 -4.500C-7.500 -9.500 -3.800 -12 0 -12S7.500 -9.500 7.500 -4.500C7.500 -3.400 6.700 -3 5.600 -3H-5.600C-6.700 -3-7.500 -3.400-7.500 -4.500Z" fill="${cap}"/>
    <circle cx="-3" cy="-7.500" r="1.500" fill="#fff" opacity=".92"/><circle cx="2.400" cy="-9" r="1.200" fill="#fff" opacity=".92"/><circle cx="3.700" cy="-5.300" r="1" fill="#fff" opacity=".92"/>
  </g>`;
}

function drawMoth(x, y, size, delay) {
  return `<g transform="translate(${x} ${y}) scale(${size})"><g class="flutter" style="animation-delay:${delay}s">
    <path d="M-.6 0-8-4.500C-9-5-9.800-4.200-9.400-3.200L-7.500 1.800C-7.100 2.800-6 3.100-5.100 2.600L-.6 .8Z" fill="#8a6d4d"/>
    <path d="M.6 0 8-4.500C9-5 9.800-4.200 9.400-3.200L7.500 1.800C7.100 2.800 6 3.100 5.100 2.600L.6 .8Z" fill="#8a6d4d"/>
    <path d="M-.6 .8-4.800 2.800-3.300 6C-2.900 6.800-1.800 6.700-1.500 5.800Z" fill="#b4966f"/><path d="M.6 .8 4.800 2.800 3.300 6C2.900 6.800 1.800 6.700 1.500 5.800Z" fill="#b4966f"/>
    <circle cx="-6" cy="-1.400" r="1" fill="#e7d5b6"/><circle cx="6" cy="-1.400" r="1" fill="#e7d5b6"/>
    <ellipse cx="0" cy="1" rx="1.100" ry="4.200" fill="#4a3a29"/>
  </g></g>`;
}

function drawFly(x, y, size, delay) {
  return `<g transform="translate(${x} ${y}) scale(${size})"><g class="flutter" style="animation-delay:${delay}s">
    <path d="M-1 -1-8-3.500C-9-3.800-9.600-2.800-9-2L-4.500 2.500C-3.800 3.200-2.700 3-2.200 2.200Z" fill="#cfe3ee" opacity=".92"/><path d="M1 -1 8-3.500C9-3.800 9.600-2.800 9-2L4.500 2.500C3.800 3.200 2.700 3 2.200 2.200Z" fill="#cfe3ee" opacity=".92"/>
    <ellipse cx="0" cy="1.500" rx="2.500" ry="4.200" fill="#23201c"/><circle cx="0" cy="-3.200" r="2" fill="#23201c"/><circle cx="-1" cy="-3.800" r=".6" fill="#d33"/><circle cx="1" cy="-3.800" r=".6" fill="#d33"/>
  </g></g>`;
}

function drawBeetle(x, y, size) {
  return `<g transform="translate(${x} ${y}) scale(${size})">
    <path d="M-5-3-8-5M5-3 8-5M-6 0H-9M6 0H9M-5 3-8 5M5 3 8 5" stroke="#2d241b" stroke-width="1" stroke-linecap="round"/>
    <circle cx="0" cy="-5.500" r="2.500" fill="#d9822b"/>
    <ellipse cx="0" cy="0" rx="6" ry="6.500" fill="#f0c24a"/>
    <path d="M-3.800 -4.500V4.500M-1.300 -6V6M1.300 -6V6M3.800 -4.500V4.500" stroke="#2d241b" stroke-width="1.100"/>
  </g>`;
}

const MUSHROOM_CAPS = { watch: "#e8a200", warning: "#ee6c10", severe: "#d32f2f" };

/** Ce qui menace la plante, dessiné dans sa scène. */
function drawHazards(tree, rand, canopyPoints) {
  let back = "";
  let front = "";
  for (const risk of tree.risks) {
    const rankValue = rank(risk.level);
    if (!rankValue) continue;
    if (risk.model === "frost") {
      const count = [0, 5, 9, 14][rankValue];
      for (let i = 0; i < count; i += 1) {
        back += drawFlake(10 + rand() * 140, 8 + rand() * 52, 2 + rand() * 1.800, n1(rand() * 3), n1(3 + rand() * 3));
      }
    } else if (DISEASES.includes(risk.model)) {
      const cap = MUSHROOM_CAPS[risk.level];
      const spot = risk.model === "powdery_mildew" ? "#ffffff" : "#5c3a1e";
      const spots = [0, 8, 14, 22][rankValue];
      if (canopyPoints.length) {
        for (let i = 0; i < spots; i += 1) {
          const p = canopyPoints[Math.floor(rand() * canopyPoints.length)];
          front += `<circle cx="${n1(p.x + (rand() - 0.5) * 10)}" cy="${n1(p.y + (rand() - 0.5) * 10)}" r="${n1(1 + rand() * 1.400)}" fill="${spot}" opacity=".82"/>`;
        }
      }
      const offset = risk.model === "powdery_mildew" ? 0 : 1;
      if (offset === 0) {
        front += drawMushroom(50, 101, 0.92 + rankValue * 0.14, cap);
        if (rankValue >= 2) front += drawMushroom(38, 103, 0.72, cap);
        if (rankValue >= 3) front += drawMushroom(62, 104, 0.6, cap);
      } else {
        front += drawMushroom(110, 101, 0.92 + rankValue * 0.14, cap);
        if (rankValue >= 2) front += drawMushroom(122, 103, 0.72, cap);
        if (rankValue >= 3) front += drawMushroom(98, 104, 0.6, cap);
      }
    } else if (risk.model === "colorado_potato_beetle") {
      front += drawBeetle(62, 78, 0.85);
      if (rankValue >= 2) front += drawBeetle(100, 74, 0.8);
      if (rankValue >= 3) front += drawBeetle(82, 90, 0.75);
    } else if (risk.model === "cherry_fruit_fly") {
      front += drawFly(145, 46, 1.450, 0);
      if (rankValue >= 2) front += drawFly(15, 54, 1.300, 0.5);
      if (rankValue >= 3) front += drawFly(147, 77, 1.150, 1);
    } else {
      front += drawMoth(145, 46, 1.150, 0);
      if (rankValue >= 2) front += drawMoth(15, 54, 1.050, 0.6);
      if (rankValue >= 3) front += drawMoth(147, 76, 0.95, 1.100);
    }
  }
  return { back, front };
}

function drawScene(tree, dark, index) {
  const rand = rng(String(tree.key));
  const frost = tree.risks.find((risk) => risk.model === "frost");
  const frostRank = rank(frost ? frost.level : "none");
  const paletteSet = dark ? PALETTES.dark : PALETTES.light;
  const name = frostRank >= 2 ? "night" : frostRank === 1 ? "cold" : sceneSeason(tree);
  const palette = paletteSet[name];
  const shape = TREE_SHAPES[tree.crop];

  let plant;
  if (tree.crop === "vine") plant = drawVine(tree, rand);
  else if (tree.crop === "tender_annual") plant = drawTomato(tree, rand);
  else if (tree.crop === "potato") plant = drawPotato(tree, rand);
  else if (tree.crop === "hardy_vegetable") plant = drawCabbages(rand);
  else if (tree.crop === "generic") plant = drawGeneric(tree, rand);
  else plant = drawFruitTree(tree, rand);

  const hasCanopy = shape && !["rest", "bud"].includes(tree.growth.phase);
  const canopy = hasCanopy ? crownPoints(shape, 24, rand, 0.9) : tree.crop === "vine" ? [{ x: 60, y: 55 }, { x: 100, y: 55 }, { x: 80, y: 58 }] : [{ x: 58, y: 70 }, { x: 102, y: 70 }];
  const hazards = drawHazards(tree, rand, canopy);

  const sun =
    name === "night"
      ? `<path d="M126 13A9.500 9.500 0 1 0 139 26 8 8 0 0 1 126 13Z" fill="#f4f1dc"/>
         ${[[24, 16], [50, 10], [70, 24], [104, 12], [146, 40], [14, 36]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r=".8" fill="#fff" opacity=".85"/>`).join("")}`
      : name === "cold"
        ? `<circle cx="134" cy="20" r="9" fill="#fff" opacity=".6"/>`
        : name === "winter"
          ? `<circle cx="24" cy="20" r="9" fill="#fff" opacity="${dark ? 0.25 : 0.8}"/>`
          : `<circle cx="24" cy="20" r="9" fill="#ffd968" opacity="${dark ? 0.7 : 1}"/><circle cx="24" cy="20" r="14" fill="#ffd968" opacity=".22"/>
             <g fill="#fff" opacity="${dark ? 0.16 : 0.85}"><ellipse cx="128" cy="24" rx="13" ry="4.500"/><ellipse cx="138" cy="21" rx="9" ry="4.500"/><ellipse cx="120" cy="22" rx="7" ry="3.500"/></g>`;

  const id = `sky${index}`;
  return `<svg class="scene" viewBox="0 0 160 110" preserveAspectRatio="xMidYMax slice" role="img" aria-hidden="true">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${palette.sky[0]}"/><stop offset="1" stop-color="${palette.sky[1]}"/></linearGradient></defs>
    <rect width="160" height="110" fill="url(#${id})"/>
    ${sun}
    <path d="M0 74C22 62 48 66 76 72 104 78 134 62 160 70V110H0Z" fill="${palette.hill}"/>
    <path d="M0 91C38 85 118 86 160 92V110H0Z" fill="${palette.ground}"/>
    <path d="M0 100C44 95 116 97 160 102V110H0Z" fill="${palette.shade}"/>
    <g transform="translate(80 100) scale(1.1) translate(-80 -100)">${plant}</g>
    ${hazards.front}
    ${hazards.back}
  </svg>`;
}

// ---------------------------------------------------------------------
// Rendu
// ---------------------------------------------------------------------

function renderBanner(hass, view) {
  const { s, alerts, calm } = view;
  if (calm) {
    const kind = calm.kind === "rest" ? "rest" : "ok";
    return `<div class="banner ${kind}">
      <div class="banner-icon">${icon(kind === "rest" ? "moon" : "check", 22)}</div>
      <div class="banner-body">
        <div class="banner-title">${esc(calm.title)}</div>
        <div class="banner-text">${esc(calm.text)}${calm.next ? ` ${esc(calm.next)}` : ""}</div>
      </div>
    </div>`;
  }
  if (!alerts.length) return "";
  const [first, ...others] = alerts;
  const rows = others
    .slice(0, 2)
    .map(
      (alert) => `<div class="minor lv-${alert.level}">
        ${icon(alert.protected ? "shield" : MODEL_ICON[alert.model], 15)}
        <span class="minor-title">${esc(alert.title)}</span>
        <span class="minor-names">${esc(alert.names)}</span>
      </div>`
    )
    .join("");
  const more =
    others.length > 2
      ? `<div class="minor-more">${esc(others.length === 3 ? s.others_one : fill(s.others, { count: others.length - 2 }))}</div>`
      : "";
  return `<div class="alerts">
    <div class="banner lv-${first.level}">
      <div class="banner-icon">${icon(first.protected ? "shield" : MODEL_ICON[first.model], 22)}</div>
      <div class="banner-body">
        <div class="banner-eyebrow"><span class="pill">${esc(s.levels[first.level])}</span><span class="banner-names">${esc(first.names)}</span></div>
        <div class="banner-title">${esc(first.title)}</div>
        <div class="banner-text">${esc(first.text)}</div>
        ${first.action ? `<div class="banner-action">${esc(first.action)}</div>` : ""}
      </div>
    </div>
    ${rows}${more}
  </div>`;
}

function renderChip(s, risk) {
  const label = s.models[risk.model] || risk.model;
  const iconName = risk.protectedNow ? "shield" : MODEL_ICON[risk.model];
  return `<span class="chip lv-${risk.level}" title="${esc(label)} · ${esc(s.levels[risk.level])}">${icon(iconName, 13)}<span>${esc(label)}</span></span>`;
}

function renderTile(hass, view, tree, index, selected, dark) {
  const { s } = view;
  const active = tree.risks.filter((risk) => risk.level !== "none");
  const frost = tree.risks.find((risk) => risk.model === "frost");
  const showFrost = frost && rank(frost.level) > 0 && isNumber(frost.attributes.reference_min);
  const shieldOn = tree.risks.some((risk) => risk.protectedNow);
  const sub = [];
  if (tree.showCrop) sub.push(tree.cropLabel);
  if (tree.stageLabel) sub.push(tree.stageLabel);

  const chips = active.length
    ? `<span class="chips">${active.slice(0, 2).map((risk) => renderChip(s, risk)).join("")}${
        active.length > 2 ? `<span class="chip more">+${active.length - 2}</span>` : ""
      }</span>`
    : "";

  const harvest = tree.growth.remaining
    ? `<div class="tile-note">${esc(fill(s.harvestIn, { days: tree.growth.remaining }))}</div>`
    : "";

  return `<button class="tile lv-${LEVELS[tree.worst]} ${selected ? "selected" : ""}" data-tree="${esc(tree.key)}" aria-expanded="${selected}">
    <span class="vignette">
      ${drawScene(tree, dark, index)}
      ${showFrost ? `<span class="temp">${icon("frost", 12)}${esc(formatNumber(hass, frost.attributes.reference_min))}°</span>` : ""}
      ${shieldOn ? `<span class="shield" title="${esc(s.protected_short)}">${icon("shield", 15)}</span>` : ""}
    </span>
    <span class="tile-body">
      <span class="tile-title">${esc(tree.title)}</span>
      <span class="tile-sub">${esc(sub.join(" · "))}</span>
      ${harvest}
      ${chips}
    </span>
  </button>`;
}

/** Hauteur et teinte d'une barre de sensibilité au gel, selon le seuil T10. */
function sensitivity(t10) {
  if (!isNumber(t10)) return { ratio: 0.05, color: "var(--divider-color)" };
  const ratio = clamp(1 + t10 / 12, 0.06, 1);
  const hue = Math.round(205 - 205 * ratio);
  return { ratio, color: `hsl(${hue}, 70%, 52%)` };
}

function renderPath(hass, s, tree) {
  if (!tree.path.length) return "";
  const steps = tree.path.map((step) => ({
    key: step.key,
    label: stageLabel(hass, tree.stageState, step.key),
    t10: step.t10,
  }));
  const hasFruit = isNumber(attrs(tree.stageState).bloom_to_harvest_days);
  if (hasFruit) {
    const lastT10 = steps[steps.length - 1].t10;
    steps.push({ key: "__fruit", label: s.growth.fruit, t10: lastT10 });
    steps.push({ key: "__harvest", label: s.growth.harvest, t10: lastT10 });
  }
  let current = steps.findIndex((step) => step.key === tree.stageKey);
  if (hasFruit && ["fruit"].includes(tree.growth.phase)) current = steps.length - 2;
  if (hasFruit && ["ripe", "autumn"].includes(tree.growth.phase)) current = steps.length - 1;

  const bars = steps
    .map((step, index) => {
      const { ratio, color } = sensitivity(step.t10);
      const state = index < current ? "past" : index === current ? "now" : "future";
      return `<span class="step ${state}" title="${esc(step.label)}"><span class="step-bar" style="height:${Math.round(ratio * 100)}%;background:${color}"></span></span>`;
    })
    .join("");

  const here = [];
  if (isNumber(tree.t10)) {
    here.push(fill(s.stage_here, { t10: formatNumber(hass, tree.t10) }));
  }
  if (tree.next && !tree.growth.growth) {
    here.push(
      fill(s.next_stage, {
        stage: tree.next.label,
        when: tree.next.when,
      })
    );
  }

  // Une annuelle n'a qu'un stade : un graphique n'y apprendrait rien.
  const chart =
    steps.length > 2
      ? `<div class="path">${bars}</div>
    <div class="path-ends"><span>${esc(steps[0].label)}</span><span>${esc(steps[steps.length - 1].label)}</span></div>`
      : "";

  const options = tree.path
    .map(
      (step) =>
        `<option value="${esc(step.key)}" ${step.key === tree.stageKey ? "selected" : ""}>${esc(stageLabel(hass, tree.stageState, step.key))}</option>`
    )
    .join("");
  const picker = options
    ? `<label class="picker"><span class="section-title">${esc(s.observed_stage)}</span>
      <select data-stage data-sub="${esc(tree.subentryId)}">${options}</select></label>
    <div class="muted small">${esc(s.observed_help)}</div>`
    : "";

  return `<section class="section">
    <div class="section-title">${esc(s.season_path)}</div>
    ${chart}
    <div class="path-now">${esc(tree.stageLabel)}</div>
    ${here.length ? `<div class="muted">${esc(here.join(" "))}</div>` : ""}
    ${chart ? `<div class="muted small">${esc(s.frost_sensitivity)}</div>` : ""}
    ${picker}
  </section>`;
}

function renderFrostGauge(hass, s, risk) {
  const a = risk.attributes;
  const min = a.reference_min;
  if (!isNumber(min) || !isNumber(a.t10)) return "";
  const t90 = isNumber(a.t90) ? a.t90 : a.t10 - 3;
  const low = Math.min(t90, min) - 3;
  const high = Math.max(a.t10 + 8, min + 3);
  const pct = (value) => ((clamp(value, low, high) - low) / (high - low)) * 100;
  const segments = [
    [low, t90, "severe"],
    [t90, a.t10, "warning"],
    [a.t10, a.t10 + 2, "watch"],
    [a.t10 + 2, high, "ok"],
  ]
    .map(
      ([from, to, kind]) =>
        `<span class="g-seg g-${kind}" style="left:${pct(from)}%;width:${pct(to) - pct(from)}%"></span>`
    )
    .join("");
  const position = pct(min);
  const align = position > 70 ? "right" : position < 30 ? "left" : "center";
  return `<div class="gauge">
    <div class="gauge-label ${align}" style="left:${position}%">${esc(fill(s.gauge_min, { temp: formatNumber(hass, min) }))}</div>
    <div class="gauge-track">${segments}<span class="gauge-mark" style="left:${position}%"></span></div>
    <div class="gauge-ticks">
      <span style="left:${pct(t90)}%">${esc(formatNumber(hass, t90))}°</span>
      <span style="left:${pct(a.t10)}%">${esc(formatNumber(hass, a.t10))}°</span>
    </div>
    <div class="muted small">${esc(formatNumber(hass, a.t10))}° : ${esc(s.gauge_t10)} · ${esc(formatNumber(hass, t90))}° : ${esc(s.gauge_t90)}</div>
  </div>`;
}

function renderCycle(hass, s, tree, risk, gddState) {
  const a = risk.attributes;
  const stages = a.stages || [];
  if (!stages.length) return "";
  const index = stages.findIndex((step) => step.stage === a.cycle_stage);
  const segments = stages
    .map((step, i) => {
      const state = i === index ? "now" : i < index ? "past" : "future";
      const label = s.cycle[step.stage] || step.stage;
      return `<span class="cycle-seg lv-${step.level} ${state}" title="${esc(label)}"></span>`;
    })
    .join("");
  const notes = [];
  if (tree.resting) {
    notes.push(s.diapause);
  } else if (a.awaiting_biofix) {
    notes.push(s.waiting_biofix);
  } else {
    if (a.biofix_date) {
      notes.push(
        fill(a.biofix_estimated ? s.estimated_biofix : s.declared_biofix, {
          date: formatDate(hass, a.biofix_date),
        })
      );
    }
    if (a.next_cycle_stage && isNumber(a.dd_to_next_cycle_stage)) {
      notes.push(
        fill(s.next_cycle, {
          stage: (s.cycle[a.next_cycle_stage] || a.next_cycle_stage).toLowerCase(),
          when: formatDelay(
            hass,
            s,
            a.dd_to_next_cycle_stage,
            dailySpeed(gddState, orElse(a.base_temperature, GDD_BASE))
          ),
        })
      );
    }
  }
  return `<div class="cycle">${segments}</div>
    ${a.cycle_stage ? `<div class="path-now">${esc(s.cycle[a.cycle_stage] || a.cycle_stage)}</div>` : ""}
    ${notes.length ? `<div class="muted">${esc(notes.join(" "))}</div>` : ""}`;
}

function renderDisease(hass, s, tree, risk) {
  const a = risk.attributes;
  if (tree.resting) return `<div class="muted">${esc(s.paused)}</div>`;
  if (risk.model === "powdery_mildew") {
    const index = clamp(a.index || 0, 0, 100);
    return `<div class="meter" role="img" aria-label="${esc(fill(s.index_band, { index }))}"><span class="meter-fill lv-${risk.level}" style="width:${index}%"></span><span class="meter-tick" style="left:30%"></span><span class="meter-tick" style="left:60%"></span></div>
      <div class="muted">${esc(fill(s.index_band, { index }))}${a.spray_interval_days ? esc(fill(s.mildew_interval, { days: a.spray_interval_days })) : ""}</div>`;
  }
  const days = clamp(a.hutton_consecutive_days || 0, 0, 2);
  return `<div class="dots">${[0, 1].map((i) => `<span class="dot ${i < days ? `on lv-${risk.level === "none" ? "watch" : risk.level}` : ""}"></span>`).join("")}<span class="muted">${esc(fill(s.wet_days, { days }))}</span></div>`;
}

function renderRiskAction(hass, s, tree, risk, confirm) {
  const buttons = [];
  if (TREATABLE.includes(risk.model) && !tree.resting) {
    const key = `treat|${tree.subentryId}|${risk.model}`;
    if (risk.protectedNow) {
      const until = (risk.protection || {}).protected_until;
      buttons.push(
        `<span class="protect">${icon("shield", 14)}${esc(until ? fill(s.protected_until, { date: formatDate(hass, until) }) : s.protected_short)}</span>`
      );
      buttons.push(`<button class="link" data-act="clear" data-model="${risk.model}" data-sub="${esc(tree.subentryId)}">${esc(s.clear_treat)}</button>`);
    } else if (risk.level !== "none") {
      buttons.push(
        `<button class="btn ${confirm === key ? "confirm" : ""}" data-act="treat" data-model="${risk.model}" data-sub="${esc(tree.subentryId)}">${icon("spray", 14)}${esc(confirm === key ? s.treat_confirm : s.treat)}</button>`
      );
    }
  }
  if (risk.attributes.awaiting_biofix && !tree.resting) {
    const key = `biofix|${tree.subentryId}|${risk.model}`;
    buttons.push(
      `<button class="btn ${confirm === key ? "confirm" : ""}" data-act="biofix" data-model="${risk.model}" data-sub="${esc(tree.subentryId)}">${esc(confirm === key ? s.treat_confirm : s.first_catch)}</button>`
    );
  }
  return buttons.length ? `<div class="actions">${buttons.join("")}</div>` : "";
}

function renderRisk(hass, view, tree, risk, confirm) {
  const { s, gddState } = view;
  let body = "";
  if (risk.model === "frost") {
    const a = risk.attributes;
    const distant =
      risk.level === "none" &&
      isNumber(a.reference_min) &&
      (!isNumber(a.t10) || a.reference_min > a.t10 + 6);
    body = distant
      ? `<div class="muted">${esc(fill(s.frost_calm, { temp: formatNumber(hass, a.reference_min) }))}</div>`
      : renderFrostGauge(hass, s, risk);
  }
  else if (DISEASES.includes(risk.model)) body = renderDisease(hass, s, tree, risk);
  else body = renderCycle(hass, s, tree, risk, gddState);
  return `<div class="risk lv-${risk.level}">
    <button class="risk-head" data-more="${esc(risk.entityId)}"><span class="risk-row">
      <span class="risk-icon">${icon(MODEL_ICON[risk.model], 16)}</span>
      <span class="risk-name">${esc(s.models[risk.model] || risk.model)}</span>
      <span class="pill">${esc(s.levels[risk.level])}</span>
    </span></button>
    ${body}
    ${renderRiskAction(hass, s, tree, risk, confirm)}
  </div>`;
}

function renderPanel(hass, view, tree, confirm) {
  const { s } = view;
  const risks = tree.risks.map((risk) => renderRisk(hass, view, tree, risk, confirm)).join("");
  return `<div class="panel">
    <div class="panel-head">
      <div class="panel-title">${esc(tree.title)}</div>
      <button class="icon-btn" data-close aria-label="${esc(s.close)}">${icon("close", 16)}</button>
    </div>
    ${renderPath(hass, s, tree)}
    ${risks ? `<section class="section"><div class="section-title">${esc(s.risks)}</div><div class="risks">${risks}</div></section>` : ""}
  </div>`;
}

function renderSpray(hass, view) {
  const { s, spray, trees } = view;
  if (!spray || trees.every((tree) => tree.resting)) return "";
  const a = spray.attributes;
  const now = Date.now();
  const hours = 48;
  const end = now + hours * 3600000;
  const pct = (value) => ((clamp(value, now, end) - now) / (end - now)) * 100;

  const windows = (a.windows || [])
    .map((window) => ({ from: Date.parse(window.start), to: Date.parse(window.end) }))
    .filter((window) => window.to > now && window.from < end)
    .map(
      (window) =>
        `<span class="win" style="left:${pct(window.from)}%;width:${Math.max(1.5, pct(window.to) - pct(window.from))}%" title="${esc(formatWhen(hass, s, new Date(window.from)))}"></span>`
    )
    .join("");

  // Repères de minuit, avec le nom du jour qui commence.
  const ticks = [];
  const fmt = new Intl.DateTimeFormat(language(hass), { timeZone: zone(hass), weekday: "short" });
  for (let t = now; t < end; t += 3600000) {
    const date = new Date(t);
    if (hourOf(hass, date) === 0) {
      const label = pct(t) > 22 ? `<b>${esc(fmt.format(date))}</b>` : "";
      ticks.push(`<span class="tick" style="left:${pct(t)}%"><i></i>${label}</span>`);
    }
  }

  const frosts = allRisks(view.trees)
    .filter((risk) => risk.model === "frost" && risk.level !== "none" && risk.attributes.next_frost_time)
    .map((risk) => Date.parse(risk.attributes.next_frost_time))
    .filter((value) => value > now && value < end);
  const frostMark = frosts.length
    ? `<span class="frost-mark" style="left:${pct(Math.min(...frosts))}%">${icon("frost", 12)}</span>`
    : "";

  const next = nextDaylightWindow(hass, spray);
  let summary;
  if (next && next.open) summary = fill(s.spray_open, { time: formatTime(hass, new Date(next.to)) });
  else if (next) summary = fill(s.spray_next, { when: formatWhen(hass, s, next.from) });
  else summary = s.spray_none;
  const blocking = (a.blocking || [])
    .map((reason) => s[`block_${reason}`])
    .filter(Boolean)
    .join(", ");

  return `<button class="spray" data-more="${esc(spray.entity_id)}">
    <span class="spray-head">
      <span class="spray-title">${icon("spray", 15)}${esc(s.spray_title)}</span>
      <span class="spray-summary ${next && next.open ? "open" : ""}">${esc(summary)}${!next && blocking ? ` (${esc(blocking)})` : ""}</span>
    </span>
    <span class="spray-track">${windows}${ticks.join("")}${frostMark}<span class="tick now"><b>${esc(s.now_label)}</b></span></span>
  </button>`;
}

function renderCard(hass, config, view, selected, confirm) {
  const { s, trees } = view;
  const dark = Boolean(hass.themes && hass.themes.darkMode);
  const title = config.title === undefined ? s.title : config.title;
  const phase = view.season ? view.season.state : null;

  if (!trees.length) {
    return `<ha-card class="${dark ? "dark" : ""}"><div class="root"><div class="empty">
      <div class="empty-art">${icon("leaf", 34)}</div>
      <div class="banner-title">${esc(view.entitiesFound ? s.unavailable : s.empty_title)}</div>
      ${view.entitiesFound ? "" : `<div class="muted">${esc(s.empty_text)}</div>`}
    </div></div></ha-card>`;
  }

  const stats = [];
  if (phase && s.phases[phase]) {
    stats.push(`<span class="stat">${icon(phase === "winter_rest" ? "moon" : "leaf", 14)}${esc(s.phases[phase])}</span>`);
  }
  if (isNumber(view.minForecast) && view.minForecast <= 5) {
    stats.push(`<span class="stat">${icon("frost", 14)}${esc(s.min_forecast)} ${esc(formatNumber(hass, view.minForecast))} °C</span>`);
  }

  const tiles = trees
    .map((tree, index) => {
      const open = tree.key === selected;
      const tile = renderTile(hass, view, tree, index, open, dark);
      return open ? tile + renderPanel(hass, view, tree, confirm) : tile;
    })
    .join("");

  return `<ha-card class="${dark ? "dark" : ""}"><div class="root">
    <header class="head">
      ${title ? `<h2 class="title">${esc(title)}</h2>` : ""}
      <div class="stats">${stats.join("")}</div>
    </header>
    ${renderBanner(hass, view)}
    <div class="tiles n${Math.min(trees.length, 7)}">${tiles}</div>
    ${config.show_spray === false ? "" : renderSpray(hass, view)}
  </div></ha-card>`;
}

const CARD_STYLE = `
  :host { display: block; container-type: inline-size; --ok: #2e8b57; --ok-rgb: 46,139,87; --watch: #b97a00; --watch-rgb: 185,122,0; --warning: #d9590b; --warning-rgb: 217,89,11; --severe: #cf2a2a; --severe-rgb: 207,42,42; --rest: #4f7396; --rest-rgb: 79,115,150; }
  ha-card.dark { --ok: #66c28d; --ok-rgb: 102,194,141; --watch: #f0b429; --watch-rgb: 240,180,41; --warning: #ff9347; --warning-rgb: 255,147,71; --severe: #ff7575; --severe-rgb: 255,117,117; --rest: #93b6d6; --rest-rgb: 147,182,214; }
  ha-card { display: block; overflow: hidden; --icon-hole: var(--ha-card-background, var(--card-background-color, #fff)); }
  .root { padding: 16px; color: var(--primary-text-color); }
  .root > * + * { margin-top: 14px; }
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; margin: 0; cursor: pointer; text-align: left; }
  button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .ic { flex: none; display: block; }
  .muted { color: var(--secondary-text-color); font-size: 12.5px; line-height: 1.45; }
  .small { font-size: 11.5px; }

  .head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; margin-bottom: -6px; }
  .title { margin: 0 12px 6px 0; font-size: 20px; font-weight: 500; line-height: 1.2; letter-spacing: -.005em; }
  .stats { display: flex; flex-wrap: wrap; margin-left: -6px; }
  .stat { display: inline-flex; align-items: center; margin: 0 0 6px 6px; font-size: 12px; color: var(--secondary-text-color); background: var(--secondary-background-color, rgba(127,127,127,.12)); border-radius: 99px; padding: 4px 10px 4px 8px; white-space: nowrap; }
  .stat .ic { margin-right: 5px; }

  .lv-none, .ok { --c: var(--ok); --c-rgb: var(--ok-rgb); }
  .lv-watch { --c: var(--watch); --c-rgb: var(--watch-rgb); }
  .lv-warning { --c: var(--warning); --c-rgb: var(--warning-rgb); }
  .lv-severe { --c: var(--severe); --c-rgb: var(--severe-rgb); }
  .rest { --c: var(--rest); --c-rgb: var(--rest-rgb); }

  .alerts > * + * { margin-top: 6px; }
  .banner { display: flex; padding: 12px 14px; border-radius: 14px; background: rgba(var(--c-rgb), .12); }
  .banner-icon { flex: none; width: 40px; height: 40px; margin-right: 12px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--c); --icon-hole: var(--c); }
  ha-card.dark .banner-icon { color: #16191c; --icon-hole: var(--c); }
  .banner-body { min-width: 0; }
  .banner-eyebrow { display: flex; flex-wrap: wrap; align-items: center; margin-bottom: 2px; }
  .banner-eyebrow > * { margin: 0 8px 2px 0; }
  .banner-names { font-size: 12px; color: var(--secondary-text-color); }
  .banner-title { font-size: 15px; font-weight: 600; line-height: 1.3; }
  .banner-text { margin-top: 2px; font-size: 13px; line-height: 1.45; color: var(--primary-text-color); opacity: .86; }
  .banner-action { margin-top: 4px; font-size: 13px; font-weight: 500; line-height: 1.45; color: var(--c); }
  .pill { display: inline-block; font-size: 11px; font-weight: 600; line-height: 1; padding: 3px 7px; border-radius: 99px; color: var(--c); background: rgba(var(--c-rgb), .16); white-space: nowrap; }
  .minor { display: flex; align-items: center; padding: 4px 14px; font-size: 13px; color: var(--primary-text-color); }
  .minor .ic { color: var(--c); margin-right: 8px; }
  .minor-title { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .minor-names { color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-left: auto; padding-left: 8px; font-size: 12px; min-width: 40px; flex: 0 1 auto; }
  .minor-more { padding: 0 14px; font-size: 12px; color: var(--secondary-text-color); }

  .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); grid-template-columns: repeat(auto-fill, minmax(min(146px, 46%), 1fr)); grid-auto-flow: dense; grid-gap: 12px; align-items: start; }
  .tiles.n1 { grid-template-columns: minmax(0, 1fr); }
  .tiles.n2, .tiles.n4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tile { display: block; width: 100%; min-width: 0; border-radius: 14px; transition: transform .16s ease; }
  .tile:hover { transform: translateY(-2px); }
  .vignette { position: relative; display: block; border-radius: 14px; overflow: hidden; box-shadow: inset 0 0 0 1px rgba(0,0,0,.05); }
  .vignette::before { content: ""; display: block; padding-top: 68.75%; }
  .tile.lv-warning .vignette, .tile.lv-severe .vignette { box-shadow: 0 0 0 2px var(--c); }
  .tile.lv-severe .vignette { animation: pulse 2.6s ease-in-out infinite; }
  .tile.selected .vignette { box-shadow: 0 0 0 2.5px var(--primary-color); animation: none; }
  .scene { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: block; }
  .temp { position: absolute; top: 7px; left: 7px; display: inline-flex; align-items: center; font-size: 11.5px; font-weight: 600; color: #0d2b4a; background: rgba(255,255,255,.88); border-radius: 99px; padding: 3px 7px 3px 5px; }
  .temp .ic { margin-right: 3px; }
  .shield { position: absolute; top: 7px; right: 7px; color: var(--ok); background: rgba(255,255,255,.9); border-radius: 50%; padding: 3px; --icon-hole: #fff; }
  .tile-body { display: block; padding: 8px 2px 2px; min-width: 0; }
  .tile-body > * + * { margin-top: 2px; }
  .tile-title { font-size: 14px; font-weight: 600; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; overflow-wrap: anywhere; }
  .tile-sub { font-size: 12px; line-height: 1.3; color: var(--secondary-text-color); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .tile-note { display: block; font-size: 12px; line-height: 1.3; color: var(--secondary-text-color); }
  .tile-body > .chips { display: flex; flex-wrap: wrap; margin: 1px -4px 0 0; }
  .chip { display: inline-flex; align-items: center; max-width: 100%; margin: 4px 4px 0 0; font-size: 11.5px; font-weight: 500; line-height: 1.1; color: var(--c, var(--secondary-text-color)); background: rgba(var(--c-rgb, 127,127,127), .13); border-radius: 99px; padding: 3px 8px 3px 6px; --icon-hole: transparent; }
  .chip .ic { margin-right: 4px; }
  .chip > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .chip.more { padding: 3px 7px; }

  .panel { grid-column: 1 / -1; padding: 14px; border-radius: 14px; background: var(--secondary-background-color, rgba(127,127,127,.09)); animation: reveal .18s ease-out; }
  .panel > * + * { margin-top: 14px; }
  .panel-head { display: flex; align-items: center; justify-content: space-between; }
  .panel-title { margin-right: 8px; font-size: 16px; font-weight: 600; min-width: 0; word-break: break-word; overflow-wrap: anywhere; }
  .icon-btn { width: 30px; height: 30px; padding: 7px; flex: none; border-radius: 50%; color: var(--secondary-text-color); }
  .icon-btn:hover { background: rgba(127,127,127,.16); }
  .section > * + * { margin-top: 6px; }
  .section-title { font-size: 12px; font-weight: 600; color: var(--secondary-text-color); }
  .link { font-size: 12px; color: var(--primary-color); white-space: nowrap; }
  .link:hover { text-decoration: underline; }
  .section > .picker { display: block; margin-top: 12px; }
  .picker .section-title { display: block; margin-bottom: 5px; }
  .picker select { display: block; width: 100%; height: 40px; padding: 0 10px; font: inherit; font-size: 14px; color: var(--primary-text-color); background: var(--ha-card-background, var(--card-background-color, #fff)); border: 1px solid var(--divider-color, rgba(127,127,127,.4)); border-radius: 10px; }
  ha-card.dark .picker select { color-scheme: dark; }
  .path { display: flex; align-items: flex-end; height: 40px; }
  .step { flex: 1 1 0; min-width: 0; height: 100%; margin-left: 3px; display: flex; align-items: flex-end; border-radius: 4px; position: relative; }
  .step:first-child { margin-left: 0; }
  .step-bar { display: block; width: 100%; min-height: 3px; border-radius: 3px; }
  .step.future .step-bar { opacity: .34; }
  .step.past .step-bar { opacity: .7; }
  .step.now .step-bar { opacity: 1; }
  .step.now::after { content: ""; position: absolute; left: 50%; bottom: -9px; width: 6px; height: 6px; margin-left: -3px; border-radius: 50%; background: var(--primary-text-color); }
  .section > .path-ends { display: flex; justify-content: space-between; margin-top: 14px; font-size: 11px; color: var(--secondary-text-color); }
  .path-now { font-size: 14px; font-weight: 500; line-height: 1.3; }
  .risks > * + * { margin-top: 8px; }
  .risk { padding: 10px 12px; border-radius: 12px; background: var(--ha-card-background, var(--card-background-color, #fff)); }
  .risk > * + * { margin-top: 7px; }
  .risk-head { display: block; width: 100%; }
  .risk-row { display: flex; align-items: center; }
  .risk-icon { width: 24px; height: 24px; margin-right: 8px; flex: none; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: var(--c); background: rgba(var(--c-rgb), .14); --icon-hole: transparent; }
  .risk-name { font-size: 14px; font-weight: 500; flex: 1; min-width: 0; margin-right: 8px; }
  .risk > .actions { display: flex; flex-wrap: wrap; align-items: center; margin-right: -12px; margin-bottom: -8px; }
  .actions > * { margin: 0 12px 8px 0; }
  .btn { display: inline-block; font-size: 12.5px; font-weight: 500; line-height: 16px; padding: 7px 12px; border-radius: 99px; box-shadow: inset 0 0 0 1px var(--divider-color, rgba(127,127,127,.4)); }
  .btn .ic { display: inline-block; vertical-align: -3px; margin-right: 6px; }
  .btn:hover { background: rgba(127,127,127,.1); }
  .btn.confirm { color: var(--text-primary-color, #fff); background: var(--primary-color); box-shadow: none; }
  .protect { display: inline-flex; align-items: center; font-size: 12.5px; font-weight: 500; color: var(--ok); --icon-hole: var(--ha-card-background, #fff); }
  .protect .ic { margin-right: 5px; }
  .gauge { position: relative; padding-top: 17px; }
  .gauge > * + * { margin-top: 3px; }
  .gauge-label { position: absolute; top: 0; font-size: 12px; font-weight: 600; white-space: nowrap; transform: translateX(-50%); }
  .gauge-label.left { transform: translateX(-6px); }
  .gauge-label.right { transform: translateX(calc(-100% + 6px)); }
  .gauge-track { position: relative; height: 10px; border-radius: 99px; overflow: visible; background: rgba(127,127,127,.2); }
  .g-seg { position: absolute; top: 0; bottom: 0; }
  .g-seg:first-child { border-radius: 99px 0 0 99px; }
  .g-seg:nth-child(4) { border-radius: 0 99px 99px 0; }
  .g-severe { background: var(--severe); } .g-warning { background: var(--warning); } .g-watch { background: var(--watch); } .g-ok { background: var(--ok); }
  .gauge-mark { position: absolute; top: -4px; bottom: -4px; width: 4px; margin-left: -2px; border-radius: 2px; background: var(--primary-text-color); box-shadow: 0 0 0 1.5px var(--ha-card-background, #fff); }
  .gauge-ticks { position: relative; height: 15px; font-size: 11px; color: var(--secondary-text-color); }
  .gauge-ticks span { position: absolute; transform: translateX(-50%); }
  .meter { position: relative; height: 8px; border-radius: 99px; background: rgba(127,127,127,.2); overflow: hidden; }
  .meter-fill { position: absolute; top: 0; bottom: 0; left: 0; border-radius: 99px; background: var(--c); }
  .meter-tick { position: absolute; top: 0; bottom: 0; width: 1.5px; background: var(--ha-card-background, #fff); }
  .dots { display: flex; align-items: center; }
  .dot { width: 11px; height: 11px; margin-right: 5px; border-radius: 50%; background: rgba(127,127,127,.25); }
  .dot.on { background: var(--c); }
  .dots .muted { margin-left: 4px; }
  .cycle { display: flex; }
  .cycle-seg { flex: 1 1 0; height: 8px; margin-left: 3px; border-radius: 3px; background: var(--c); opacity: .3; }
  .cycle-seg:first-child { margin-left: 0; }
  .cycle-seg.lv-none { background: rgba(127,127,127,.5); }
  .cycle-seg.past { opacity: .55; }
  .cycle-seg.now { opacity: 1; box-shadow: 0 0 0 1.5px var(--primary-text-color); }

  .spray { display: block; width: 100%; padding: 2px 0 14px; }
  .spray-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; margin-bottom: 7px; }
  .spray-title { display: inline-flex; align-items: center; margin-right: 10px; font-size: 13px; font-weight: 500; color: var(--primary-text-color); --icon-hole: var(--ha-card-background, #fff); }
  .spray-title .ic { margin-right: 6px; }
  .spray-summary { font-size: 12.5px; color: var(--secondary-text-color); }
  .spray-summary.open { color: var(--ok); font-weight: 500; }
  .spray-track { position: relative; display: block; height: 10px; border-radius: 99px; background: rgba(127,127,127,.18); }
  .win { position: absolute; top: 0; bottom: 0; border-radius: 99px; background: var(--ok); }
  .tick { position: absolute; top: 0; bottom: -15px; }
  .tick i { position: absolute; top: 0; height: 10px; width: 1.5px; background: var(--ha-card-background, #fff); }
  .tick.now { left: 0; }
  .tick b { position: absolute; top: 12px; left: 0; font-size: 11px; font-weight: 400; color: var(--secondary-text-color); white-space: nowrap; }
  .frost-mark { position: absolute; top: -3px; width: 16px; height: 16px; margin-left: -8px; display: flex; align-items: center; justify-content: center; border-radius: 50%; color: #fff; background: #3b7dc4; }

  .empty { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 18px 8px; }
  .empty > * + * { margin-top: 6px; }
  .empty-art { color: var(--ok); }

  .flake { animation: drift 4s ease-in-out infinite alternate; }
  .flutter { animation: flutter 1.5s ease-in-out infinite alternate; transform-box: fill-box; transform-origin: center; }
  @keyframes drift { from { transform: translate(-1.5px, -2px) rotate(0); } to { transform: translate(1.5px, 3px) rotate(40deg); } }
  @keyframes flutter { from { transform: translate(-2px, 1px) scaleX(1); } to { transform: translate(2px, -2px) scaleX(.72); } }
  @keyframes pulse { 0%, 100% { box-shadow: 0 0 0 2px var(--c); } 50% { box-shadow: 0 0 0 4px rgba(var(--c-rgb), .45); } }
  @keyframes reveal { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
  @media (prefers-reduced-motion: reduce) {
    .flake, .flutter, .tile.lv-severe .vignette, .panel { animation: none; }
    .tile { transition: none; }
  }
  @container (min-width: 430px) {
    .tiles.n3, .tiles.n6 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .tiles.n1 .tile { display: flex; align-items: center; }
    .tiles.n1 .vignette { flex: 0 0 52%; margin-right: 14px; }
    .tiles.n1 .tile-body { padding: 0; flex: 1; }
    .tiles.n1 .tile-title { font-size: 16px; }
  }
  @container (min-width: 640px) {
    .tiles.n4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  }
  @container (max-width: 340px) {
    .root { padding: 12px; }
    .tiles { grid-gap: 10px; }
  }
`;

// ---------------------------------------------------------------------
// Élément
// ---------------------------------------------------------------------

class MeteoSentinelleCard extends HTMLElement {
  static getStubConfig() {
    return { type: `custom:${CARD_TYPE}` };
  }

  /** Éditeur natif de Home Assistant, qui gère lui-même l'ordre d'initialisation. */
  static getConfigForm() {
    const root = document.querySelector ? document.querySelector("home-assistant") : null;
    const labels = strings(root && root.hass).fields;
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        {
          name: "devices",
          selector: { device: { multiple: true, filter: { integration: DOMAIN } } },
        },
        { name: "show_spray", default: true, selector: { boolean: {} } },
      ],
      computeLabel: (schema) => labels[schema.name] || schema.name,
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._selected = null;
    this._confirm = null;
    this._signature = null;
    this._ids = null;
    this._idsFrom = null;
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = Object.assign({}, config);
    this._signature = null;
    this._update();
  }

  getCardSize() {
    const trees = (this._view && this._view.trees.length) || 2;
    return 4 + Math.ceil(trees / 3) * 3;
  }

  getGridOptions() {
    return { columns: 12, rows: "auto", min_columns: 6 };
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  get hass() {
    return this._hass;
  }

  _discover() {
    // `hass` change à chaque état du système : le répertoire des entités n'est
    // refait que lorsque le registre change, ou à défaut de temps en temps.
    const source = this._hass.entities;
    const now = Date.now();
    if (!this._ids || this._idsFrom !== source || now - (this._idsAt || 0) > 60000) {
      this._ids = discover(this._hass);
      this._idsFrom = source;
      this._idsAt = now;
    }
    return this._ids;
  }

  _computeSignature(ids) {
    const parts = [
      JSON.stringify(this._config),
      this._selected,
      this._confirm,
      this._hass.themes && this._hass.themes.darkMode,
      language(this._hass),
      // Les délais affichés (« cette nuit », « demain ») vieillissent seuls.
      Math.floor(Date.now() / 300000),
    ];
    for (const list of [ids.risks, ids.stages, ids.spray, ids.season, ids.gdd]) {
      for (const id of list) parts.push((this._hass.states[id] || {}).last_updated);
    }
    return parts.join("|");
  }

  _update() {
    if (!this._hass || !this._config) return;
    // Redessiner refermerait la liste que l'utilisateur est en train d'ouvrir.
    const opened = this.shadowRoot.activeElement;
    if (opened && opened.tagName === "SELECT") return;
    const ids = this._discover();
    const signature = this._computeSignature(ids);
    if (signature === this._signature) return;
    this._signature = signature;

    const view = buildView(this._hass, this._config, ids);
    this._view = view;
    if (this._selected && !view.trees.some((tree) => tree.key === this._selected)) {
      this._selected = null;
    }
    const active = this.shadowRoot.activeElement;
    const focused = active && active.dataset && active.dataset.tree;
    this.shadowRoot.innerHTML = `<style>${CARD_STYLE}</style>${renderCard(
      this._hass,
      this._config,
      view,
      this._selected,
      this._confirm
    )}`;
    const card = this.shadowRoot.querySelector("ha-card");
    if (card) {
      card.addEventListener("click", (event) => this._onClick(event));
      card.addEventListener("change", (event) => this._onChange(event));
    }
    if (focused) {
      const key = window.CSS && window.CSS.escape ? window.CSS.escape(focused) : focused;
      const tile = this.shadowRoot.querySelector(`[data-tree="${key}"]`);
      if (tile) tile.focus();
    }
  }

  _fire(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
  }

  _onChange(event) {
    const select = event.target;
    if (!select.hasAttribute || !select.hasAttribute("data-stage")) return;
    // Quitter la liste laisse la carte se redessiner avec le nouveau stade.
    select.blur();
    this._call("set_stage", { tree: select.dataset.sub, stage: select.value });
  }

  _onClick(event) {
    const target = event.target.closest
      ? event.target.closest("[data-act],[data-more],[data-close],[data-tree]")
      : null;
    if (!target) return;
    const { act, more, tree } = target.dataset;
    if (act) {
      this._onAction(act, target.dataset.model, target.dataset.sub);
    } else if (more) {
      this._fire("hass-more-info", { entityId: more });
    } else if (target.hasAttribute("data-close")) {
      this._selected = null;
      this._update();
    } else if (tree !== undefined) {
      this._selected = this._selected === tree ? null : tree;
      this._confirm = null;
      this._update();
    }
  }

  async _onAction(action, model, tree) {
    if (action === "clear") {
      this._call("clear_treatment", { target: model, tree });
      return;
    }
    // Ces gestes modifient les calculs : une seconde pression les confirme,
    // pour qu'un doigt qui passe ne déclare pas un traitement.
    const key = `${action}|${tree}|${model}`;
    if (this._confirm !== key) {
      this._confirm = key;
      this._update();
      clearTimeout(this._confirmTimer);
      this._confirmTimer = setTimeout(() => {
        this._confirm = null;
        this._update();
      }, 4000);
      return;
    }
    clearTimeout(this._confirmTimer);
    this._confirm = null;
    this._update();
    if (action === "treat") this._call("log_treatment", { target: model, tree });
    if (action === "biofix") this._call("set_biofix", { pest: model, tree });
  }

  async _call(service, data) {
    try {
      await this._hass.callService(DOMAIN, service, data);
    } catch (err) {
      this._fire("hass-notification", {
        message: fill(strings(this._hass).call_failed, { message: (err && err.message) || "" }),
      });
    }
  }
}

if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, MeteoSentinelleCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "Météo Sentinelle",
    description:
      "Votre verger illustré : le stade de chaque arbre, ce qui le menace et quand agir.",
    preview: true,
    documentationURL: "https://github.com/Sdavid66/Meteo-Sentinelle",
  });
}

})();
