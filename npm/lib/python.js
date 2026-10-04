// Finds Python 3.10+, keeps a private virtual environment at ~/.tcxp/venv (or $TCXP_HOME/venv)
// and installs the tcxp wheel bundled in this package into it. No network is needed:
// the wheel ships inside the npm package and tcxp has no Python dependencies.
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { VERSION } from "../index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
export const PKG = join(HERE, "..");
export const HOME = process.env.TCXP_HOME || join(homedir(), ".tcxp");
export const VENV = join(HOME, "venv");
const WIN = process.platform === "win32";
// Python on Windows writes piped output in the locale code page; make every child use UTF-8.
const pyEnv = (env = process.env) => ({ ...env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" });
export const venvBin = (name) => join(VENV, WIN ? "Scripts" : "bin", WIN ? `${name}.exe` : name);

export function bundledWheel() {
  const dir = join(PKG, "python");
  const whl = existsSync(dir) && readdirSync(dir).find((f) => f.startsWith(`tcxp-${VERSION}-`) && f.endsWith(".whl"));
  if (!whl) throw new Error(`The Python wheel for tcxp ${VERSION} is missing from this package (expected python/tcxp-${VERSION}-*.whl).`);
  return join(dir, whl);
}

export function findPython() {
  const candidates = process.env.TCXP_PYTHON ? [process.env.TCXP_PYTHON]
    : WIN ? ["py", "python", "python3"] : ["python3", "python", "python3.13", "python3.12", "python3.11", "python3.10"];
  for (const cmd of candidates) {
    const args = cmd === "py" ? ["-3", "-c"] : ["-c"];
    const r = spawnSync(cmd, [...args, "import sys; print('%d.%d' % sys.version_info[:2])"], { encoding: "utf8", env: pyEnv() });
    if (r.status !== 0) continue;
    const [maj, min] = r.stdout.trim().split(".").map(Number);
    if (maj === 3 && min >= 10) return cmd === "py" ? ["py", "-3"] : [cmd];
  }
  return null;
}

const stamp = () => join(HOME, "installed.json");

export function isReady() {
  if (!existsSync(venvBin("tcxp"))) return false;
  try { return JSON.parse(readFileSync(stamp(), "utf8")).version === VERSION; } catch { return false; }
}

export function setup({ quiet = false, force = false } = {}) {
  if (!force && isReady()) return venvBin("tcxp");
  const py = findPython();
  if (!py) throw new Error("tcxp needs Python 3.10 or newer. Install it from https://www.python.org/downloads/ (or set TCXP_PYTHON) and run again.");
  const log = (m) => quiet || process.stderr.write(m + "\n");
  mkdirSync(HOME, { recursive: true });
  if (force || !existsSync(venvBin("python"))) {
    log(`tcxp: creating a Python environment in ${VENV}`);
    const r = spawnSync(py[0], [...py.slice(1), "-m", "venv", "--clear", VENV], { stdio: quiet ? "ignore" : "inherit", env: pyEnv() });
    if (r.status !== 0) throw new Error(`Could not create a virtual environment with ${py.join(" ")} -m venv. On Debian/Ubuntu, install python3-venv.`);
  }
  log(`tcxp: installing the bundled Python library (tcxp ${VERSION})`);
  const r = spawnSync(venvBin("python"), ["-m", "pip", "install", "--quiet", "--disable-pip-version-check",
    "--no-index", "--force-reinstall", bundledWheel()], { stdio: quiet ? "ignore" : "inherit", env: pyEnv() });
  if (r.status !== 0) throw new Error("pip could not install the bundled tcxp wheel.");
  writeFileSync(stamp(), JSON.stringify({ version: VERSION, python: py.join(" "), at: new Date().toISOString() }) + "\n");
  return venvBin("tcxp");
}

export function runPython(args, opts = {}) {
  return spawnSync(setup({ quiet: opts.quiet }), args, { encoding: "utf8", ...opts, env: pyEnv(opts.env) });
}
