from tcxp.__main__ import main
from tcxp.fleet import ARMS, Fleet, FleetConfig, generate_requests
from tcxp.ladder import NOT_STATED


def test_requests_have_ground_truth_and_drift():
    rs = generate_requests(200, 2, 4, 0.5, 0.25, 0.3, seed=1, drift_epoch=2)
    assert len(rs) == 400 and {r.epoch for r in rs} == {0, 1, 2, 3}
    assert not any(r.kind.endswith("+new") for r in rs if r.epoch < 2)
    assert any(r.kind.endswith("+new") for r in rs if r.epoch >= 2)
    assert all((r.truth == NOT_STATED) == (r.kind.split("+")[0] in ("trap", "not_stated")) for r in rs)


def test_fleet_runs_all_arms_on_the_same_requests():
    res = Fleet(FleetConfig(observatrons=400, epochs=4, drift_epoch=2, seed=2)).run()
    n = {a: res.totals(a)["decisions"] for a in ARMS}
    assert len(set(n.values())) == 1 and n["context"] == 1200
    for a in ARMS:
        t = res.totals(a)
        assert sum(t["decided_by"].values()) == t["decisions"]
        assert 0 <= t["accuracy"] <= 1
    assert res.totals("context")["silent_errors"] < res.totals("llm_alone")["silent_errors"]
    assert res.totals("context_learning")["model_cost"] < res.totals("context")["model_cost"]
    assert res.delta()["silent_errors"] < 0


def test_fleet_is_reproducible_and_addressable():
    c = FleetConfig(observatrons=50, epochs=2, seed=9)
    assert FleetConfig.from_address(c.to_address()) == c
    assert Fleet(c).run().totals("context_learning") == Fleet(c.to_address()).run().totals("context_learning")


def test_unshared_guards_learn_nothing_from_three_requests_each():
    t = Fleet(FleetConfig(observatrons=300, requests_per=3, epochs=3, share=False)).run().totals("context_learning")
    assert t["guard_acted"] == 0


def test_fleet_cli(capsys):
    assert main(["fleet", "--observatrons", "200", "--epochs", "3", "--drift-epoch", "1"]) == 0
    out = capsys.readouterr().out
    assert "context_learning" in out and "guard confidence" in out
    assert main(["fleet", "--observatrons", "50", "--epochs", "2", "-o", "json"]) == 0
