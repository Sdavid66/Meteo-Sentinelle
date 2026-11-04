/**
 * États Home Assistant fictifs pour la carte, partagés par la page de démo
 * (tests/card_demo.html) et les tests (tests/test_card.js).
 *
 * Ils reprennent la forme exacte des attributs de sensor.py : une scène se
 * décrit par le stade et les risques de chaque arbre, le reste est déduit.
 */
(function (root) {
  const H = 3600000;
  const D = 24 * H;
  const onTheHour = (ms) => Math.round((Date.now() + ms) / H) * H;
  const iso = (ms) => new Date(onTheHour(ms)).toISOString();
  const nextFourAm = () => {
    const date = new Date(Date.now() + 12 * H);
    date.setHours(4, 0, 0, 0);
    if (date.getTime() < Date.now()) date.setDate(date.getDate() + 1);
    return date.toISOString();
  };

  const TABLES = {
    apple: {
      label: "Pommier",
      btoh: 145,
      stages: [
        ["dormant", null, -25], ["silver_tip", 90, -9.4], ["green_tip", 130, -7.8],
        ["half_inch_green", 200, -5], ["tight_cluster", 280, -2.8], ["first_pink", 330, -2.2],
        ["full_pink", 370, -2.2], ["first_bloom", 420, -2.2], ["full_bloom", 500, -2.2],
      ],
    },
    apricot: {
      label: "Abricotier",
      btoh: 110,
      stages: [
        ["dormant", null, -21], ["first_swell", 50, -9.4], ["tip_separation", 90, -6.7],
        ["first_white", 150, -4.4], ["first_bloom", 190, -3.9], ["full_bloom", 230, -2.8],
        ["in_the_shuck", 330, -2.8], ["shuck_split", 430, -2.2],
      ],
    },
    plum: {
      label: "Prunier",
      btoh: 130,
      stages: [
        ["dormant", null, -24], ["swollen_bud", 70, -10], ["side_white", 110, -8.3],
        ["green_tip", 160, -6.7], ["tight_cluster", 220, -4.4], ["first_white", 280, -3.3],
        ["first_bloom", 320, -2.8], ["full_bloom", 370, -2.2], ["post_bloom", 470, -2.2],
      ],
    },
    peach: {
      label: "Pêcher / nectarinier",
      btoh: 110,
      stages: [
        ["dormant", null, -19], ["swollen_bud", 60, -7.8], ["calyx_green", 110, -6.1],
        ["quarter_inch_green", 160, -5], ["pink", 220, -3.9], ["first_bloom", 270, -3.3],
        ["full_bloom", 320, -2.8], ["post_bloom", 420, -2.2],
      ],
    },
    pear: {
      label: "Poirier",
      btoh: 135,
      stages: [
        ["dormant", null, -25], ["swollen_bud", 80, -9.4], ["bud_burst", 120, -6.7],
        ["green_cluster", 190, -4.4], ["white_bud", 260, -3.9], ["full_white", 310, -3.3],
        ["first_bloom", 360, -2.8], ["full_bloom", 420, -2.2], ["petal_fall", 520, -2.2],
      ],
    },
    sweet_cherry: {
      label: "Cerisier doux",
      btoh: 60,
      stages: [
        ["dormant", null, -23], ["swollen_bud", 70, -8.3], ["bud_burst", 120, -3.9],
        ["tight_cluster", 190, -3.3], ["white_bud", 250, -2.8], ["first_bloom", 300, -2.2],
        ["full_bloom", 350, -2.2], ["post_bloom", 450, -2.2],
      ],
    },
    vine: {
      label: "Vigne",
      btoh: 150,
      stages: [
        ["dormant", 0, -15], ["bud_swell", 150, -6], ["bud_burst", 220, -3],
        ["first_leaves", 300, -1.5], ["shoots_10cm", 400, -1],
      ],
    },
    tender_annual: {
      label: "Annuelles gélives (tomate, courgette, basilic, haricot)",
      stages: [["off_season", null, null], ["growing", 100, 0]],
    },
    potato: {
      label: "Pomme de terre (feuillage)",
      stages: [["off_season", null, null], ["emerged", 100, -1]],
    },
    hardy_vegetable: {
      label: "Légumes rustiques (chou, poireau, épinard)",
      stages: [["growing", null, -6]],
    },
  };

  const CYCLES = {
    codling_moth: {
      base: 10, upper: 31.1, origin: "biofix",
      stages: [
        ["flight", 0, "watch"], ["egg_laying", 55.6, "watch"], ["hatch_start", 122.2, "warning"],
        ["hatch_peak", 138.9, "severe"], ["oviposition_peak", 305.6, "warning"], ["second_generation", 588.9, "watch"],
      ],
    },
    cherry_fruit_fly: {
      base: 5, upper: null, origin: "season",
      stages: [["approach", 375, "watch"], ["emergence", 430, "warning"], ["oviposition", 530, "severe"]],
    },
    colorado_potato_beetle: {
      base: 10, upper: null, origin: "biofix",
      stages: [
        ["eggs", 0, "watch"], ["instar_1", 102.8, "warning"], ["instar_2", 133.3, "severe"],
        ["instar_3", 166.7, "warning"], ["instar_4", 222.2, "watch"], ["pupation", 375, "none"],
      ],
    },
    grapevine_moth: {
      base: 7, upper: null, origin: "season",
      stages: [
        ["first_flight", 217.9, "warning"], ["first_generation", 406.6, "watch"], ["second_flight", 786.3, "warning"],
        ["second_generation", 1329.8, "watch"], ["third_flight", 1452.8, "warning"], ["third_generation", 2108.2, "watch"],
      ],
    },
  };

  const CROP_MODELS = {
    apple: ["frost", "powdery_mildew", "codling_moth"],
    pear: ["frost", "powdery_mildew", "codling_moth"],
    apricot: ["frost", "powdery_mildew"],
    plum: ["frost", "powdery_mildew"],
    peach: ["frost", "powdery_mildew"],
    sweet_cherry: ["frost", "powdery_mildew", "cherry_fruit_fly"],
    vine: ["frost", "powdery_mildew", "late_blight", "grapevine_moth"],
    tender_annual: ["frost", "late_blight", "powdery_mildew"],
    potato: ["frost", "late_blight", "colorado_potato_beetle"],
    hardy_vegetable: ["frost", "powdery_mildew"],
  };

  const NO_PROTECTION = {
    status: "none", product: null, applied_at: null, protected_until: null,
    hours_remaining: 0, days_remaining: 0, rain_since_mm: 0, rainfast_mm: null,
  };

  /** Un état de capteur, tel que le frontend le reçoit. */
  function state(entity_id, value, attributes) {
    return {
      entity_id,
      state: value,
      attributes,
      last_updated: "2026-11-05T08:00:00+00:00",
      last_changed: "2026-11-05T08:00:00+00:00",
    };
  }

  /**
   * Fabrique les entités d'une scène.
   *
   * `trees` : [{ id, name, crop, stage, gdd, bloomDaysAgo, frost, risks }]
   * - `frost` : { level, min, t10?, t90?, inHours } ;
   * - `risks` : { modèle: { level, … attributs du résultat } }.
   */
  function scenario({ phase = "growing", gdd = 500, trees = [], spray = null, lang = "fr", dark = false, recent = 6 }) {
    const states = {};
    const entities = {};
    const add = (id, value, attributes, translation_key, device_id) => {
      states[id] = state(id, value, { site_id: "site1", ...attributes });
      entities[id] = { entity_id: id, platform: "meteo_sentinelle", translation_key, device_id };
    };

    add("sensor.sentinelle_saison", phase, {
      hemisphere: "north", latitude: 46.26, elevation: 836, season_start: "2026-01-01",
      rest_start: "2026-10-16", rest_trigger: "calendar", trees_resting: [],
    }, "season", "site");
    add("sensor.sentinelle_degres_jours", gdd, {
      season_year: 2026, base_temperature: 5.6, first_day: "2026-01-01", last_day: "2026-11-04",
      complete_season: true,
      recent_days: Array.from({ length: 7 }, (_, i) => ({ date: `2026-11-0${i + 1}`, gdd: recent, total: gdd })),
    }, "growing_degree_days", "site");
    add("sensor.sentinelle_fenetre", spray ? iso(spray.first ?? 3 * H) : "unknown", {
      current: spray?.open ? { start: iso(-H), end: iso((spray.first ?? 5 * H)) } : null,
      upcoming: spray && !spray.open ? { start: iso(spray.first ?? 3 * H), end: iso((spray.first ?? 3 * H) + 5 * H) } : null,
      windows: spray
        ? [
            ...(spray.open ? [{ start: iso(-H), end: iso(spray.first ?? 5 * H) }] : [{ start: iso(spray.first ?? 3 * H), end: iso((spray.first ?? 3 * H) + 5 * H) }]),
            { start: iso(20 * H), end: iso(26 * H) },
            { start: iso(40 * H), end: iso(44 * H) },
          ]
        : [],
      blocking: spray ? [] : ["wind", "rain"],
      horizon_hours: 72, max_wind_kmh: 19, rainfast_hours: 2, open_now: Boolean(spray?.open),
    }, "spray_window", "site");

    for (const tree of trees) {
      const table = TABLES[tree.crop];
      const device = `dev_${tree.id}`;
      const path = table.stages.map(([key, g, t10]) => ({ key, gdd: g, t10 }));
      const treeGdd = tree.gdd ?? gdd;
      const index = path.findIndex((step) => step.key === tree.stage);
      const next = path.slice(index + 1).find((step) => step.gdd !== null);
      const current = path[index] || {};
      const bloom = tree.bloomDaysAgo !== undefined ? new Date(Date.now() - tree.bloomDaysAgo * D).toISOString() : undefined;
      const stageAttributes = {
        tree: tree.name, tree_name: tree.name, subentry_id: tree.id, crop: tree.crop,
        crop_label: table.label, stage_key: tree.stage, stages: path,
        bloom_to_harvest_days: table.btoh ?? null, auto_advance: true,
        resting: ["dormant", "off_season"].includes(tree.stage), last_change_automatic: true,
        changed_at: null, gdd_total: treeGdd, gdd_offset: 0, t10: current.t10 ?? null, t90: null,
      };
      if (next) {
        stageAttributes.next_stage_key = next.key;
        stageAttributes.next_stage = next.key;
        stageAttributes.next_stage_gdd = next.gdd;
        stageAttributes.gdd_to_next_stage = Math.max(0, next.gdd - treeGdd);
      }
      if (bloom) {
        stageAttributes.bloom_date = bloom;
        stageAttributes.days_to_harvest = Math.max(0, Math.round((table.btoh || 0) - tree.bloomDaysAgo));
      }
      add(`sensor.${tree.id}_stade`, tree.stage, stageAttributes, "phenology_stage", device);

      const common = {
        tree: tree.name, tree_name: tree.name, subentry_id: tree.id, crop: tree.crop,
        stage: tree.stage, stage_label: tree.stage,
        resting: stageAttributes.resting, sources: { temperature: "ecowitt" },
      };

      for (const model of CROP_MODELS[tree.crop]) {
        const wanted = model === "frost" ? tree.frost || {} : tree.risks?.[model] || {};
        const level = wanted.level || "none";
        const protection = wanted.protection || (model === "frost" ? undefined : NO_PROTECTION);
        const attributes = { ...common, model };
        if (protection) attributes.protection = protection;

        if (model === "frost") {
          const min = wanted.min ?? 6;
          Object.assign(attributes, {
            air_min: min, surface_min: min - 2, reference_min: min, reference: "air",
            next_frost_time: wanted.inHours ? nextFourAm() : null,
            dew_point: 1, radiative_offset: 2, t10: wanted.t10 ?? current.t10 ?? null,
            t90: wanted.t90 ?? (current.t10 !== null && current.t10 !== undefined ? current.t10 - 1.7 : null),
            expected_damage: "none",
          });
        } else if (model === "powdery_mildew") {
          Object.assign(attributes, {
            index: wanted.index ?? 0, epidemic_started: (wanted.index ?? 0) >= 60,
            last_processed_day: null, last_day_optimal_hours: 0, last_day_rain_mm: 0,
            last_day_delta: 0, spray_interval_days: wanted.interval ?? null, days: [],
          });
        } else if (model === "late_blight") {
          Object.assign(attributes, {
            hutton_met: wanted.hutton ?? false, smith_met: false,
            hutton_consecutive_days: wanted.days ?? 0, smith_consecutive_days: 0,
            favourable_days: 0, thermal_pressure: 0, last_day_min_temp: 12,
            last_day_wet_hours: 7, evaluated_days: 4, days: [],
          });
        } else {
          const cycle = CYCLES[model];
          const steps = cycle.stages.map(([stage, degree_days, stageLevel]) => ({
            stage, degree_days, level: stageLevel, extrapolated: false,
          }));
          const dd = wanted.dd ?? 0;
          const reached = steps.filter((step) => dd >= step.degree_days).pop();
          const following = steps.find((step) => dd < step.degree_days);
          const awaiting = wanted.awaiting ?? (cycle.origin === "biofix" && !wanted.biofix);
          Object.assign(attributes, {
            pest: model, cycle_stage: awaiting ? null : reached?.stage ?? null, degree_days: dd,
            base_temperature: cycle.base, upper_temperature: cycle.upper, origin: cycle.origin,
            awaiting_biofix: stageAttributes.resting ? false : awaiting,
            biofix_date: wanted.biofix ?? null, biofix_estimated: wanted.estimated ?? false,
            next_cycle_stage: awaiting ? null : following?.stage ?? null,
            next_cycle_stage_dd: awaiting ? null : following?.degree_days ?? null,
            dd_to_next_cycle_stage: awaiting || !following ? null : following.degree_days - dd,
            extrapolated: false, incomplete_season: false, source: "", stages: steps,
          });
        }
        add(`sensor.${tree.id}_${model}`, level, attributes, `${model}_risk`, device);
      }
    }

    return makeHass(states, entities, { lang, dark });
  }

  const STAGE_LABELS = {
    fr: {
      dormant: "Dormance", off_season: "Hors saison", silver_tip: "Pointe argentée", green_tip: "Pointe verte",
      half_inch_green: "Pousse de 1 cm", tight_cluster: "Bouquet serré", first_pink: "Début rose",
      full_pink: "Pleine floraison rose", first_bloom: "Début floraison", full_bloom: "Pleine floraison",
      post_bloom: "Après floraison", petal_fall: "Chute des pétales", swollen_bud: "Bourgeon gonflé",
      bud_burst: "Débourrement", green_cluster: "Bouquet vert", white_bud: "Bouton blanc", full_white: "Plein blanc",
      first_swell: "Premier gonflement", tip_separation: "Écartement des écailles", first_white: "Début blanc",
      in_the_shuck: "Jeune fruit engainé", shuck_split: "Sortie de l'engainement", side_white: "Blanc latéral",
      calyx_green: "Calice vert", quarter_inch_green: "Pousse de 0,5 cm", pink: "Stade rose",
      bud_swell: "Bourgeon gonflé", first_leaves: "Premières feuilles", shoots_10cm: "Rameaux 10 cm",
      growing: "En végétation", emerged: "Levée effectuée",
    },
    en: {
      dormant: "Dormant", off_season: "Off season", silver_tip: "Silver tip", green_tip: "Green tip",
      half_inch_green: "Half-inch green", tight_cluster: "Tight cluster", first_pink: "First pink",
      full_pink: "Full pink", first_bloom: "First bloom", full_bloom: "Full bloom", post_bloom: "Post bloom",
      petal_fall: "Petal fall", swollen_bud: "Swollen bud", bud_burst: "Bud burst", green_cluster: "Green cluster",
      white_bud: "White bud", full_white: "Full white", first_swell: "First swell", tip_separation: "Tip separation",
      first_white: "First white", in_the_shuck: "In the shuck", shuck_split: "Shuck split", side_white: "Side white",
      calyx_green: "Calyx green", quarter_inch_green: "Quarter-inch green", pink: "Pink", bud_swell: "Bud swell",
      first_leaves: "First leaves", shoots_10cm: "10 cm shoots", growing: "Growing", emerged: "Emerged",
    },
  };

  function makeHass(states, entities, { lang = "fr", dark = false } = {}) {
    return {
      states,
      entities,
      language: lang,
      locale: { language: lang },
      themes: { darkMode: dark },
      config: { time_zone: "Europe/Zurich" },
      formatEntityState: (stateObj, value) =>
        STAGE_LABELS[lang]?.[value ?? stateObj.state] ?? value ?? stateObj.state,
      callService: async (domain, service, data) => {
        (root.__cardCalls = root.__cardCalls || []).push({ domain, service, data });
      },
    };
  }

  const SCENARIOS = {
    "Aujourd'hui : repos": (o) =>
      scenario({
        ...o,
        phase: "winter_rest",
        gdd: 12,
        recent: 0.2,
        trees: [
          { id: "pommier", name: "Pommier", crop: "apple", stage: "dormant", frost: { min: 3 }, risks: { codling_moth: { awaiting: false } } },
          { id: "abricotier", name: "Abricotier", crop: "apricot", stage: "dormant", frost: { min: 3 } },
          { id: "prunier", name: "Prunier", crop: "plum", stage: "dormant", frost: { min: 3 } },
          { id: "jardin", name: "Jardin_tomates_courgettes", crop: "tender_annual", stage: "off_season", frost: { min: 1 } },
        ],
      }),
    "Printemps : gel en floraison": (o) =>
      scenario({
        ...o,
        gdd: 505,
        trees: [
          { id: "golden", name: "Golden", crop: "apple", stage: "full_bloom", bloomDaysAgo: 2, frost: { level: "severe", min: -3.4, t10: -2.2, t90: -3.9, inHours: 14 } , risks: { codling_moth: { dd: 2, biofix: null, awaiting: true }, powdery_mildew: { level: "watch", index: 30 } } },
          { id: "abricotier", name: "Abricotier", crop: "apricot", stage: "shuck_split", bloomDaysAgo: 32, frost: { level: "warning", min: -3.4, t10: -2.2, t90: -3.9, inHours: 14 } },
          { id: "cerisier", name: "Cerisier du fond", crop: "sweet_cherry", stage: "full_bloom", bloomDaysAgo: 3, frost: { level: "warning", min: -2.6, t10: -2.2, t90: -3.9, inHours: 14 } },
          { id: "peche", name: "Pêcher", crop: "peach", stage: "pink", gdd: 240, frost: { level: "watch", min: -2.5, t10: -3.9, t90: -9.4, inHours: 14 } },
        ],
      }),
    "Été : carpocapse et oïdium": (o) =>
      scenario({
        ...o,
        gdd: 1250,
        spray: { first: 3 * H },
        trees: [
          { id: "golden", name: "Golden", crop: "apple", stage: "full_bloom", bloomDaysAgo: 70, frost: { min: 13 }, risks: { codling_moth: { level: "severe", dd: 142, biofix: "2026-05-02", estimated: true }, powdery_mildew: { level: "warning", index: 70, interval: 7 } } },
          { id: "conference", name: "Conférence", crop: "pear", stage: "petal_fall", bloomDaysAgo: 75, frost: { min: 13 }, risks: { codling_moth: { level: "watch", dd: 60, biofix: "2026-05-02" }, powdery_mildew: { level: "warning", index: 62, interval: 7, protection: { status: "protected", product: "Soufre", protected_until: new Date(Date.now() + 5 * D).toISOString(), days_remaining: 5 } } } },
          { id: "tomates", name: "Tomates", crop: "tender_annual", stage: "growing", gdd: 1100, frost: { min: 13 }, risks: { late_blight: { level: "warning", hutton: true, days: 2 } } },
          { id: "vigne", name: "Vigne de la treille", crop: "vine", stage: "shoots_10cm", gdd: 1250, frost: { min: 13 }, risks: { grapevine_moth: { level: "warning", dd: 800 }, powdery_mildew: { level: "none", index: 10 } } },
          { id: "patates", name: "Pommes de terre", crop: "potato", stage: "emerged", gdd: 900, frost: { min: 13 }, risks: { colorado_potato_beetle: { level: "severe", dd: 140, biofix: "2026-06-10" } } },
          { id: "cerisier", name: "Burlat", crop: "sweet_cherry", stage: "post_bloom", bloomDaysAgo: 58, frost: { min: 13 }, risks: { cherry_fruit_fly: { level: "severe", dd: 560 } } },
        ],
      }),
    "Fin d'été : tout va bien": (o) =>
      scenario({
        ...o,
        gdd: 1600,
        spray: { open: true, first: 6 * H },
        recent: 12,
        trees: [
          { id: "golden", name: "Golden", crop: "apple", stage: "full_bloom", bloomDaysAgo: 135, frost: { min: 12 }, risks: { codling_moth: { dd: 620, biofix: "2026-05-02" } } },
          { id: "conference", name: "Conférence", crop: "pear", stage: "petal_fall", bloomDaysAgo: 136, frost: { min: 12 } },
          { id: "prunier", name: "Reine-Claude", crop: "plum", stage: "post_bloom", bloomDaysAgo: 118, frost: { min: 12 } },
          { id: "abricotier", name: "Abricotier", crop: "apricot", stage: "shuck_split", bloomDaysAgo: 140, frost: { min: 12 } },
          { id: "tomates", name: "Tomates", crop: "tender_annual", stage: "growing", gdd: 1600, frost: { min: 12 } },
          { id: "choux", name: "Choux", crop: "hardy_vegetable", stage: "growing", frost: { min: 12 } },
        ],
      }),
    "Début de saison : bourgeons": (o) =>
      scenario({
        ...o,
        gdd: 150,
        recent: 5,
        spray: { first: 20 * H },
        trees: [
          { id: "golden", name: "Golden", crop: "apple", stage: "green_tip", frost: { min: 4 } },
          { id: "abricotier", name: "Abricotier", crop: "apricot", stage: "first_white", frost: { min: 4 } },
          { id: "prunier", name: "Prunier", crop: "plum", stage: "side_white", frost: { min: 4 } },
          { id: "cerisier", name: "Cerisier", crop: "sweet_cherry", stage: "swollen_bud", frost: { min: 4 } },
          { id: "vigne", name: "Vigne", crop: "vine", stage: "dormant", gdd: 90, frost: { min: 4 } },
          { id: "patates", name: "Pommes de terre", crop: "potato", stage: "off_season", frost: { min: 4 } },
        ],
      }),
    "Toutes les cultures": (o) =>
      scenario({
        ...o,
        gdd: 1250,
        spray: { first: 6 * H },
        trees: [
          { id: "a1", name: "Pommier en fleurs", crop: "apple", stage: "full_bloom", bloomDaysAgo: 3, frost: { min: 9 } },
          { id: "a2", name: "Pommier en boutons", crop: "apple", stage: "first_pink", gdd: 340, frost: { min: 9 } },
          { id: "a3", name: "Pommier feuilles", crop: "apple", stage: "half_inch_green", gdd: 210, frost: { min: 9 } },
          { id: "a4", name: "Pommier bourgeons", crop: "apple", stage: "silver_tip", gdd: 95, frost: { min: 9 } },
          { id: "b1", name: "Poirier", crop: "pear", stage: "petal_fall", bloomDaysAgo: 60, frost: { min: 9 } },
          { id: "b2", name: "Abricotier", crop: "apricot", stage: "shuck_split", bloomDaysAgo: 80, frost: { min: 9 } },
          { id: "b3", name: "Prunier", crop: "plum", stage: "post_bloom", bloomDaysAgo: 100, frost: { min: 9 } },
          { id: "b4", name: "Pêcher en fleurs", crop: "peach", stage: "full_bloom", bloomDaysAgo: 2, frost: { min: 9 } },
          { id: "c1", name: "Cerisier", crop: "sweet_cherry", stage: "post_bloom", bloomDaysAgo: 50, frost: { min: 9 } },
          { id: "c2", name: "Vigne (repos)", crop: "vine", stage: "dormant", gdd: 40, frost: { min: 9 } },
          { id: "c3", name: "Vigne (feuilles)", crop: "vine", stage: "first_leaves", gdd: 320, frost: { min: 9 } },
          { id: "c4", name: "Vigne (raisin)", crop: "vine", stage: "shoots_10cm", gdd: 1500, frost: { min: 9 } },
          { id: "d1", name: "Tomates jeunes", crop: "tender_annual", stage: "growing", gdd: 300, frost: { min: 9 } },
          { id: "d2", name: "Tomates mûres", crop: "tender_annual", stage: "growing", gdd: 1300, frost: { min: 9 } },
          { id: "d3", name: "Pommes de terre", crop: "potato", stage: "emerged", gdd: 800, frost: { min: 9 } },
          { id: "d4", name: "Choux", crop: "hardy_vegetable", stage: "growing", frost: { min: 9 } },
        ],
      }),
    "Un seul arbre": (o) =>
      scenario({
        ...o,
        gdd: 800,
        spray: { first: 6 * H },
        trees: [
          { id: "golden", name: "Pommier du fond du jardin", crop: "apple", stage: "full_bloom", bloomDaysAgo: 30, frost: { min: 8 }, risks: { powdery_mildew: { level: "watch", index: 40 }, codling_moth: { level: "warning", dd: 125, biofix: "2026-05-02" } } },
        ],
      }),
    "Verger vide": (o) => makeHass({}, {}, o),
  };

  root.CARD_SCENARIOS = SCENARIOS;
})(typeof window !== "undefined" ? window : globalThis);
