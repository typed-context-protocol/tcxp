// tcxp-sql/0.1, small: SELECT columns or SUM/COUNT/MIN/MAX FROM table [WHERE c op v [AND …]].
// Every value is a string; comparisons are numeric only when both sides are plain numbers.
export const DIALECT = "tcxp-sql/0.1";
const NUM = /^-?\d+(?:\.\d+)?$/;

export function parseCsv(text) {
  const [head, ...lines] = text.trim().split(/\r?\n/);
  const cols = head.split(",").map((c) => c.trim());
  return { columns: cols, rows: lines.filter(Boolean).map((l) => Object.fromEntries(l.split(",").map((v, i) => [cols[i], v.trim()]))) };
}

const cmp = (a, op, b) => {
  const [x, y] = NUM.test(a) && NUM.test(b) ? [Number(a), Number(b)] : [a, b];
  return { "=": x === y, "!=": x !== y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y }[op];
};
const fmt = (n) => (Number.isInteger(n) ? String(n) : String(Math.round(n * 1e6) / 1e6));

export function query(tables, sql, params = {}) {
  const toks = sql.trim().replace(/;$/, "").match(/'(?:[^']|'')*'|-?\d+(?:\.\d+)?|:[A-Za-z_]\w*|<=|>=|!=|[=<>,()*]|[A-Za-z_]\w*/g) || [];
  let i = 0;
  const peek = () => toks[i] ?? "";
  const take = (w) => {
    const t = toks[i++];
    if (t === undefined || (w && t.toUpperCase() !== w)) throw new Error(`${DIALECT}: expected ${w || "more"}, found ${t ?? "end"}`);
    return t;
  };
  const literal = () => {
    const t = take();
    if (t.startsWith("'")) return t.slice(1, -1).replace(/''/g, "'");
    if (t.startsWith(":")) {
      const v = params[t.slice(1)];
      if (v === undefined || v === "") throw new Error(`Slot ${t} is empty`);
      return String(v);
    }
    if (NUM.test(t)) return t;
    throw new Error(`${DIALECT}: expected a value, found ${t}`);
  };
  take("SELECT");
  const items = [];
  do {
    if (peek() === ",") take();
    const t = take();
    if (/^(SUM|COUNT|MIN|MAX)$/i.test(t) && peek() === "(") { take("("); const c = take(); take(")"); items.push([t.toUpperCase(), c]); }
    else items.push(["col", t]);
  } while (peek() === ",");
  take("FROM");
  const table = tables[take()];
  if (!table) throw new Error("No such table");
  const conds = [];
  if (peek().toUpperCase() === "WHERE") {
    take();
    do {
      if (peek().toUpperCase() === "AND") take();
      const col = take();
      if (peek().toUpperCase() === "BETWEEN") { take(); const lo = literal(); take("AND"); const hi = literal();
        conds.push((r) => cmp(r[col], ">=", lo) && cmp(r[col], "<=", hi)); }
      else { const op = take(); const v = literal(); conds.push((r) => cmp(r[col], op, v)); }
    } while (peek().toUpperCase() === "AND");
  }
  const rows = table.rows.filter((r) => conds.every((c) => c(r)));
  if (items.some(([k]) => k !== "col")) {
    return { columns: items.map(([k, c]) => `${k}(${c})`), rows: [items.map(([k, c]) => {
      const vals = rows.map((r) => (c === "*" ? "" : r[c]));
      const nums = vals.filter((v) => NUM.test(v)).map(Number);
      if (k === "COUNT") return String(c === "*" ? rows.length : vals.filter((v) => v !== "").length);
      if (k === "SUM") return fmt(nums.reduce((a, b) => a + b, 0));
      return nums.length ? fmt(k === "MIN" ? Math.min(...nums) : Math.max(...nums)) : "";
    })] };
  }
  const cols = items[0][1] === "*" ? table.columns : items.map(([, c]) => c);
  return { columns: cols, rows: rows.map((r) => cols.map((c) => r[c])) };
}

/** A SQL template whose :slots fill from state; derive() adds computed slots (tax_year → dates). */
export class QueryCard {
  constructor(id, title, template, derive = null) { Object.assign(this, { id, title, template, derive }); }
  get slots() { return [...new Set([...this.template.matchAll(/:([A-Za-z_]\w*)/g)].map((m) => m[1]))]; }
  fill(state) {
    const v = Object.fromEntries(Object.entries(state).filter(([, x]) => x !== "" && x != null && !Array.isArray(x)).map(([k, x]) => [k, String(x)]));
    if (this.derive) Object.assign(v, Object.fromEntries(Object.entries(this.derive(v)).filter(([, x]) => x)));
    return Object.fromEntries(this.slots.filter((s) => s in v).map((s) => [s, v[s]]));
  }
  missing(state) { const f = this.fill(state); return this.slots.filter((s) => !(s in f)); }
  run(tables, state) { return query(tables, this.template, this.fill(state)); }
}

export const taxYearBounds = (s) => (/^\d{4}$/.test(s.tax_year || "") ? { start_date: `${s.tax_year}-01-01`, end_date: `${s.tax_year}-12-31` } : {});
