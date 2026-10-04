#!/bin/sh
# Install tcxp (Python library + `tcxp` command) and, if Node is present, the npm package.
#
#   sh install.sh            from a source checkout or the release zip
#
# Python: installs into ~/.tcxp/venv (or $TCXP_HOME/venv) and links ~/.local/bin/tcxp.
# Nothing is installed system-wide and no sudo is needed. Remove with: rm -rf ~/.tcxp ~/.local/bin/tcxp
set -eu
ROOT=$(cd "$(dirname "$0")" && pwd)
HOME_DIR=${TCXP_HOME:-"$HOME/.tcxp"}
BIN_DIR=${TCXP_BIN:-"$HOME/.local/bin"}

say() { printf '%s\n' "tcxp: $*"; }

PY=""
for c in ${TCXP_PYTHON:-} python3 python3.13 python3.12 python3.11 python3.10 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY=$c; break
  fi
done
[ -n "$PY" ] || { say "Python 3.10 or newer is required (https://www.python.org/downloads/)"; exit 1; }

# Prefer a wheel shipped next to this script; otherwise install from the source tree.
WHEEL=$(ls "$ROOT"/dist/tcxp-*.whl "$ROOT"/npm/python/tcxp-*.whl 2>/dev/null | head -n 1 || true)
SRC=${WHEEL:-$ROOT}

say "creating $HOME_DIR/venv with $PY"
"$PY" -m venv "$HOME_DIR/venv"
"$HOME_DIR/venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "$SRC"

mkdir -p "$BIN_DIR"
ln -sf "$HOME_DIR/venv/bin/tcxp" "$BIN_DIR/tcxp"
say "installed $("$HOME_DIR/venv/bin/tcxp" version)"
say "command: $BIN_DIR/tcxp"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "add this to your shell profile so 'tcxp' works everywhere:"
     printf '    export PATH="%s:$PATH"\n' "$BIN_DIR" ;;
esac

if command -v npm >/dev/null 2>&1 && [ -d "$ROOT/npm/python" ] && [ "${TCXP_SKIP_NPM:-0}" != "1" ]; then
  say "Node found: the npm package is in $ROOT/npm (npm install -g ./npm to use 'npx tcxp' / 'tcxp docs' from Node)"
fi
say "try: tcxp demo   then   tcxp roll   then   tcxp docs"
