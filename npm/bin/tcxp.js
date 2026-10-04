#!/usr/bin/env node
// `tcxp` from npm. JavaScript-native commands run here; everything else is forwarded to the
// Python library, which is installed once from the wheel bundled in this package.
import { spawnSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";
import { Address, URI, VERSION } from "../index.js";
import { HOME, PKG, VENV, isReady, setup, venvBin } from "../lib/python.js";

const argv = process.argv.slice(2);
const cmd = argv[0];
const flag = (name, fallback) => { const i = argv.indexOf(name); return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback; };

function serve(defaultPort, open) {
  return import("../lib/server.js").then(({ createTcxpServer }) => {
    const port = Number(flag("--port", process.env.PORT || defaultPort));
    const server = createTcxpServer().listen(port, "127.0.0.1", () => {
      const url = `http://127.0.0.1:${server.address().port}/${argv.includes("--flow") ? "flow/" : ""}`;
      console.log(`tcxp ${open ? "docs" : "server"} at ${url}  (Ctrl+C to stop)`);
      if (!open) console.log(`  API: ${url}api   e.g. ${url}api/fleet?observatrons=1000&epochs=6`);
      if (open && !argv.includes("--no-open")) {
        const opener = process.platform === "darwin" ? "open" : process.platform === "win32" ? "explorer" : "xdg-open";
        spawnSync(opener, [url], { stdio: "ignore" });
      }
    });
  });
}

const HELP = `tcxp ${VERSION} (npm)

JavaScript commands
  tcxp docs [--port N] [--no-open]   open the animated docs (served locally); --flow opens the decision-flow page
  tcxp serve [--port N]              local server: docs at /, the CLI as JSON at /api/<command>
  tcxp parse <address>               canonical form of an address (JavaScript parser)
  tcxp setup [--force]               install the bundled Python library into ${VENV}
  tcxp where                         show where the Python library lives
  tcxp uninstall                     remove ${HOME}

Everything else runs the Python library (installed on first use; needs Python 3.10+):
`;

try {
  if (cmd === "docs" && !argv.includes("--path")) await serve(0, true);
  else if (cmd === "serve") await serve(8765, false);
  else if (cmd === "parse") console.log(Address.parse(argv[1] ?? "").toString());
  else if (cmd === "uri" || (cmd === "version" && argv.includes("--js"))) console.log(URI);
  else if (cmd === "setup") { const bin = setup({ force: argv.includes("--force") }); console.log(`tcxp: ready (${bin})`); }
  else if (cmd === "where") console.log(JSON.stringify({ home: HOME, venv: VENV, ready: isReady(), package: PKG, tcxp: venvBin("tcxp") }, null, 2));
  else if (cmd === "uninstall") { if (existsSync(HOME)) rmSync(HOME, { recursive: true, force: true }); console.log(`tcxp: removed ${HOME}`); }
  else {
    if (!cmd || cmd === "-h" || cmd === "--help" || cmd === "help") process.stdout.write(HELP);
    const r = spawnSync(setup(), cmd === "help" ? ["--help"] : argv, { stdio: "inherit" });
    process.exitCode = r.status ?? 1;
  }
} catch (e) {
  console.error(`tcxp: ${e.message || e}`);
  process.exitCode = 2;
}
