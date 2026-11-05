/**
 * Tests de la carte, exécutables sans navigateur ni Home Assistant.
 *
 * Ils ne jugent pas l'apparence (tests/card_demo.html sert à cela) mais tout
 * ce qui peut casser en silence : ordre d'initialisation, valeurs vides,
 * traductions manquantes, gestes de l'utilisateur.
 *
 * Lancement : node tests/test_card.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const CARD = path.join(ROOT, "custom_components/meteo_sentinelle/frontend/meteo-sentinelle-card.js");

let passed = 0;
function check(condition, label) {
  if (!condition) throw new Error(`ÉCHEC : ${label}`);
  passed += 1;
  console.log(`  ok  ${label}`);
}

function load() {
  const registry = {};
  class FakeElement {
    attachShadow() {
      this.shadowRoot = {
        innerHTML: "",
        renders: 0,
        querySelector: () => ({ addEventListener() {}, focus() {} }),
      };
      return this.shadowRoot;
    }
    dispatchEvent(event) {
      (this.events = this.events || []).push(event);
    }
  }
  const context = vm.createContext({
    HTMLElement: FakeElement,
    console,
    setTimeout,
    clearTimeout,
    window: {},
    document: {},
    customElements: {
      get: (name) => registry[name],
      define: (name, value) => {
        registry[name] = value;
      },
    },
    CustomEvent: class {
      constructor(type, init) {
        this.type = type;
        this.detail = init.detail;
      }
    },
  });
  // La fonction englobante de la carte cache ses fonctions : on la retire ici
  // pour les tester directement.
  const source = fs.readFileSync(CARD, "utf8");
  const opening = "(function () {\n";
  const closing = "\n})();\n";
  if (!source.includes(opening) || !source.endsWith(closing)) {
    throw new Error("ÉCHEC : la carte doit rester enveloppée dans une fonction");
  }
  vm.runInContext(source.replace(opening, "").slice(0, -closing.length), context);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "tests/card_fixtures.js"), "utf8"), context);
  return {
    context,
    Card: registry["meteo-sentinelle-card"],
    STRINGS: vm.runInContext("STRINGS", context),
    SCENARIOS: context.window.CARD_SCENARIOS,
    window: context.window,
    buildView: (hass, config) =>
      vm.runInContext("(h, c) => buildView(h, c, discover(h))", context)(hass, config),
  };
}

const { Card, STRINGS, SCENARIOS, window, buildView, context } = load();
const contextRef = () => context;
const CONFIG = { type: "custom:meteo-sentinelle-card" };

function render(hass, order = "config-first", config = CONFIG) {
  const card = new Card();
  if (order === "config-first") {
    card.setConfig(config);
    card.hass = hass;
  } else {
    card.hass = hass;
    card.setConfig(config);
  }
  return card;
}

console.log("\n--- rendu de chaque scène ---");
for (const [name, build] of Object.entries(SCENARIOS)) {
  for (const lang of ["fr", "en"]) {
    for (const dark of [false, true]) {
      for (const order of ["config-first", "hass-first"]) {
        const html = render(build({ lang, dark }), order).shadowRoot.innerHTML;
        for (const bad of ["undefined", "NaN", "[object", "null"]) {
          if (html.replace(/<style>[\s\S]*?<\/style>/, "").includes(bad)) {
            throw new Error(`ÉCHEC : « ${bad} » affiché dans ${name} (${lang})`);
          }
        }
      }
    }
    passed += 4;
  }
  console.log(`  ok  ${name} : rendu propre, en deux langues, clair et sombre, dans les deux ordres`);
}

console.log("\n--- détail de chaque arbre ---");
for (const [name, build] of Object.entries(SCENARIOS)) {
  const hass = build({ lang: "fr" });
  const card = render(hass);
  for (const tree of card._view.trees) {
    card._selected = tree.key;
    card._signature = null;
    card._update();
    const html = card.shadowRoot.innerHTML.replace(/<style>[\s\S]*?<\/style>/, "");
    check(!/undefined|NaN|\[object/.test(html) && html.includes("panel-head"), `${name} / ${tree.title} : détail propre`);
  }
}

console.log("\n--- traductions ---");
function keys(value, prefix = "") {
  return Object.entries(value).flatMap(([key, item]) =>
    item && typeof item === "object" ? keys(item, `${prefix}${key}.`) : [`${prefix}${key}`]
  );
}
check(
  JSON.stringify(keys(STRINGS.fr).sort()) === JSON.stringify(keys(STRINGS.en).sort()),
  "le français et l'anglais ont exactement les mêmes textes"
);

console.log("\n--- vieux navigateurs ---");
const cardSource = fs.readFileSync(CARD, "utf8");
const cardStyle = cardSource.slice(cardSource.indexOf("const CARD_STYLE"));
for (const [feature, label] of [
  [/color-mix\(/, "color-mix"],
  [/aspect-ratio/, "aspect-ratio"],
  [/\binset:/, "inset"],
  [/place-items/, "place-items"],
  [/[;{]\s*gap:/, "gap (les flexbox l'ignorent avant Chrome 84)"],
]) {
  check(!feature.test(cardStyle), `pas de ${label} dans la feuille de style`);
}
const code = cardSource.replace(/\/\/[^\n]*/g, "");
check(!/flatMap|\?\?|\?\.[a-zA-Z_([]/.test(code), "ni `?.`, ni `??`, ni flatMap dans le code");

console.log("\n--- messages ---");
const rest = buildView(SCENARIOS["Aujourd'hui : repos"]({ lang: "fr" }), CONFIG);
check(rest.alerts.length === 0 && rest.calm.kind === "rest", "repos : pas d'alerte, le verger se repose");
check(rest.calm.next.includes("au printemps"), "en novembre, la reprise est annoncée au printemps");
check(!/demain|dans ~/.test(rest.calm.next), "et pas pour demain, malgré le cumul de l'année écoulée");
const january = SCENARIOS["Début de saison : bourgeons"]({ lang: "fr" });
check(!buildView(january, CONFIG).calm.next.includes("au printemps"), "en saison, le délai reste estimé");

const spring = buildView(SCENARIOS["Printemps : gel en floraison"]({ lang: "fr" }), CONFIG);
check(spring.alerts[0].model === "frost" && spring.alerts[0].level === "severe", "le gel sévère passe en premier");
check(spring.alerts.filter((alert) => alert.model === "frost").length === 1, "le gel de plusieurs arbres fait un seul message");
check(spring.alerts[0].names.startsWith("Golden"), "l'arbre le plus exposé est cité d'abord");
check(spring.alerts[0].text.includes("−3,4"), "la température garde sa décimale et son signe");

const summer = buildView(SCENARIOS["Été : carpocapse et oïdium"]({ lang: "fr" }), CONFIG);
check(rankOrder(summer.alerts), "les messages vont du plus urgent au moins urgent");
const golden = summer.trees.find((tree) => tree.key === "golden");
check(golden.growth.phase === "fruit", "pleine floraison il y a 70 jours : l'arbre porte des fruits");
check(golden.stageLabel === "Fruits en croissance", "et son libellé le dit");
const pear = summer.alerts.find((alert) => alert.model === "powdery_mildew");
check(pear.action.includes("fenêtre"), "un risque non couvert renvoie vers la fenêtre de traitement");

const firstDaylight = vm.runInContext("firstDaylight", contextRef());
const at = (hour) => Date.UTC(2026, 6, 15, hour, 0) ; // Zurich = UTC + 2 en juillet
const zurich = { config: { time_zone: "Europe/Zurich" } };
const night = { start: new Date(at(22)).toISOString(), end: new Date(at(23)).toISOString() };
check(firstDaylight(zurich, night, at(20)) === null, "une fenêtre toute de nuit n'est pas proposée");
const dawn = { start: new Date(at(1)).toISOString(), end: new Date(at(9)).toISOString() };
check(firstDaylight(zurich, dawn, at(1)).from === at(5), "une fenêtre à cheval sur l'aube retient 7 h");
const day = { start: new Date(at(8)).toISOString(), end: new Date(at(12)).toISOString() };
check(firstDaylight(zurich, day, at(8)).from === at(8), "une fenêtre de jour est proposée telle quelle");

function rankOrder(alerts) {
  const order = ["none", "watch", "warning", "severe"];
  return alerts.every((alert, i) => i === 0 || order.indexOf(alerts[i - 1].level) >= order.indexOf(alert.level));
}

console.log("\n--- sécurité et performance ---");
const hostile = SCENARIOS["Aujourd'hui : repos"]({ lang: "fr" });
const victim = "sensor.pommier_stade";
hostile.states[victim].attributes.tree_name = '<img src=x onerror="alert(1)">';
const hostileHtml = render(hostile).shadowRoot.innerHTML;
check(!hostileHtml.includes("<img"), "un nom d'arbre ne peut pas injecter de HTML");

const stable = SCENARIOS["Aujourd'hui : repos"]({ lang: "fr" });
const steady = render(stable);
const before = steady.shadowRoot.innerHTML;
steady.shadowRoot.innerHTML = "sentinelle";
steady.hass = { ...stable, states: { ...stable.states, "light.salon": { state: "on", attributes: {} } } };
check(steady.shadowRoot.innerHTML === "sentinelle", "un état sans rapport ne redessine pas la carte");
const updated = {
  ...stable.states["sensor.pommier_frost"],
  state: "warning",
  last_updated: "2026-11-05T09:00:00+00:00",
};
steady.hass = { ...stable, states: { ...stable.states, "sensor.pommier_frost": updated } };
check(steady.shadowRoot.innerHTML !== "sentinelle" && before.length > 0, "un risque qui change redessine la carte");

console.log("\n--- gestes ---");
(async () => {
  window.__cardCalls = [];
  const hass = SCENARIOS["Été : carpocapse et oïdium"]({ lang: "fr" });
  const calls = [];
  hass.callService = async (domain, service, data) => calls.push({ domain, service, data });
  const card = render(hass);

  await card._onAction("treat", "powdery_mildew", "golden");
  check(calls.length === 0 && card._confirm === "treat|golden|powdery_mildew", "une première pression demande confirmation");
  await card._onAction("treat", "powdery_mildew", "golden");
  check(calls.length === 1 && calls[0].service === "log_treatment", "la seconde déclare le traitement");
  check(calls[0].domain === "meteo_sentinelle" && calls[0].data.tree === "golden" && calls[0].data.target === "powdery_mildew", "avec la bonne cible et le bon arbre");

  await card._onAction("biofix", "codling_moth", "golden");
  await card._onAction("biofix", "codling_moth", "golden");
  check(calls[1].service === "set_biofix" && calls[1].data.pest === "codling_moth", "la première capture déclare le biofix");

  card._onChange({
    target: {
      hasAttribute: (name) => name === "data-stage",
      blur() {},
      dataset: { sub: "golden" },
      value: "green_tip",
    },
  });
  check(
    calls.at(-1).service === "set_stage" && calls.at(-1).data.tree === "golden" && calls.at(-1).data.stage === "green_tip",
    "la liste déroulante corrige le stade de l'arbre choisi"
  );
  calls.pop();

  card._selected = "golden";
  card._signature = null;
  card._update();
  const detail = card.shadowRoot.innerHTML;
  check(detail.includes('data-stage data-sub="golden"'), "le détail propose la liste des stades");
  check(detail.includes('value="full_bloom" selected'), "le stade courant y est présélectionné");

  await card._onAction("clear", "powdery_mildew", "conference");
  check(calls[2].service === "clear_treatment", "effacer un traitement ne demande pas de confirmation");

  hass.callService = async () => {
    throw new Error("refus");
  };
  await card._call("log_treatment", {});
  check(card.events.at(-1).type === "hass-notification", "un échec est signalé à l'utilisateur");

  check(typeof Card.getConfigForm().computeLabel === "function", "l'éditeur natif décrit ses champs");
  check(card.getGridOptions().min_columns === 6, "la carte annonce sa taille pour la vue en sections");

  console.log(`\n${passed} vérifications passées.`);
  clearTimeout(card._confirmTimer);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
