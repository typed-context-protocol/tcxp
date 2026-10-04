// The decision flow: query box → sensors → gates (diamonds) → SQL card.
// Mirrors tcxp.flow.Flow (Python). State is one address; every change is a trace row.
import { Address, encode } from "../index.js";
import { compileCard } from "./card.js";
import { Gate, parseHandler } from "./gate.js";
import { evaluate, wordRe } from "./tql.js";
import { QueryCard, parseCsv, taxYearBounds } from "./sql.js";

export const STOPPING = ["core.ask", "core.halt"];

export const PAYROLL_CSV = `employee,role,country,pay_date,wages,qualified_pct,project
E-101,Engineer,US,2024-01-31,15000,0.80,Atlas (2025 launch)
E-102,Engineer,US,2024-01-31,14000,0.75,Atlas (2025 launch)
E-201,Engineer,CA,2024-01-31,12000,0.80,Atlas (2025 launch)
E-101,Engineer,US,2024-06-30,15500,0.80,Atlas (2025 launch)
E-102,Engineer,US,2024-06-30,14500,0.70,Atlas (2025 launch)
E-301,Designer,US,2024-06-30,9000,0.20,Atlas (2025 launch)
E-201,Engineer,CA,2024-06-30,12500,0.80,Atlas (2025 launch)
E-101,Engineer,US,2024-12-31,16000,0.85,Atlas (2025 launch)
E-102,Engineer,US,2024-12-31,15000,0.70,Atlas (2025 launch)
E-101,Engineer,US,2025-01-31,16500,0.60,Atlas (2025 launch)
E-102,Engineer,US,2025-01-31,15500,0.50,Atlas (2025 launch)
E-401,Engineer,US,2025-03-31,13000,0.90,Beacon
E-201,Engineer,CA,2025-03-31,13000,0.80,Atlas (2025 launch)`;

