// tcxp for JavaScript: address parsing and canonical form.
// Mirrors the Python reference (tcxp.address). Both pass conformance/vectors.json.

const UNRESERVED = /[A-Za-z0-9\-._~]/;
const VALUE_SAFE = /[A-Za-z0-9\-._~!:\/@]/;
const KEY_RE = /^[A-Za-z0-9_.\-]+$/;
const SEG_RE = /^[A-Za-z0-9._~\-]+$/;
const HOST_RE = /^[A-Za-z0-9.\-]+(:[0-9]+)?$/;
export const VIRTUAL_PREFIX = "!tcxp:/";
export const MAX_INLINE = 2000;

export class AddressError extends Error {}

export function encode(text, safe = VALUE_SAFE) {
  if (/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(text))
    throw new AddressError("Text contains an invalid Unicode character (a lone surrogate)");
  let out = "";
  for (const byte of new TextEncoder().encode(text)) {
    const ch = String.fromCharCode(byte);
    out += byte < 128 && safe.test(ch) ? ch : "%" + byte.toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}

export function decode(text) {
  const bytes = [];
  for (let i = 0; i < text.length; ) {
    if (text[i] === "%") {
      const pair = text.slice(i + 1, i + 3);
      if (!/^[0-9a-fA-F]{2}$/.test(pair)) throw new AddressError(`Bad percent-encoding near ${text.slice(i, i + 3)}`);
      bytes.push(parseInt(pair, 16));
      i += 3;
    } else {
      const cp = text.codePointAt(i);                 // whole code points, so emoji survive
      const ch = String.fromCodePoint(cp);
      bytes.push(...new TextEncoder().encode(ch));
      i += ch.length;
    }
  }
  try {
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(new Uint8Array(bytes));
  } catch {
    throw new AddressError("Percent-encoded bytes are not valid UTF-8");
  }
}

export const isAddressText = (v) => typeof v === "string" && (v.startsWith(VIRTUAL_PREFIX) || v.startsWith("tcxp:"));

function canonicalPointer(text) {
  if (!isAddressText(text)) return text;
  try { return Address.parse(text).toString(); } catch (e) { if (e instanceof AddressError) return text; throw e; }
}

export function parseQuery(query) {
  const groups = new Map();
  if (!query) return groups;
  for (const part of query.split("&")) {
    if (part === "") throw new AddressError("Empty parameter");
    const eq = part.indexOf("=");
    const key = decode(eq < 0 ? part : part.slice(0, eq));
    if (!KEY_RE.test(key)) throw new AddressError(`Key ${key} may only use letters, digits, '_', '.', '-'`);
    let value = eq < 0 ? "" : decode(part.slice(eq + 1));
    value = canonicalPointer(value);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(value);
  }
  return groups;
}

export class Address {
  constructor(form = "virtual", path = [], params = [], authority = "") {
    this.form = form;
    this.path = Object.freeze([...path]);
    this.params = Object.freeze(params.map(([k, v]) => Object.freeze([k, Object.freeze([...v])])));
    this.authority = authority;
    Object.freeze(this);
  }

  static parse(text) {
    if (typeof text !== "string") throw new AddressError("Address text must be a string");
    if (text.includes("#")) throw new AddressError("Fragments ('#') are not part of tcxp state");
    for (const ch of text) {
      const cp = ch.codePointAt(0);
      if (cp < 0x21 || cp > 0x7e)
        throw new AddressError(`Character U+${cp.toString(16).toUpperCase().padStart(4, "0")} must be percent-encoded`);
    }
    const q = text.indexOf("?");
    const rest = q < 0 ? text : text.slice(0, q);
    const query = q < 0 ? "" : text.slice(q + 1);
    let form, authority = "", path;
    if (rest.startsWith(VIRTUAL_PREFIX) || (rest.startsWith("tcxp:/") && !rest.startsWith("tcxp://"))) {
      const body = rest.startsWith("!") ? rest.slice("!tcxp:".length) : rest.slice("tcxp:".length);
      if (body.startsWith("//")) throw new AddressError("A virtual pointer has no host");
      form = "virtual";
      path = body.slice(1);
    } else if (rest.startsWith("tcxp://")) {
      const after = rest.slice("tcxp://".length);
      const slash = after.indexOf("/");
      authority = slash < 0 ? after : after.slice(0, slash);
      path = slash < 0 ? "" : after.slice(slash + 1);
      if (!authority || !HOST_RE.test(authority)) throw new AddressError(`Invalid host ${authority}`);
      form = "tcxp";
    } else if (rest.startsWith("https://")) {
      const after = rest.slice("https://".length);
      const marker = after.indexOf("/tcxp/");
      if (marker < 0 && after.endsWith("/tcxp")) { authority = after.slice(0, -"/tcxp".length); path = ""; }
      else if (marker < 0) throw new AddressError("An https carrier address must contain '/tcxp/'");
      else { authority = after.slice(0, marker); path = after.slice(marker + "/tcxp/".length); }
      const host = authority.split("/")[0];
      if (!host || !HOST_RE.test(host)) throw new AddressError(`Invalid host ${host}`);
      form = "https";
    } else {
      throw new AddressError("Expected '!tcxp:/', 'tcxp:/', 'tcxp://' or 'https://…/tcxp/'");
    }
    if (path.endsWith("/")) throw new AddressError("Paths cannot end with '/'");
    const segs = path ? path.split("/") : [];
    for (const s of segs) if (!SEG_RE.test(s)) throw new AddressError(`Invalid path segment ${s}`);
    const groups = parseQuery(query);
    const params = [...groups.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return new Address(form, segs, params, authority);
  }

  static prefix(form, authority) {
    if (form === "virtual") return VIRTUAL_PREFIX;
    if (form === "tcxp") return `tcxp://${authority}/`;
    if (form === "https") return `https://${authority}/tcxp/`;
    throw new AddressError(`Unknown form ${form}`);
  }

  toString() {
    const head = Address.prefix(this.form, this.authority) + this.path.join("/");
    const q = this.params.flatMap(([k, vals]) => vals.map((v) => `${k}=${encode(v)}`)).join("&");
    return q ? `${head}?${q}` : head;
  }

  toURI() {
    const t = this.toString();
    return this.form === "virtual" ? "tcxp:/" + t.slice(VIRTUAL_PREFIX.length) : t;
  }

  get(key, fallback = undefined) {
    const hit = this.params.find(([k]) => k === key);
    return hit ? hit[1][0] : fallback;
  }

  getAll(key) {
    const hit = this.params.find(([k]) => k === key);
    return hit ? [...hit[1]] : [];
  }

  toObject() {
    return Object.fromEntries(this.params.map(([k, v]) => [k, v.length === 1 ? v[0] : [...v]]));
  }

  with(values) {
    const groups = new Map(this.params.map(([k, v]) => [k, [...v]]));
    for (const [key, value] of Object.entries(values)) {
      if (!KEY_RE.test(key)) throw new AddressError(`Invalid key ${key}`);
      if (value === null || value === undefined) groups.delete(key);
      else if (Array.isArray(value)) groups.set(key, value.length ? value.map(toText) : [""]);
      else groups.set(key, [toText(value)]);
    }
    const params = [...groups.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return new Address(this.form, this.path, params, this.authority);
  }
}

function toText(v) {
  if (v instanceof Address) return v.toString();
  if (typeof v === "boolean") return v ? "true" : "false";
  return canonicalPointer(String(v));
}

export const VERSION = "0.1.0";
export const URI = Address.parse("!tcxp:/lib/tcxp").with({ version: VERSION, dialect: "tcxp-sql/0.1", runtime: "js" }).toString();
