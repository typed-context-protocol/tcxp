"""Build the browser flow page from npm/flow/page.html.

Writes npm/flow/index.html (a full page, modules beside it), docs/flow-artifact.html (body only,
modules under flow/), and copies the page and modules into src/tcxp/web/ so `tcxp docs --flow`
works from a pip install.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOW = ROOT / "npm" / "flow"
MODULES = ("tql.js", "gate.js", "card.js", "sql.js", "flow.js", "view.js")
HEAD = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>\n')


def main() -> None:
    page = (FLOW / "page.html").read_text(encoding="utf-8")
    (FLOW / "index.html").write_text(HEAD + page.replace("__BASE__", "./") + "\n</body></html>\n", encoding="utf-8")
    (ROOT / "docs" / "flow-artifact.html").write_text(page.replace("__BASE__", "./flow/"), encoding="utf-8")
    web = ROOT / "src" / "tcxp" / "web"
    (web / "flow").mkdir(parents=True, exist_ok=True)
    shutil.copy(FLOW / "index.html", web / "flow" / "index.html")
    for m in MODULES:
        shutil.copy(FLOW / m, web / "flow" / m)
    shutil.copy(ROOT / "npm" / "index.js", web / "index.js")
    print("Wrote npm/flow/index.html, docs/flow-artifact.html and src/tcxp/web/flow/")


if __name__ == "__main__":
    main()
