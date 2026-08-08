/**
 * Carte Météo Sentinelle — chronologie des risques du verger.
 *
 * Une carte plutôt qu'un tableau de bord bricolé, pour une raison
 * précise : un niveau de risque instantané ne dit pas grand-chose. Ce
 * qui informe, c'est la *trajectoire* — depuis quand le mildiou est
 * favorable, quand la prochaine fenêtre de traitement s'ouvre, si le
 * gel annoncé tombe avant ou après.
 *
 * La carte affiche donc une seule chronologie continue, coupée en son
 * milieu par l'instant présent :
 *
 *   passé (historique du recorder)  |  futur (prévisions)
 *   ────────────────────────────────┼────────────────────────────────
 *   bandes de niveau par risque     │  fenêtres de pulvérisation,
 *                                   │  prochaine gelée annoncée
 *
 * Aucune dépendance, aucun build : le fichier est servi tel quel par
 * l'intégration, ce qui évite à l'utilisateur d'installer un dépôt
 * frontend séparé et d'ajouter une ressource à la main.
 */

const CARD_TYPE = "meteo-sentinelle-card";
const DOMAIN = "meteo_sentinelle";

const LEVELS = ["none", "watch", "warning", "severe"];

const LEVEL_COLORS = {
  none: "var(--state-inactive-color, #b9bfc7)",
  watch: "var(--warning-color, #ffa600)",
  warning: "#f57c00",
  severe: "var(--error-color, #db4437)",
  unknown: "var(--disabled-color, #6f7378)",
};

const STRINGS = {
  fr: {
    now: "maintenant",
    spray: "Fenêtre de traitement",
    frost: "Gelée annoncée",
    noEntities:
      "Aucune entité Météo Sentinelle trouvée. Ajoutez des arbres depuis la page de l'intégration, ou listez les entités dans la configuration de la carte.",
    hoursBack: "Heures affichées dans le passé",
    hoursForward: "Heures affichées dans le futur",
    title: "Titre",
    entities: "Entités (une par ligne, vide = détection automatique)",
    awaitingBiofix: "en attente du biofix",
    estimated: "biofix estimé",
    partial: "cumul incomplet",
    levels: {
      none: "Aucun",
      watch: "Vigilance",
      warning: "Alerte",
      severe: "Danger",
    },
    stages: {
      flight: "vol en cours",
      egg_laying: "pontes",
      hatch_start: "début d'éclosion",
      hatch_peak: "éclosion généralisée",
      oviposition_peak: "pic de ponte",
      second_generation: "2e génération",
      approach: "émergence proche",
      emergence: "émergence",
      oviposition: "ponte en cours",
      eggs: "pontes déposées",
      instar_1: "larves L1",
      instar_2: "larves L2",
      instar_3: "larves L3",
      instar_4: "larves L4",
      pupation: "nymphose",
      first_flight: "1er vol",
      first_generation: "larves G1",
      second_flight: "2e vol",
      third_flight: "3e vol",
      third_generation: "larves G3",
    },
  },
  en: {
    now: "now",
    spray: "Spray window",
    frost: "Frost expected",
    noEntities:
      "No Météo Sentinelle entity found. Add trees from the integration page, or list entities in the card configuration.",
    hoursBack: "Hours shown in the past",
    hoursForward: "Hours shown in the future",
    title: "Title",
    entities: "Entities (one per line, empty = auto-detect)",
    awaitingBiofix: "waiting for biofix",
    estimated: "estimated biofix",
    partial: "partial accumulation",
    levels: {
      none: "None",
      watch: "Watch",
      warning: "Warning",
      severe: "Severe",
    },
    stages: {
      flight: "flight under way",
      egg_laying: "egg laying",
      hatch_start: "hatch starting",
      hatch_peak: "peak hatch",
      oviposition_peak: "peak oviposition",
      second_generation: "2nd generation",
      approach: "emergence near",
      emergence: "emergence",
      oviposition: "egg laying",
      eggs: "eggs laid",
      instar_1: "1st instar",
      instar_2: "2nd instar",
      instar_3: "3rd instar",
      instar_4: "4th instar",
      pupation: "pupation",
      first_flight: "1st flight",
      first_generation: "1st gen. larvae",
      second_flight: "2nd flight",
      third_flight: "3rd flight",
      third_generation: "3rd gen. larvae",
    },
  },
};

