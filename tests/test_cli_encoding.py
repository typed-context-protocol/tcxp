"""The CLI must not crash when stdout can't encode its non-ASCII text.

Windows writes piped output in the locale code page (cp1252), which has no `→`.
PYTHONIOENCODING=cp1252 reproduces that on every OS.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.mark.parametrize("command", ["demo", "flow"])
def test_help_survives_cp1252_stdout(command):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SRC), env.get("PYTHONPATH")]))
    r = subprocess.run([sys.executable, "-m", "tcxp", command, "--help"], env=env, capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert r.stdout
