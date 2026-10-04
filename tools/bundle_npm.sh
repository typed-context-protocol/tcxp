#!/bin/sh
# Build the Python wheel and the docs, and copy them into npm/ so `npm pack` ships them.
# Run from anywhere:  sh tools/bundle_npm.sh
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
python3 tools/build_flow.py
python3 tools/build_docs.py
rm -rf dist npm/python npm/docs
python3 -m build --wheel --sdist --outdir dist . >/dev/null
mkdir -p npm/python npm/docs
cp dist/tcxp-*.whl npm/python/
cp docs/index.html npm/docs/index.html
cp conformance/vectors.json npm/vectors.json
cp conformance/tql_vectors.json npm/tql_vectors.json
cp LICENSE LICENSE-W3C NOTICE npm/
PY=$(python3 -c "import re;print(re.search(r'__version__ = \"(.+?)\"', open('src/tcxp/__init__.py').read()).group(1))")
JS=$(node -p "require('./npm/package.json').version")
[ "$PY" = "$JS" ] || { echo "Version mismatch: Python $PY, npm $JS" >&2; exit 1; }
echo "Bundled tcxp $PY: $(ls npm/python) + docs into npm/"
