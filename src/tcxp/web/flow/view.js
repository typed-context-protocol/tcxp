// Renders a Flow as a process map: [query] → ◆ gate → ◆ gate → [SQL card].
// Cards (the manager's words) sit above each diamond; the false outcome hangs below it.
import { describe } from "./flow.js";

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export function marked(text, highlights) {
  const hs = [...highlights].sort((a, b) => a.start - b.start || b.end - a.end);
  let out = "", at = 0;
  for (const h of hs) {
    if (h.start < at) continue;
    out += esc(text.slice(at, h.start)) + `<mark class="hl hl-${esc(h.color)}" title="${esc(h.sensor)}">${esc(text.slice(h.start, h.end))}</mark>`;
    at = h.end;
  }
  return out + esc(text.slice(at));
}

function sqlHtml(card) {
  return esc(card.sql).replace(/:([A-Za-z_]\w*)/g, (_, s) =>
    s in card.filled ? `<span class="slot lit" title=":${s}">'${esc(card.filled[s])}'</span>` : `<span class="slot dark" title="missing">:${s}</span>`);
}

const arrow = (dir, cls, label = "", sub = "") =>
  `<div class="arrow ${dir} ${cls}"><span class="line"></span>${label ? `<span class="lbl">${esc(label)}</span>` : ""}${sub ? `<span class="sub">${esc(sub)}</span>` : ""}</div>`;

export function renderCanvas(flow, r) {
  const steps = new Map((r?.steps || []).map((s) => [s.gate, s]));
  const stopIndex = r?.stoppedAt ? flow.gates.findIndex((g) => g.id === r.stoppedAt) : -1;
  const cols = [];
  cols.push(`<div class="col"><div class="slot-top"></div>
    <div class="node query"><div class="tag">query</div><div class="qtext">${r?.query ? marked(r.query, r.highlights) : '<span class="muted">Type a question above</span>'}</div></div>
    <div class="slot-bottom"></div></div>`);
  flow.gates.forEach((g, i) => {
    const s = steps.get(g.id);
    const reached = !!s;
    const after = stopIndex >= 0 && i > stopIndex;
    cols.push(arrow("right", reached ? "on" : "off", i === 0 ? "" : "true", i === 0 ? "" : (flow.gates[i - 1].ifTrue.map(describe).join(", "))));
    const state = !s ? "idle" : s.result === null ? "unknown" : s.branch;
    const falseActs = g.ifFalse.map(describe);
    cols.push(`<div class="col gate ${after ? "dim" : ""}" data-gate="${esc(g.id)}">
      <div class="slot-top">
        <div class="card ${g.approved ? "approved" : "proposed"}">
          <div class="card-text">${esc(g.card || g.test)}</div>
          <div class="card-meta">
            <span>${g.approved ? `approved by ${esc(g.approvedBy)}` : "proposed · shown, not acted on"}</span>
            <span class="card-btns">
              ${g.approved ? "" : `<button class="btn tiny" data-approve="${esc(g.id)}">Approve</button>`}
              <button class="btn tiny ghost" data-copy="${esc(g.address().toString())}" title="Copy this gate's address">URI</button>
              <button class="btn tiny ghost" data-remove="${esc(g.id)}" title="Remove">×</button>
            </span>
          </div>
        </div>
        ${arrow("down", "card-in")}
      </div>
      <div class="diamond-wrap ${state} ${g.approved ? "" : "is-proposed"}">
        <svg viewBox="0 0 200 128" aria-hidden="true"><polygon points="100,3 197,64 100,125 3,64"/></svg>
        <div class="dtext"><code>${esc(g.test)}</code>?</div>
      </div>
      <div class="slot-bottom">
        ${arrow("down", s && s.branch === "false" ? "on false" : "off", "false", s && s.result === null ? `unknown: ${s.dark.join(", ")} is Dark` : "")}
        <div class="outcome ${s && s.branch === "false" ? "taken" : ""} ${r?.stoppedAt === g.id ? "stopped" : ""}">
          ${falseActs.length ? falseActs.map((a) => `<div>${esc(a)}</div>`).join("") : '<div class="muted">continue</div>'}
          ${r?.stoppedAt === g.id ? '<div class="stop">■ stops here</div>' : ""}
        </div>
      </div>
    </div>`);
  });
  const lastTrue = flow.gates.length ? flow.gates[flow.gates.length - 1].ifTrue.map(describe).join(", ") : "";
  const passed = r && !r.stoppedAt;
  cols.push(arrow("right", passed ? "on" : "off", flow.gates.length ? "true" : "", lastTrue));
  const c = r?.card;
  cols.push(`<div class="col ${stopIndex >= 0 ? "dim" : ""}"><div class="slot-top"></div>
    <div class="node sqlcard">
      <div class="tag">SQL card · ${esc(flow.card.title)}</div>
      <pre class="sql">${c ? sqlHtml(c) : esc(flow.card.template)}</pre>
      <div class="sqlfoot">${!c ? "" : c.result ? `<b>${esc(c.result.columns[0])} = ${Number(c.result.rows[0][0]).toLocaleString("en-US")}</b>`
        : c.missing.length ? `missing ${c.missing.map((m) => `<span class="slot dark">:${esc(m)}</span>`).join(" ")}` : c.error ? esc(c.error) : "waiting for the gates"}</div>
    </div><div class="slot-bottom"></div></div>`);
  return cols.join("");
}
