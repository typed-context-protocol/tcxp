// A gate is one diamond: a TQL test, what happens if true or false, and the card it came from.
// Gates are addresses: !tcxp:/gate/<id>?test=…&true.do=…&false.do=…&status=…
import { Address, parseQuery } from "../index.js";
import { formatTql, parseTql } from "./tql.js";

export const PROPOSED = "proposed";
export const APPROVED = "approved";
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function parseHandler(text) {
  if (!text.startsWith("@")) throw new Error("Handler references start with '@'");
  const q = text.indexOf("?");
  const name = q < 0 ? text.slice(1) : text.slice(1, q);
  if (!name || !/^[A-Za-z0-9._-]+$/.test(name)) throw new Error(`Invalid handler name ${JSON.stringify(name)}`);
  const params = {};
  for (const [k, v] of parseQuery(q < 0 ? "" : text.slice(q + 1))) params[k] = v.length === 1 ? v[0] : v;
  return [name, params];
}

export class Gate {
  constructor({ id, test, ifTrue = [], ifFalse = [], nextTrue = "", nextFalse = "", status = PROPOSED,
                card = "", by = "", approvedBy = "" }) {
    if (!SLUG.test(id)) throw new Error(`Gate id ${JSON.stringify(id)} must be lowercase words joined by '-'`);
    if (status !== PROPOSED && status !== APPROVED) throw new Error("A gate's status is 'proposed' or 'approved'");
    for (const a of [...ifTrue, ...ifFalse]) parseHandler(a);
    Object.assign(this, { id, test: formatTql(parseTql(test)), ifTrue: [...ifTrue], ifFalse: [...ifFalse],
                          nextTrue, nextFalse, status, card, by, approvedBy });
    Object.freeze(this);
  }

  get approved() { return this.status === APPROVED; }

  with(changes) { return new Gate({ ...this, ...changes }); }

  address() {
    return Address.parse(`!tcxp:/gate/${this.id}`).with({
      test: this.test, "true.do": this.ifTrue, "false.do": this.ifFalse,
      "true.next": this.nextTrue || null, "false.next": this.nextFalse || null, status: this.status,
      card: this.card || null, by: this.by || null, approved_by: this.approvedBy || null,
    });
  }

  static fromAddress(address) {
    const a = typeof address === "string" ? Address.parse(address) : address;
    const all = (k) => a.getAll(k).filter(Boolean);
    return new Gate({ id: a.path[a.path.length - 1], test: a.get("test", ""), ifTrue: all("true.do"),
                      ifFalse: all("false.do"), nextTrue: a.get("true.next", ""), nextFalse: a.get("false.next", ""),
                      status: a.get("status", PROPOSED), card: a.get("card", ""), by: a.get("by", ""),
                      approvedBy: a.get("approved_by", "") });
  }
}
