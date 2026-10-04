// A small local server: the animated docs at / and the Python CLI behind /api/<command>.
// Bound to 127.0.0.1. Only allow-listed commands and flags run; no shell is involved;
// nothing that spends money (--real) or touches files (--session, --csv) is reachable.
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { PKG, setup } from "./python.js";
import { Address, URI, VERSION } from "../index.js";

const COMMANDS = {
  version: { json: true, flags: [] },
  fleet: { json: true, flags: ["observatrons", "requests-per", "epochs", "drift-epoch", "seed", "no-share", "address"] },
  sim: { json: false, flags: ["employees", "agents", "tasks", "decisions-per-task", "steps-min", "steps-max", "cycles",
                              "ambiguity", "gate", "no-gate", "share-resolutions", "no-share-resolutions", "cost-error",
                              "ask-cost", "seed", "compare", "address"] },
  bench: { json: false, flags: ["seed", "details"] },
  budget: { json: false, flags: ["steps", "cost", "tolerated", "volume", "answered", "floor", "confidence", "failures"] },
  convert: { json: false, flags: ["output"], positional: "address" },
  learn: { json: false, flags: [] },
};
const SWITCHES = new Set(["no-share", "gate", "no-gate", "share-resolutions", "no-share-resolutions", "compare", "details"]);
const VALUE_RE = /^[A-Za-z0-9!:/?=&%@._~+\-]{0,4000}$/;

function argsFor(cmd, query) {
  const spec = COMMANDS[cmd];
  const args = [cmd];
  if (spec.positional) {
    const v = query.get(spec.positional) ?? "";
    if (!VALUE_RE.test(v) || v.startsWith("-")) throw new Error(`bad ${spec.positional}`);
    args.push(v);
  }
  for (const [k, v] of query) {
    if (k === spec.positional) continue;
    if (!spec.flags.includes(k)) throw new Error(`flag --${k} is not allowed for ${cmd}`);
    if (SWITCHES.has(k)) { if (v !== "false") args.push(`--${k}`); continue; }
    if (!VALUE_RE.test(v) || v.startsWith("-") && !/^-\d/.test(v)) throw new Error(`bad value for --${k}`);
    args.push(`--${k}`, v);
  }
  if (spec.json) args.push("-o", "json");
  return args;
}

function run(args) {
  return new Promise((resolve) => {
    const child = spawn(setup({ quiet: true }), args, { env: { ...process.env, NO_COLOR: "1", TCXP_COLOR: "0" } });
    let out = "", err = "";
    const timer = setTimeout(() => child.kill(), 120_000);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("close", (code) => { clearTimeout(timer); resolve({ code, out, err }); });
  });
}

export function createTcxpServer() {
  const docs = join(PKG, "docs", "index.html");
  return createServer(async (req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    const send = (status, body, type = "application/json; charset=utf-8") => {
      res.writeHead(status, { "content-type": type, "cache-control": "no-store", "x-content-type-options": "nosniff" });
      res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body, null, 2));
    };
    try {
      if (req.method !== "GET") return send(405, { error: "GET only" });
      if (url.pathname === "/" || url.pathname === "/index.html") {
        return existsSync(docs) ? send(200, readFileSync(docs), "text/html; charset=utf-8") : send(404, { error: "docs not bundled" });
      }
      const statics = { "/flow": "flow/index.html", "/flow/": "flow/index.html", "/index.js": "index.js",
        ...Object.fromEntries(["tql", "gate", "card", "sql", "flow", "view", "index"].map((m) =>
          [`/flow/${m}.${m === "index" ? "html" : "js"}`, `flow/${m}.${m === "index" ? "html" : "js"}`])) };
      if (statics[url.pathname]) {
        const file = join(PKG, statics[url.pathname]);
        if (!existsSync(file)) return send(404, { error: "not bundled" });
        return send(200, readFileSync(file), file.endsWith(".html") ? "text/html; charset=utf-8" : "text/javascript; charset=utf-8");
      }
      if (url.pathname === "/api") return send(200, { uri: URI, version: VERSION, commands: Object.fromEntries(
        Object.entries(COMMANDS).map(([k, v]) => [k, v.flags])) });
      if (url.pathname === "/api/parse") return send(200, { address: Address.parse(url.searchParams.get("a") ?? "").toString() });
      const m = url.pathname.match(/^\/api\/([a-z]+)$/);
      if (!m || !COMMANDS[m[1]]) return send(404, { error: "unknown endpoint", see: "/api" });
      const args = argsFor(m[1], url.searchParams);
      const t0 = Date.now();
      const r = await run(args);
      if (r.code !== 0) return send(400, { command: "tcxp " + args.join(" "), error: r.err.trim() || `exit ${r.code}` });
      const body = { command: "tcxp " + args.join(" "), ms: Date.now() - t0 };
      if (COMMANDS[m[1]].json) { try { body.result = JSON.parse(r.out); } catch { body.result = r.out.trim(); } }
      else body.text = r.out;
      return send(200, body);
    } catch (e) {
      return send(400, { error: String(e.message || e) });
    }
  });
}
