// TQL, the tcxp query language for one yes/no question. Mirrors tcxp.flow (Python);
// both pass conformance/tql_vectors.json.
//   known(key)  dark(key)  has(key, "text")  key = "v" | != | < | > | <= | >= number
//   combined with and / or / not and parentheses.

export class TQLError extends Error {}

const TOK = /\s*(?:("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?)|(<=|>=|!=|=|<|>|\(|\)|,)|([A-Za-z_][A-Za-z0-9_.]*))/y;
const KINDS = ["str", "num", "op", "word"];
const NUM = /^-?\d+(?:\.\d+)?$/;
const OPS = ["=", "!=", "<", ">", "<=", ">="];

function tokens(text) {
  const out = [];
  const t = text.trim();
  let pos = 0;
  while (pos < t.length) {
    TOK.lastIndex = pos;
    const m = TOK.exec(t);
    if (!m || TOK.lastIndex === pos) throw new TQLError(`TQL: unexpected text at ${JSON.stringify(t.slice(pos, pos + 12))}`);
    const i = [1, 2, 3, 4].find((g) => m[g] !== undefined);
    out.push([KINDS[i - 1], m[i]]);
    pos = TOK.lastIndex;
  }
  return out;
}

const unquote = (s) => s.slice(1, -1).replace(/\\(.)/g, "$1");
const quote = (s) => '"' + s.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';

export function parseTql(text) {
  const toks = tokens(text);
  let i = 0;
  const peek = (n = 0) => toks[i + n] ?? ["end", ""];
  const take = (kind, value) => {
    const [k, v] = peek();
    if ((kind && k !== kind) || (value !== undefined && v.toLowerCase() !== value))
      throw new TQLError(`TQL: expected ${value ?? kind}, found ${JSON.stringify(v || "the end")}`);
    i++;
    return v;
  };
  const pOr = () => {
    let n = pAnd();
    while (peek()[1].toLowerCase() === "or") { take(); n = ["or", n, pAnd()]; }
    return n;
  };
  const pAnd = () => {
    let n = pNot();
    while (peek()[1].toLowerCase() === "and") { take(); n = ["and", n, pNot()]; }
    return n;
  };
  const pNot = () => {
    if (peek()[1].toLowerCase() === "not") { take(); return ["not", pNot()]; }
    return atom();
  };
  const atom = () => {
    const [k, v] = peek();
    if (v === "(") { take(); const n = pOr(); take("op", ")"); return n; }
    if (k !== "word") throw new TQLError(`TQL: expected a test, found ${JSON.stringify(v || "the end")}`);
    const fn = v.toLowerCase();
    if ((fn === "known" || fn === "dark") && peek(1)[1] === "(") {
      take(); take("op", "(");
      const key = take("word");
      take("op", ")");
      return [fn, key];
    }
    if (fn === "has" && peek(1)[1] === "(") {
      take(); take("op", "(");
      const key = take("word");
      take("op", ",");
      const s = take("str");
      take("op", ")");
      return ["has", key, unquote(s)];
    }
    const key = take("word");
    if (!OPS.includes(peek()[1])) throw new TQLError(`TQL: after ${JSON.stringify(key)} expected =, !=, <, >, <= or >=`);
    const op = take("op");
    const [k2, v2] = peek();
    if (k2 === "str") { take(); return ["cmp", key, op, unquote(v2)]; }
    if (k2 === "num") { take(); return ["cmp", key, op, v2]; }
    throw new TQLError(`TQL: expected a "quoted" value or a number after ${op}`);
  };
  const node = pOr();
  if (peek()[0] !== "end") throw new TQLError(`TQL: unexpected ${JSON.stringify(peek()[1])}`);
  return node;
}

export function formatTql(node) {
  const kind = node[0];
  if (kind === "known" || kind === "dark") return `${kind}(${node[1]})`;
  if (kind === "has") return `has(${node[1]}, ${quote(node[2])})`;
  if (kind === "cmp") return `${node[1]} ${node[2]} ${NUM.test(node[3]) ? node[3] : quote(node[3])}`;
  if (kind === "not") {
    const inner = formatTql(node[1]);
    return ["known", "dark", "has", "not"].includes(node[1][0]) ? `not ${inner}` : `not (${inner})`;
  }
  const [a, b] = node.slice(1).map((n) => (!["and", "or"].includes(n[0]) || n[0] === kind ? formatTql(n) : `(${formatTql(n)})`));
  return `${a} ${kind} ${b}`;
}

function value(state, key) {
  let v = state[key] ?? "";
  if (Array.isArray(v)) v = v.length === 1 ? v[0] : "";
  return v === null ? "" : String(v);
}

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
export const wordRe = (w) => new RegExp(`(?<![\\p{L}\\p{N}_])${escapeRe(w)}(?![\\p{L}\\p{N}_])`, "giu");

/** [true | false | null, darkKeys]. null = unknown because a key it needs is Dark. */
export function evaluate(test, state) {
  const node = typeof test === "string" ? parseTql(test) : test;
  const dark = [];
  const ev = (n) => {
    const kind = n[0];
    if (kind === "known") return value(state, n[1]) !== "";
    if (kind === "dark") return value(state, n[1]) === "";
    if (kind === "has") {
      const v = value(state, n[1]);
      if (v === "") { dark.push(n[1]); return null; }
      return wordRe(n[2]).test(v);
    }
    if (kind === "cmp") {
      const v = value(state, n[1]);
      if (v === "") { dark.push(n[1]); return null; }
      const [a, b] = NUM.test(v) && NUM.test(n[3]) ? [Number(v), Number(n[3])] : [v, n[3]];
      return { "=": a === b, "!=": a !== b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b }[n[2]];
    }
    if (kind === "not") { const r = ev(n[1]); return r === null ? null : !r; }
    const l = ev(n[1]), r = ev(n[2]);
    if (kind === "and") return l === false || r === false ? false : l === null || r === null ? null : true;
    return l === true || r === true ? true : l === null || r === null ? null : false;
  };
  const result = ev(node);
  return [result, result === null ? [...new Set(dark)] : []];
}