const YEAR = "(20\\d{2})";
const kw = (words) => new RegExp("\\b(?:" + words.split("|").map((w) => w.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")\\b", "gi");

/** The Section 41 sensors (what tcxp recognizes as you type). Highlighting from cards is separate. */
export const SENSORS = [
  { id: "task", re: kw("deduct|deduction|credit|section 41|r&d|qre|qres|qualified research"),
    actions: ["@core.update?task=section_41_qre&task.meaning=!tcxp:/tax/us/irc-41", "@core.highlight?color=yellow"] },
  { id: "country-us", re: kw("us-based|us based|in the us|united states|u.s.|us employees"),
    actions: ["@core.update?country=US&country.meaning=!tcxp:/geo/iso-3166/US", "@core.highlight?color=cyan"] },
  { id: "tax-year", re: new RegExp(`\\b(?:tax\\s*year|fiscal\\s*year|tax\\s*return|return|filing)\\s*(?:of|for|is|:)?\\s*'?${YEAR}\\b`, "gi"),
    actions: ["@core.update?tax_year={1}&tax_year.structure=!tcxp:/schema/year/yyyy", "@core.highlight?color=green"] },
  { id: "tax-year-before", re: new RegExp(`\\b${YEAR}\\s+(?:tax\\s*year|tax\\s*return|return|filing)\\b`, "gi"),
    actions: ["@core.update?tax_year={1}&tax_year.structure=!tcxp:/schema/year/yyyy", "@core.highlight?color=green"] },
  { id: "fiscal-short", re: /\bFY\s?'?(\d{2})\b/gi,
    actions: ["@core.update?tax_year=20{1}&tax_year.structure=!tcxp:/schema/year/yyyy", "@core.highlight?color=green"] },
];

export const DEMO_CARDS = [
  ["For Section 41 tax preparation, when we get CSVs, require the tax year.", "manager"],
  ["If false, alert that it's halted and you cannot proceed.", "manager"],
  ["If the query contains yesterday, highlight it.", "manager"],
];

export function describe(action) {
  const [name, p] = parseHandler(action);
  if (name === "core.ask") return "ask for " + [].concat(p.key || []).join(", ");
  if (name === "core.halt") return "halt";
  if (name === "core.notify") return `alert "${p.message || ""}"`;
  if (name === "core.highlight") return p.word ? `highlight "${p.word}"` : "highlight";
  if (name === "core.log") return `note "${p.message || ""}"`;
  if (name === "core.update") return "set " + Object.entries(p).map(([k, v]) => `${k}=${v}`).join(", ");
  return "@" + name;
}

export class Flow {
  constructor({ path = "reason/section-41", params = { query: "", task: "", country: "", tax_year: "" },
                sensors = SENSORS, card = null, tables = null } = {}) {
    this.address = Address.parse(`!tcxp:/${path}`).with(params);
    this.sensors = sensors;
    this.gates = [];
    this.trace = [];
    this.card = card ?? new QueryCard("us-wages", "US wages in the tax year",
      "SELECT SUM(wages) FROM payroll WHERE country = :country AND pay_date BETWEEN :start_date AND :end_date", taxYearBounds);
    this.tables = tables ?? { payroll: parseCsv(PAYROLL_CSV) };
    this.listeners = new Set();
    this.log("set", "", "", "init");
  }

  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  emit(event) { for (const fn of this.listeners) fn(event, this); }

  log(op, key, value, cause) {
    this.trace.push({ index: this.trace.length, time: new Date().toISOString(), op, key, value, cause, address: this.address.toString() });
  }

  set(values, cause) {
    const next = this.address.with(values);
    if (next.toString() === this.address.toString()) return;
    this.address = next;
    for (const [k, v] of Object.entries(values)) this.log("set", k, String(v ?? ""), cause);
  }

  state() { return this.address.toObject(); }

  // ---- gates ----
  put(gate, cause) {
    const i = this.gates.findIndex((g) => g.id === gate.id);
    if (i >= 0) this.gates[i] = gate; else this.gates.push(gate);
    this.log("trigger", "gate", gate.address().toString(), cause);
    this.emit("gates");
    return gate;
  }
  addCard(text, { by = "manager", target = "" } = {}) {
    return this.put(compileCard(text, this.gates, { by, target }).gate, `card:${by}`);
  }
  /** Same as calling @core.approve?gate=<id>&by=<who>: the approval is a recorded call. */
  approve(id, by) {
    const g = this.gates.find((x) => x.id === id);
    if (!g) throw new Error(`No gate ${id}`);
    if (!by) throw new Error("approve needs who approved");
    this.log("trigger", "core.approve", `@core.approve?gate=${id}&by=${encode(by)}`, `person:${by}`);
    return this.put(g.with({ status: "approved", approvedBy: by }), `person:${by}`);
  }
  remove(id) {
    this.gates = this.gates.filter((g) => g.id !== id);
    this.log("trigger", "gate", "", `removed:${id}`);
    this.emit("gates");
  }

  // ---- run ----
  run(query) {
    const out = { query, steps: [], stoppedAt: "", asks: [], alerts: [], notes: [], halted: "", highlights: [] };
    this.set({ query }, "input:query");
    for (const s of this.sensors) {                       // observe
      for (const m of query.matchAll(s.re)) {
        if (!m[0]) continue;
        for (const a of s.actions) {
          const filled = a.replace(/\{(\d+)\}/g, (_, n) => encode(m[Number(n)] ?? ""));
          this.call(filled, `sensor:${s.id}`, out, { start: m.index, end: m.index + m[0].length, sensor: s.id });
        }
      }
    }
    const state = this.state();
    const order = new Map(this.gates.map((g, i) => [g.id, i]));
    const seen = new Set();
    for (let i = 0; i >= 0 && i < this.gates.length;) {
      const g = this.gates[i];
      if (seen.has(g.id)) break;
      seen.add(g.id);
      const [result, dark] = evaluate(g.test, state);
      const branch = result ? "true" : "false";
      const acts = result ? g.ifTrue : g.ifFalse;
      out.steps.push({ gate: g.id, result, branch, actions: acts, fired: g.approved, dark });
      this.log("decide", g.id, result === null ? `false (dark: ${dark.join(", ")})` : branch, `gate:${g.id}`);
      let stop = false;
      if (g.approved) {
        for (const k of dark) if (!out.asks.includes(k)) out.asks.push(k);
        for (const a of acts) {
          const [name, p] = parseHandler(a);
          if (name === "core.highlight" && p.word) {
            for (const m of query.matchAll(wordRe(p.word))) this.call(a, `gate:${g.id}`, out, { start: m.index, end: m.index + m[0].length, sensor: g.id });
            continue;
          }
          this.call(a, `gate:${g.id}`, out);
          stop = stop || STOPPING.includes(name);
        }
        if (dark.length && !acts.length) stop = true;
      }
      if (stop) { out.stoppedAt = g.id; break; }
      const next = result ? g.nextTrue : g.nextFalse;
      i = next && order.has(next) ? order.get(next) : i + 1;
    }
    const st = this.state();
    out.card = { sql: this.card.template, filled: this.card.fill(st), missing: this.card.missing(st) };
    if (!out.stoppedAt && !out.card.missing.length) {
      try { out.card.result = this.card.run(this.tables, st); } catch (e) { out.card.error = String(e.message || e); }
    }
    out.address = this.address.toString();
    this.last = out;
    this.emit("run");
    return out;
  }

  /** Only built-in core handlers run here: they act on this flow and nothing else. */
  call(action, cause, out, spike = null) {
    const [name, p] = parseHandler(action);
    if (name === "core.update") {
      this.set(Object.fromEntries(Object.entries(p).filter(([k]) => !k.startsWith("_"))), cause);
    } else if (name === "core.highlight") {
      if (spike) out.highlights.push({ color: p.color || "yellow", ...spike });
    } else if (name === "core.ask") {
      for (const k of [].concat(p.key || [])) if (!out.asks.includes(k)) out.asks.push(k);
    } else if (name === "core.halt") {
      out.halted = p.reason || "halted";
    } else if (name === "core.notify") {
      out.alerts.push(p.message || "");
    } else if (name === "core.log") {
      out.notes.push(p.message || "");
    } else {
      throw new Error(`@${name} is not available in the browser flow`);
    }
    if (!["core.update", "core.highlight"].includes(name)) this.log("trigger", name, action, cause);
  }

  static demo({ approved = true } = {}) {
    const f = new Flow();
    for (const [text, by] of DEMO_CARDS) {
      const g = f.addCard(text, { by });
      if (approved) f.approve(g.id, by);
    }
    return f;
  }
}
