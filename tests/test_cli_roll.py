import json

from tcxp import __uri__, __version__
from tcxp.__main__ import main
from tcxp.address import Address
from tcxp.roll import Roll, Step


def _steps():
    a = Address.build("reason/x", {"tax_year": "", "task": ""})
    seq = [a, a.with_(task="s41"), a.with_(task="s41", tax_year=2024), a.with_(task="s41", tax_year=2024, m="!tcxp:/geo/US")]
    return [Step(i, f"t{i}", f"change {i}", s) for i, s in enumerate(seq)]


def test_roll_render_marks_now_and_changes():
    r = Roll(_steps(), past=2, future=1)
    frame = r.render(2, color=False)
    assert "▼ NOW" in frame and "tax_year" in frame and "2024" in frame
    assert "↗US" in r.render(3, color=False)                      # pointers show their last segment
    assert r._changed(2, "tax_year") and not r._changed(2, "task")
    d = r.to_dict()
    assert len(d["steps"]) == 4 and d["keys"] == ["m", "task", "tax_year"]


def test_roll_play_writes_frames():
    out = []
    end = Roll(_steps()).play(0, None, 0, out=out.append, color=False)
    assert end == 4 and len(out) == 4 and all("tcxp context roll" in f for f in out)


def test_cli_version_and_convert(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __uri__ and __version__ in __uri__
    assert main(["convert", "!tcxp:/r?a=1", "-o", "java"]) == 0
    assert "Map.ofEntries" in capsys.readouterr().out


def test_cli_sim_record_and_sequencer(tmp_path, capsys):
    s = str(tmp_path / "s.json")
    assert main(["sim", "--tasks", "2", "--cycles", "1", "--decisions-per-task", "1", "--record", "--session", s]) == 0
    assert main(["sequencer", "play", "--steps", "2", "--speed", "0", "--session", s]) == 0
    assert "▼ NOW" in capsys.readouterr().out
    assert main(["sequencer", "rewind", "--session", s]) == 0
    assert main(["status", "--session", s]) == 0 and "trace: intact" in capsys.readouterr().out
    assert main(["roll", "--export", str(tmp_path / "f.json"), "--session", s]) == 0
    assert json.loads((tmp_path / "f.json").read_text())["steps"]
    assert main(["sequencer", "reset", "--session", s]) == 0
    assert main(["play", "--session", s]) == 2                      # no session: clear error, exit code 2


def test_cli_bench_budget_sql(capsys, tmp_path):
    assert main(["bench"]) == 0 and "ladder" in capsys.readouterr().out
    assert main(["budget", "--steps", "6", "--cost", "50000", "--tolerated", "100", "--volume", "40", "--answered", "90"]) == 0
    assert '"verified_cases_per_step": 8979' in capsys.readouterr().out
    csv = tmp_path / "t.csv"
    csv.write_text("a,b\n1,x\n2,y\n")
    assert main(["sql", "SELECT SUM(a) FROM t", "--csv", f"t={csv}"]) == 0
    assert "3" in capsys.readouterr().out
