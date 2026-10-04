// Runs the shared TQL and reasoning-card vectors against npm/flow (same file the Python tests use).
import { readFileSync } from "node:fs";
import { evaluate, formatTql, parseTql, TQLError } from "./flow/tql.js";
import { compileCard } from "./flow/card.js";
import { Gate } from "./flow/gate.js";

const V = JSON.parse(readFileSync(new URL("./tql_vectors.json", import.meta.url), "utf8"));
let pass = 0, fail = 0;
const check = (ok, what) => { ok ? pass++ : (fail++, console.error("FAIL", what)); };
for (const v of V.valid) {
  check(formatTql(parseTql(v.test)) === v.canonical, `canonical ${v.test} → ${formatTql(parseTql(v.test))}`);
  const [r, dark] = evaluate(v.test, V.states[v.state]);
  check(r === v.result && JSON.stringify(dark) === JSON.stringify(v.dark), `eval ${v.test} @${v.state}: ${r} ${dark}`);
}
for (const t of V.invalid) {
  let threw = false;
  try { parseTql(t); } catch (e) { threw = e instanceof TQLError; }
  check(threw, `should reject ${JSON.stringify(t)}`);
}
for (const c of V.cards) {
  const got = compileCard(c.card).gate.address().toString();
  check(got === c.address, `card ${c.card}\n  got  ${got}\n  want ${c.address}`);
}
const base = Gate.fromAddress(V.base_gate);
check(base.address().toString() === V.base_gate, "gate round trip");
for (const c of V.attach) {
  const r = compileCard(c.card, [base]);
  check(r.gate.address().toString() === c.address && r.isNew === c.new, `attach ${c.card}\n  got  ${r.gate.address()}\n  want ${c.address}`);
}
console.log(`${pass}/${pass + fail} flow vectors passed`);
if (fail) process.exit(1);