function t(hass) {
  const lang = (hass?.locale?.language || hass?.language || "en").slice(0, 2);
  return STRINGS[lang] || STRINGS.en;
}

/** Entités de risque de l'intégration, ordonnées par arbre. */
function discoverEntities(hass) {
  const found = [];
  for (const [entityId, state] of Object.entries(hass.states)) {
    if (!entityId.startsWith("sensor.")) continue;

    // Le registre est la source fiable ; l'attribut sert de repli quand
    // il n'est pas exposé au frontend.
    const registry = hass.entities?.[entityId];
    const mine = registry
      ? registry.platform === DOMAIN
      : Boolean(state.attributes?.tree && state.attributes?.crop);
    if (!mine) continue;

    // Seules les entités dont l'état est un niveau de risque nous
    // intéressent : les capteurs d'indice ou d'échéance ont leur place
    // ailleurs.
    if (!LEVELS.includes(state.state)) continue;
    found.push(entityId);
  }
  return found.sort((a, b) => {
    const at = hass.states[a].attributes?.tree || "";
    const bt = hass.states[b].attributes?.tree || "";
    return at.localeCompare(bt) || a.localeCompare(b);
  });
}

function sprayEntity(hass) {
  for (const [entityId, state] of Object.entries(hass.states)) {
    if (!entityId.startsWith("sensor.")) continue;
    const registry = hass.entities?.[entityId];
    if (registry && registry.platform !== DOMAIN) continue;
    if (state.attributes?.windows && state.attributes?.max_wind_kmh !== undefined) {
      return state;
    }
  }
  return null;
}

/** Segments [{level, from, to}] reconstruits depuis l'historique. */
function toSegments(points, start, end) {
  if (!points.length) return [{ level: "unknown", from: start, to: end }];
  const segments = [];
  for (let i = 0; i < points.length; i += 1) {
    const from = Math.max(points[i].time, start);
    const to = i + 1 < points.length ? points[i + 1].time : end;
    if (to <= from) continue;
    segments.push({ level: points[i].level, from, to });
  }
  if (segments.length && segments[0].from > start) {
    segments.unshift({ level: "unknown", from: start, to: segments[0].from });
  }
  return segments;
}

class MeteoSentinelleCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement(`${CARD_TYPE}-editor`);
  }

  static getStubConfig() {
    return { type: `custom:${CARD_TYPE}`, hours_back: 24, hours_forward: 24 };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._history = {};
    this._loading = false;
    this._lastFetch = 0;
  }

  setConfig(config) {
    this._config = {
      hours_back: 24,
      hours_forward: 24,
      entities: [],
      ...config,
    };
    this._history = {};
    this._lastFetch = 0;
  }

  getCardSize() {
    return 3 + Math.min(6, this._entities()?.length || 1);
  }

  set hass(hass) {
    this._hass = hass;
    // L'historique est coûteux : on ne le relit qu'à intervalle
    // raisonnable, le rendu suit à chaque mise à jour d'état.
    if (Date.now() - this._lastFetch > 120000) {
      this._fetchHistory();
    }
    this._render();
  }

  _entities() {
    if (!this._hass) return [];
    const configured = (this._config?.entities || []).filter(Boolean);
    return configured.length ? configured : discoverEntities(this._hass);
  }

  async _fetchHistory() {
    const entities = this._entities();
    if (!this._hass || !entities.length || this._loading) return;
    this._loading = true;
    this._lastFetch = Date.now();

    const end = new Date();
    const start = new Date(end.getTime() - this._config.hours_back * 3600000);

    try {
      const response = await this._hass.connection.sendMessagePromise({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: entities,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });

      const history = {};
      for (const [entityId, points] of Object.entries(response || {})) {
        history[entityId] = (points || [])
          .map((point) => ({
            level: LEVELS.includes(point.s) ? point.s : "unknown",
            time: (point.lu || 0) * 1000,
          }))
          .filter((point) => point.time > 0)
          .sort((a, b) => a.time - b.time);
      }
      this._history = history;
    } catch (err) {
      // Sans recorder, la carte reste utile : elle n'affiche que le
      // présent et le futur au lieu d'échouer.
      this._history = {};
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _openMoreInfo(entityId) {
    const event = new CustomEvent("hass-more-info", {
      detail: { entityId },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  _render() {
    if (!this._hass || !this._config) return;
    const strings = t(this._hass);
    const entities = this._entities();

    const now = Date.now();
    const start = now - this._config.hours_back * 3600000;
    const end = now + this._config.hours_forward * 3600000;
    const span = end - start;
    const pct = (value) => ((Math.min(Math.max(value, start), end) - start) / span) * 100;

    const rows = entities
      .map((entityId) => {
        const state = this._hass.states[entityId];
        if (!state) return "";

        const points = this._history[entityId] || [];
        const segments = toSegments(points, start, now);
        // Le niveau courant est prolongé jusqu'au bord droit : c'est
        // une persistance, pas une prévision, d'où le hachurage.
        const bars = segments
          .map(
            (segment) =>
              `<span class="seg" style="left:${pct(segment.from)}%;width:${
                pct(segment.to) - pct(segment.from)
              }%;background:${LEVEL_COLORS[segment.level]}"></span>`
          )
          .join("");

        const current = LEVELS.includes(state.state) ? state.state : "unknown";
        const projected = `<span class="seg projected" style="left:${pct(
          now
        )}%;width:${100 - pct(now)}%;background:${LEVEL_COLORS[current]}"></span>`;

        // Deux « stades » cohabitent : celui de la plante et celui du
        // cycle de l'insecte. Le second est plus informatif quand il
        // existe, puisqu'il porte l'urgence.
        const attributes = state.attributes || {};
        const cycle = attributes.cycle_stage
          ? strings.stages[attributes.cycle_stage] || attributes.cycle_stage
          : "";
        const stage = cycle || attributes.stage_label || attributes.stage || "";

        const notes = [];
        if (attributes.awaiting_biofix) notes.push(strings.awaitingBiofix);
        if (attributes.biofix_estimated) notes.push(strings.estimated);
        if (attributes.incomplete_season) notes.push(strings.partial);

        const detail = [strings.levels[current] || current, stage, ...notes]
          .filter(Boolean)
          .join(" · ");

        return `
          <div class="row" data-entity="${entityId}">
            <div class="label">
              <span class="name">${attributes.friendly_name || entityId}</span>
              <span class="sub">${detail}</span>
            </div>
            <div class="track">${bars}${projected}</div>
          </div>`;
      })
      .join("");

    // Bande des fenêtres de pulvérisation, côté futur uniquement.
    const spray = sprayEntity(this._hass);
    let sprayRow = "";
    if (spray) {
      const windows = (spray.attributes.windows || [])
        .map((window) => {
          const from = Date.parse(window.start);
          const to = Date.parse(window.end);
          if (!from || !to || to < now) return "";
          return `<span class="seg spray" style="left:${pct(from)}%;width:${
            pct(to) - pct(from)
          }%" title="${window.start} → ${window.end}"></span>`;
        })
        .join("");

      sprayRow = `
        <div class="row" data-entity="${spray.entity_id}">
          <div class="label">
            <span class="name">${strings.spray}</span>
            <span class="sub">${
              spray.attributes.open_now ? "✓" : ""
            } ${spray.state ? new Date(spray.state).toLocaleString() : "—"}</span>
          </div>
          <div class="track">${windows}</div>
        </div>`;
    }

    // Repère de la prochaine gelée annoncée, tous arbres confondus.
    const frostTimes = entities
      .map((id) => this._hass.states[id]?.attributes?.next_frost_time)
      .filter(Boolean)
      .map((value) => Date.parse(value))
      .filter((value) => value && value > now);
    const frostMarker = frostTimes.length
      ? `<span class="marker frost" style="left:${pct(
          Math.min(...frostTimes)
        )}%" title="${strings.frost}"></span>`
      : "";

    const body = entities.length
      ? `${rows}${sprayRow}`
      : `<div class="empty">${strings.noEntities}</div>`;

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 12px 16px 16px; }
        .header {
          font-size: var(--ha-card-header-font-size, 22px);
          font-weight: 400;
          padding: 4px 0 12px;
        }
        .row {
          display: grid;
          grid-template-columns: minmax(110px, 34%) 1fr;
          gap: 10px;
          align-items: center;
          padding: 5px 0;
          cursor: pointer;
        }
        .row:hover .name { text-decoration: underline; }
        .label { display: flex; flex-direction: column; min-width: 0; }
        .name {
          font-size: 13px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .sub {
          font-size: 11px;
          color: var(--secondary-text-color);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .track {
          position: relative;
          height: 16px;
          border-radius: 8px;
          overflow: hidden;
          background: var(--divider-color, #e0e0e0);
        }
        .seg { position: absolute; top: 0; bottom: 0; }
        .projected { opacity: 0.35; }
        .spray {
          background: repeating-linear-gradient(
            45deg,
            var(--success-color, #43a047),
            var(--success-color, #43a047) 5px,
            rgba(255, 255, 255, 0.45) 5px,
            rgba(255, 255, 255, 0.45) 10px
          );
        }
        .axis {
          position: relative;
          height: 18px;
          margin-top: 6px;
          margin-left: calc(34% + 10px);
          border-top: 1px solid var(--divider-color, #e0e0e0);
        }
        .now {
          position: absolute;
          top: -4px;
          bottom: 0;
          width: 2px;
          background: var(--primary-color, #03a9f4);
        }
        .now span {
          position: absolute;
          top: 4px;
          left: 4px;
          font-size: 10px;
          color: var(--primary-color, #03a9f4);
          white-space: nowrap;
        }
        .tick {
          position: absolute;
          top: 2px;
          font-size: 10px;
          color: var(--secondary-text-color);
          transform: translateX(-50%);
        }
        .marker.frost {
          position: absolute;
          top: -6px;
          width: 0;
          height: 0;
          border-left: 5px solid transparent;
          border-right: 5px solid transparent;
          border-top: 7px solid var(--info-color, #039be5);
          transform: translateX(-50%);
        }
        .empty {
          padding: 16px 0;
          color: var(--secondary-text-color);
          font-size: 13px;
        }
      </style>
      <ha-card>
        ${this._config.title ? `<div class="header">${this._config.title}</div>` : ""}
        ${body}
        <div class="axis">
          <span class="tick" style="left:0%">-${this._config.hours_back}h</span>
          <span class="tick" style="left:100%">+${this._config.hours_forward}h</span>
          <span class="now" style="left:${pct(now)}%"><span>${strings.now}</span></span>
          ${frostMarker}
        </div>
      </ha-card>`;

    this.shadowRoot.querySelectorAll(".row").forEach((row) => {
      row.addEventListener("click", () =>
        this._openMoreInfo(row.dataset.entity)
      );
    });
  }
}

class MeteoSentinelleCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { hours_back: 24, hours_forward: 24, entities: [], ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _emit(changes) {
    this._config = { ...this._config, ...changes };
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this._config || this._rendered) {
      if (this._rendered) return;
    }
    const strings = t(this._hass);
    this._rendered = true;

    this.innerHTML = `
      <style>
        .field { display: flex; flex-direction: column; margin-bottom: 12px; }
        label { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 4px; }
        input, textarea {
          font: inherit;
          padding: 8px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #000);
        }
        textarea { min-height: 76px; resize: vertical; }
      </style>
      <div class="field">
        <label for="ms-title">${strings.title}</label>
        <input id="ms-title" type="text" value="${this._config.title || ""}">
      </div>
      <div class="field">
        <label for="ms-back">${strings.hoursBack}</label>
        <input id="ms-back" type="number" min="1" max="168" value="${
          this._config.hours_back
        }">
      </div>
      <div class="field">
        <label for="ms-fwd">${strings.hoursForward}</label>
        <input id="ms-fwd" type="number" min="1" max="168" value="${
          this._config.hours_forward
        }">
      </div>
      <div class="field">
        <label for="ms-entities">${strings.entities}</label>
        <textarea id="ms-entities">${(this._config.entities || []).join("\n")}</textarea>
      </div>`;

    this.querySelector("#ms-title").addEventListener("change", (event) =>
      this._emit({ title: event.target.value || undefined })
    );
    this.querySelector("#ms-back").addEventListener("change", (event) =>
      this._emit({ hours_back: Number(event.target.value) || 24 })
    );
    this.querySelector("#ms-fwd").addEventListener("change", (event) =>
      this._emit({ hours_forward: Number(event.target.value) || 24 })
    );
    this.querySelector("#ms-entities").addEventListener("change", (event) =>
      this._emit({
        entities: event.target.value
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
      })
    );
  }
}

if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, MeteoSentinelleCard);
  customElements.define(`${CARD_TYPE}-editor`, MeteoSentinelleCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "Météo Sentinelle",
    description:
      "Chronologie des risques du verger : historique des niveaux, fenêtres de traitement et gelée annoncée.",
    preview: true,
    documentationURL: "https://github.com/Sdavid66/Meteo-Sentinelle",
  });
}
