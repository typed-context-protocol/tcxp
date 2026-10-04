// Reasoning cards: a sentence in plain language becomes a proposed gate, or actions on an
// existing gate's outcome. Same phrasings and output as tcxp.flow.compile_card (Python).
import { encode } from "../index.js";
import { Gate, PROPOSED } from "./gate.js";
import { formatTql, parseTql } from "./tql.js";

export class CardNotUnderstood extends Error {}

export const DEFAULT_SLOTS = {
  "tax year": "tax_year", "fiscal year": "tax_year", year: "tax_year", country: "country",
  "start date": "start_date", "end date": "end_date", client: "client", currency: "currency",
  "time zone": "timezone", timezone: "timezone", "date format": "date_format",
};

const quote = (s) => '"' + s.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';
const stripDash = (s) => s.replace(/^-+|-+$/g, "");

export function slug(text) {
  const s = stripDash(text.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
  return stripDash(s.slice(0, 48)) || "gate";
}

function factKey(phrase, slots) {
  let p = phrase.trim().toLowerCase().replace(/^(?:the|a|an|our|their)\s+/, "");
  p = p.replace(/\s+(?:is|are|be|was)\s+(?:known|confirmed|provided|given|present|set|stated)$/, "");
  if (Object.hasOwn(slots, p)) return slots[p];
  const key = p.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  if (!key || !/^[A-Za-z_][A-Za-z0-9_.]*$/.test(key)) throw new CardNotUnderstood(`Couldn't turn ${JSON.stringify(phrase)} into a key name`);
  return key;
}

const VERBS = "(?:alert|notify|warn|tell|highlight|ask|halt|stop|block|log|note)";
const HALT_WORDS = /\b(halt|halted|stop|stopped|cannot proceed|can't proceed|can not proceed|block|blocked)\b/;
const SPLIT = new RegExp(`\\s+(?:and|then|,)\\s+(?=(?:then\\s+)?${VERBS}\\b)|\\s*,\\s*(?=${VERBS}\\b)`, "i");

function actionsFrom(clause, gateId) {
  const c = clause.trim().replace(/[.!]+$/, "");
  const acts = [];
  for (let part of c.split(SPLIT).map((p) => p.trim()).filter(Boolean)) {
    part = part.replace(/^(?:then|do|send|show|raise)\s+(?:an?\s+)?/i, "");
    const low = part.toLowerCase();
    const v = (low.match(new RegExp("^" + VERBS)) || [""])[0];
    if (["alert", "notify", "warn", "tell"].includes(v)) {
      const msg = part.replace(/^(?:alert|notify|warn|tell)\w*\s*(?:them|the user|me|everyone)?\s*(?:that\s+)?/i, "").trim() || part;
      acts.push(`@core.notify?message=${encode(msg)}&gate=${gateId}`);
      if (HALT_WORDS.test(msg.toLowerCase())) acts.push(`@core.halt?reason=${encode(msg)}`);
    } else if (v === "highlight") {
      const m = part.match(/^highlight\s+(?:the\s+word\s+)?["']?([^"']+?)["']?$/i);
      const word = m ? m[1].trim() : "";
      acts.push(word && !["it", "them", "that", "this"].includes(word.toLowerCase())
        ? `@core.highlight?word=${encode(word)}&color=yellow` : "@core.highlight?color=yellow");
    } else if (v === "ask") {
      const m = part.match(/^ask\s+(?:for\s+|about\s+)?(.+)$/i);
      if (!m) throw new CardNotUnderstood(`Ask for what? ${JSON.stringify(part)}`);
      acts.push(`@core.ask?key=${factKey(m[1], DEFAULT_SLOTS)}`);
    } else if (["halt", "stop", "block"].includes(v)) {
      acts.push(`@core.halt?reason=${encode(part)}`);
    } else if (["log", "note"].includes(v)) {
      const msg = part.replace(/^(?:log|note)\s*(?:that\s+)?/i, "").trim() || part;
      acts.push(`@core.log?message=${encode(msg)}`);
    } else if (HALT_WORDS.test(low)) {
      acts.push(`@core.halt?reason=${encode(part)}`);
    } else {
      throw new CardNotUnderstood(`Couldn't find an action in ${JSON.stringify(part)}. Try: highlight it · ask for the tax year · alert that … · halt · note that …`);
    }
  }
  return acts;
}

/** Returns { gate, isNew }. Throws CardNotUnderstood (with phrasings that work) otherwise. */
export function compileCard(text, gates = [], { by = "", target = "", slots = {}, proposer = null } = {}) {
  const allSlots = { ...DEFAULT_SLOTS, ...slots };
  const t = text.trim().split(/\s+/).join(" ");
  const low = t.toLowerCase().replace(/[.!]+$/, "");

  // 1. outcome cards: "If false, …" / "If true, …" / "Otherwise, …"
  let m = t.match(/^(?:if\s+(false|true|not|no|yes)|(otherwise|else))\s*[,:]?\s*(?:then\s+)?(.+)$/i);
  if (m) {
    const branch = m[2] || ["false", "not", "no"].includes((m[1] || "").toLowerCase()) ? "false" : "true";
    const g = target ? gates.find((x) => x.id === target) : gates[gates.length - 1];
    if (!g) throw new CardNotUnderstood("An 'If false/If true' card attaches to a gate; add a gate first");
    const acts = actionsFrom(m[3], g.id);
    const field = branch === "false" ? "ifFalse" : "ifTrue";
    return { gate: g.with({ [field]: [...g[field], ...acts], status: PROPOSED, card: (g.card ? g.card + " | " : "") + t,
                            approvedBy: "" }), isNew: false };
  }
  // 2. TQL written directly
  m = t.match(/^(?:test|tql|check)\s*:\s*(.+)$/i);
  if (m) {
    const q = formatTql(parseTql(m[1]));
    return { gate: new Gate({ id: slug(q), test: q, card: t, by }), isNew: true };
  }
  // 3. "If the query contains X, highlight it"
  m = t.match(/^if\s+(?:the\s+)?(?:query|question|text|request|message)\s+(?:contains|mentions|has|says|includes)\s+(?:the\s+word\s+)?["']?([^"',]+?)["']?(?:\s*,\s*(?:then\s+)?|\s+then\s+)(.+)$/i);
  if (m) {
    const word = m[1].trim();
    const gid = slug(`mentions ${word}`);
    const acts = actionsFrom(m[2].replace(/\bhighlight\s+(?:it|that|them)\b/gi, "highlight"), gid)
      .map((a) => (a === "@core.highlight?color=yellow" ? `@core.highlight?word=${encode(word)}&color=yellow` : a));
    return { gate: new Gate({ id: gid, test: `has(query, ${quote(word)})`, ifTrue: acts, card: t, by }), isNew: true };
  }
  // 4. "require X" / "until X is confirmed"
  m = low.match(/\buntil\s+(.+?)\s+(?:is|are|has been|have been)\s+(?:known|confirmed|provided|given|stated)\b/)
    || low.match(/\b(?:require|requires|required|need|needs|must have|must include|make sure (?:we|they|you) have)\s+((?:the\s+)?[a-z][a-z0-9 _-]*?)(?=\s+(?:before|when|for|to|in|from|on)\b|[.,;]|$)/);
  if (m) {
    const key = factKey(m[1], allSlots);
    const gid = slug(`${key.replace(/_/g, " ")} required`);
    return { gate: new Gate({ id: gid, test: `known(${key})`, ifFalse: [`@core.ask?key=${key}`], card: t, by }), isNew: true };
  }
  // 5. a model proposes; code validates
  if (proposer) {
    const p = proposer(t);
    const q = formatTql(parseTql(String(p.test)));
    return { gate: new Gate({ id: p.id || slug(q), test: q, ifTrue: p.ifTrue || p.if_true || [],
                              ifFalse: p.ifFalse || p.if_false || [], card: t, by: by || "proposer" }), isNew: true };
  }
  throw new CardNotUnderstood("I couldn't turn that card into a gate. Phrasings that work: " +
    "'If the query contains yesterday, highlight it.' · 'For Section 41, require the tax year.' · " +
    "'If false, alert that we cannot proceed.' · 'Test: known(tax_year) and country = \"US\"'");
}
