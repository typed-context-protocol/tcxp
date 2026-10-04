// Runs the shared conformance vectors against the JavaScript implementation.
import { readFileSync } from "node:fs";
import { Address, AddressError } from "./index.js";

const vectors = JSON.parse(readFileSync(new URL("./vectors.json", import.meta.url), "utf8"));
let failed = 0;

for (const v of vectors.valid) {
  try {
    const a = Address.parse(v.input);
    const params = a.params.map(([k, vals]) => [k, [...vals]]);
    const ok = a.toString() === v.canonical && a.toURI() === v.uri && a.form === v.form &&
      a.authority === v.authority && a.path.join("/") === v.path && JSON.stringify(params) === JSON.stringify(v.params) &&
      Address.parse(a.toString()).toString() === v.canonical;
    if (!ok) { failed++; console.log("FAIL", v.input, "→", a.toString(), "expected", v.canonical); }
  } catch (e) { failed++; console.log("FAIL (threw)", v.input, e.message); }
}
for (const v of vectors.invalid) {
  try { Address.parse(v.input); failed++; console.log("FAIL (accepted)", v.input, "—", v.note); }
  catch (e) { if (!(e instanceof AddressError)) { failed++; console.log("FAIL (wrong error)", v.input, e); } }
}
const total = vectors.valid.length + vectors.invalid.length;
console.log(`${total - failed}/${total} conformance vectors passed`);
process.exit(failed ? 1 : 0);
