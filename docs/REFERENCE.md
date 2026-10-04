# tcxp reference

tcxp is the reference library for the Typed ConteXt Protocol (tcxp). Its core rule is that the address is the state. An Address has three written forms: the virtual pointer `!tcxp:/…` (in memory, nothing hosted), the registry address `tcxp://host/…`, and the carrier `https://host/tcxp/…` that any browser or tool accepts. A context object is plain data with five lists (`observe`, `intent`, `reason`, `decision`, `trace`) and one current Address. The registry says what *can* run (every registered handler); a context object's intent map says what *this decision meant* to run. A handler runs only when both agree. An Observatron mounts it on an input and runs it. Each sensor firing is a Spike. A Spike has an anchor facet `data` and three context facets: `meaning`, `structure` and `environment`. A context facet is Lit when it holds an address and Dark when it is empty, and two readings compare as `MATCH`, `NO MATCH` or `DARK`.

Version 0.1.0. SQL dialect `tcxp-sql/0.1`.

## Install

```bash
pip install tcxp                 # from the package index
pip install -e ".[dev]"          # from a checkout of this repo (tests: pytest)
sh install.sh                    # from a checkout or the release zip: ~/.tcxp/venv + ~/.local/bin/tcxp
npx tcxp …                       # npm: runs the Python library bundled in the package
```

`npx tcxp` installs the bundled wheel into `~/.tcxp/venv` on first use (Python 3.10+, no network). JavaScript-only commands: `tcxp docs`, `tcxp serve` (docs at `/`, CLI as JSON at `/api/<command>`), `tcxp parse`, `tcxp setup`, `tcxp where`, `tcxp uninstall`. Build the npm bundle with `sh tools/bundle_npm.sh`.

## Module map

| File | Purpose |
|---|---|
| `src/tcxp/__init__.py` | Public API re-exports, `__version__`, `__uri__` |
| `src/tcxp/__main__.py` | The `tcxp` command line |
| `src/tcxp/address.py` | Immutable, canonical `Address` and percent-encoding |
| `src/tcxp/bus.py` | `EventBus` publish/subscribe |
| `src/tcxp/context.py` | `ContextObject`, `Sensor`, `Observatron`, `Observation` |
| `src/tcxp/convert.py` | Address to and from JSON, dict, CSV, SQL, Python, JS, C++, Java |
| `src/tcxp/facets.py` | `Spike`, Lit/Dark facets, `MATCH`/`NO MATCH`/`DARK`, `Equivalences` |
| `src/tcxp/governor.py` | `Rule`, `Verdict`, `Governor` (ACT / ASK / HALT) |
| `src/tcxp/ladder.py` | Check ladder: `Question`, `Answer`, `CodeChecker`, `SimulatedChecker`, `Ladder` |
| `src/tcxp/models.py` | Real API checkers: `JevChecker`, `ClaudeChecker` |
| `src/tcxp/registry.py` | Data, handlers and content-addressed state behind addresses |
| `src/tcxp/schema.py` | `Schema` and `Field`: types and answer spaces |
| `src/tcxp/sql.py` | `tcxp-sql/0.1` engine over CSV, `QueryCard` |
| `src/tcxp/trace.py` | Hash-chained, append-only `Trace` |
| `src/tcxp/session.py` | Session files and playback (`Session`) |
| `src/tcxp/pretty.py` | Terminal tables, colors, Lit/Dark display |
| `src/tcxp/roll.py` | Context roll (piano-roll view of a trace) |
| `src/tcxp/bench.py` | Tax-year benchmark across checker arms |
| `src/tcxp/learn.py` | `SoftmaxPerceptron` and reliability curves |
| `src/tcxp/reliability.py` | Verified-example budgets before automating |
| `src/tcxp/sim.py` | Organization simulator (Dark facets across hand-offs), teams and named stories |
| `src/tcxp/flow.py` | Decision flows: TQL, gates (diamonds), reasoning cards, approval, the run, `tcxp flow` |
| `src/tcxp/expr.py` | Expression trees as addresses: fold upward, ask about Dark leaves, solve linear equations |
| `src/tcxp/fleet.py` | Many Observatrons, with and without context objects |
| `src/tcxp/demo.py` | Section 41 terminal demo |
| `src/tcxp/data/payroll.csv` | Sample payroll table for the demo |
| `src/tcxp/web/index.html` | The animated docs, shipped in the wheel for `tcxp docs` (generated) |
| `src/tcxp/py.typed` | Marks the package as typed |
| `tools/build_docs.py` | Builds `docs/index.html`, `docs/artifact.html` and `src/tcxp/web/index.html` from real output |
| `tools/bundle_npm.sh` | Builds the wheel and docs and copies them into `npm/` |
| `install.sh` | Installs the library and the `tcxp` command for the current user |
| `pyproject.toml` | Package metadata (hatchling); console script `tcxp` |
| `npm/bin/tcxp.js` | The npm `tcxp` command: JS commands, otherwise forwards to Python |
| `npm/lib/python.js` | Finds Python, manages `~/.tcxp/venv`, installs the bundled wheel |
| `npm/lib/server.js` | Local docs + JSON API server (allow-listed commands only) |
| `npm/test-server.mjs` | Server smoke test |
| `tools/docs_template.html` | HTML template for those docs |
| `npm/index.js` | JavaScript Address implementation |
| `npm/test.js` | Runs the conformance vectors against `npm/index.js` |
| `conformance/vectors.json` | Shared valid/invalid address vectors |
| `tests/` | pytest suite |

## CLI commands

Run as `tcxp …` or `python -m tcxp …`. Every command accepts `--session FILE` (default `./tcxp-session.json`), either before the command (global) or after it (per command).

| Command | What it does | Options |
|---|---|---|
| `version` | Print the library version as an address | `--output/-o FORMAT` (default `uri`) |
| `demo` | Interactive Section 41 demo; saves a session | `--ladder` (also show the simulated code → Jev → LLM ladder) |
| `play` | Print frames from the playhead | `--steps N`, `--output/-o FORMAT`, `--speed SECONDS` (default 0) |
| `roll` | Play the session as a context roll | `--speed` (default 1), `--steps N`, `--past 3`, `--future 2`, `--export FILE.json` |
| `sequencer ACTION [N]` | Alias: `play` (= roll), `rewind`, `seek N`, `status`, `reset` | same as `roll` |
| `rewind [N]` | Playhead to the start, or back N steps | |
| `seek N` | Playhead to step N | |
| `status` | Playhead, current address, trace integrity (exit 1 if broken) | |
| `reset` | Delete the session file | |
| `sim` | Run the organization simulator | `--story NAME` (`list` shows them; flags override the story), `--teams name:size:ambiguity,...`, `--address ADDR`, `--compare`, `--record`, plus one flag per `SimConfig` field: `--employees`, `--agents`, `--tasks`, `--decisions-per-task`, `--steps-min`, `--steps-max`, `--cycles`, `--ambiguity`, `--gate/--no-gate`, `--share-resolutions/--no-share-resolutions`, `--cost-error`, `--ask-cost`, `--seed` |
| `fleet` | Many Observatrons: accuracy, cost, risk per arm | `--address`, `--observatrons`, `--requests-per`, `--epochs`, `--drift-epoch` (-1 = never), `--seed`, `--no-share`, `--real`, `--limit N`, `--output/-o table\|json` |
| `bench` | Benchmark code, Jev and LLM arms | `--real` (needs `JEV_API_KEY`, `ANTHROPIC_API_KEY`), `--details`, `--seed` |
| `sql QUERY` | Run a `tcxp-sql/0.1` query over CSV files | `--csv name=path.csv` (repeatable; without it the sample table `payroll` is loaded), `--param slot=value` (repeatable) |
| `convert ADDRESS` | Convert an address to another format | `--output/-o FORMAT` (default `json`) |
| `budget` | Verified examples needed before automating | `--cost`, `--tolerated` (required), `--steps 1`, `--volume 0`, `--answered 100`, `--floor 95`, `--confidence 0.95`, `--failures 0` |
| `learn` | Train the perceptron and print its reliability curve | adds confirmed examples from the session if it exists |
| `flow [QUERY]` | Decision flow: query box → gates from reasoning cards → SQL card. Interactive without a query | `--card SENTENCE` (repeatable), `--approve`, `--empty`, `--proposed`; inside: `:card`, `:approve`, `:gates`, `:address`, `:quit` |
| `expr EXPRESSION` | A rule as an expression tree: draw it, fold it, report Dark leaves | `--set name=value` (repeatable), `--solve`, `--output/-o table\|json` |
| `docs` | Serve the animated docs on 127.0.0.1 and open a browser | `--port N`, `--no-open`, `--path` (print the file path), `--flow` (the interactive decision-flow page) |

`FORMAT` is one of `uri, json, dict, csv, sql, python, js, cpp, java`. User errors (`OSError`, `ValueError`, `KeyError`, `LookupError`) print `tcxp: …` and exit 2, without a traceback.

Example (verified):

```bash
S=/tmp/ref-session.json
tcxp version -o json
tcxp convert '!tcxp:/reason?tax_year=2024&task=section_41_qre' -o python
printf 'What should I deduct for Section 41 US-based QREs?\n2024\n:quit\n' | tcxp demo --session $S
tcxp status --session $S
tcxp rewind --session $S && tcxp play --steps 1 --session $S
tcxp roll --steps 1 --speed 0 --session $S
tcxp sim --compare
tcxp sim --story list
tcxp sim --story launch --compare
tcxp expr '3 + 2y = 9' --solve
tcxp sim --address '!tcxp:/sim/org?tasks=2&cycles=1&gate=true'
tcxp fleet --observatrons 200 --epochs 4 --drift-epoch 2
tcxp bench
tcxp sql "SELECT COUNT(*), SUM(wages) FROM payroll WHERE country = 'US'"
tcxp docs --path
tcxp budget --steps 6 --cost 50000 --tolerated 100 --volume 40 --answered 90
tcxp learn --session $S
tcxp reset --session $S
```

---

## Package files

### `src/tcxp/__init__.py`

- **Purpose:** The public entry point. Re-exports the main classes and sets `__version__` and `__uri__` (the library's own address).
- **Consumes:** `address`, `bus`, `context`, `convert`, `facets`, `governor`, `ladder`, `registry`, `schema`, `sql`, `trace`.
- **Consumed by:** `__main__.py` (`__uri__`, `__version__`), `tools/build_docs.py`, `tests/test_core.py`, `tests/test_cli_roll.py`.
- **Key API:** `Address`, `AddressError`, `is_address_text`, `MAX_INLINE`, `EventBus`, `ContextObject`, `Observation`, `Observatron`, `Sensor`, `convert`, `Spike`, `FACETS`, `LIT`, `DARK`, `MATCH`, `NO_MATCH`, `Equivalences`, `spikes_in`, `dark_count`, `Governor`, `Rule`, `Verdict`, `ACT`, `ASK`, `HALT`, `Question`, `Answer`, `Ladder`, `CodeChecker`, `SimulatedChecker`, `NOT_STATED`, `Registry`, `IntegrityError`, `Schema`, `Field`, `Database`, `QueryCard`, `DIALECT`, `Trace`, `__version__`, `__uri__`.

```python
import tcxp

print(tcxp.__version__, tcxp.__uri__)   # 0.1.0 !tcxp:/lib/tcxp?dialect=tcxp-sql/0.1&version=0.1.0
a = tcxp.Address.parse("!tcxp:/reason?tax_year=")
print(a.with_(tax_year=2024))           # !tcxp:/reason?tax_year=2024
```

### `src/tcxp/__main__.py`

- **Purpose:** The `tcxp` command (also `python -m tcxp`). See the CLI table above.
- **Consumes:** `__init__` (`__uri__`, `__version__`), `convert`; lazily `demo`, `session`, `roll`, `sim`, `pretty`, `fleet`, `bench`, `sql`, `reliability`, `learn`.
- **Consumed by:** `tests/test_cli_roll.py`, `tests/test_fleet.py`; `tools/build_docs.py` runs it as a subprocess.
- **Key API:** `main(argv: list[str] | None = None) -> int` parses arguments and returns the exit code.

```python
from tcxp.__main__ import main

code = main(["convert", "!tcxp:/reason?tax_year=2024", "-o", "json"])   # prints JSON
print(code)                                                              # 0
```

### `src/tcxp/address.py`

- **Purpose:** The `Address` value: immutable and canonical. The same state always gives the same string (keys sorted, repeated keys keep order, one percent-encoding).
- **Consumes:** nothing from tcxp.
- **Consumed by:** `__init__`, `context`, `convert`, `demo`, `facets`, `fleet`, `governor`, `pretty`, `registry`, `roll`, `schema`, `session`, `sim`, `sql`, `trace`; `tests/test_address.py`, `tests/test_cli_roll.py`.
- **Key API:**
  - `Address.parse(text) -> Address`: reads `!tcxp:/`, `tcxp:/`, `tcxp://host/` or `https://host/tcxp/`; raises `AddressError` on anything else (spaces, `#`, bad keys).
  - `Address.build(path="", params=None, form="virtual", authority="") -> Address`.
  - `get(key, default=None)`, `get_all(key)`, `keys()`, `to_dict()`, `key in a`.
  - `with_(**values)`, `set(key, value)`, `set_many(values)`, `without(*keys)`: return a new Address. `None` removes a key, a list writes repeated keys, `""` or `[]` is Dark.
  - `at(path)`, `to_form(form, authority="")`, `to_uri()`, properties `form`, `path`, `params`, `authority`, `is_virtual`, `path_text`, `sha256`.
  - Functions `encode`, `decode`, `is_address_text`, `parse_query`, `format_query`; constants `VIRTUAL_PREFIX = "!tcxp:/"`, `MAX_INLINE = 2000`.

```python
from tcxp.address import Address

a = Address.parse("!tcxp:/reason?tax_year=&task=section_41")
b = a.with_(tax_year=2024, tags=["x", "y"])      # a new Address; a is unchanged
print(b)                         # !tcxp:/reason?tags=x&tags=y&task=section_41&tax_year=2024
print(b.get("tax_year"), b.get_all("tags"))       # 2024 ('x', 'y')
print(b.to_uri())                                 # tcxp:/reason?...
print(b.to_form("https", "example.com"))          # https://example.com/tcxp/reason?...
print(Address.parse("tcxp://registry.example/handlers/join").form)   # tcxp
```

### `src/tcxp/bus.py`

- **Purpose:** A small publish/subscribe event bus. Observatrons emit `mount`, `spike` and `decision` on it.
- **Consumes:** nothing from tcxp.
- **Consumed by:** `__init__`, `context`, `demo`; `tests/test_core.py`.
- **Key API:** `EventBus(keep_history=False)`; `on(topic, handler) -> off()`; `once(topic, handler)`; `emit(topic, payload=None)`; `clear()`; `history` (list or `None`). Handlers on `"*"` receive `{"topic", "payload"}`.

```python
from tcxp import EventBus

bus = EventBus(keep_history=True)
off = bus.on("spike", lambda p: print("spike:", p))
bus.on("*", lambda e: print("any:", e["topic"]))
bus.emit("spike", {"sensor": "tax-year"})
off()
bus.emit("spike", {"sensor": "tax-year"})
print(len(bus.history))   # 2
```

### `src/tcxp/context.py`

- **Purpose:** The context object (the plan and its state) and the Observatron (a context object mounted on an input). Flow per input: observe → intent → reason → decision → trace.
- **Consumes:** `address`, `bus`, `facets`, `governor`, `registry`, `schema`, `trace`.
- **Consumed by:** `__init__`, `demo`, `session`; `tests/test_core.py`.
- **Key API:**
  - `Sensor(id, pattern, actions=(), kind="regex", key="", meaning=(), structure=(), environment=(), color="yellow", description="")`: `kind` is `"regex"` or `"keyword"`. In actions, `{0}` is the match and `{1}`… are groups. `find(text)`, `to_dict()`, `from_dict(d)`.
  - `ContextObject(path="reason", schema=None, observe=(), reason=(), registry=None, params=None, clock=utc_now, inline_limit=MAX_INLINE, intent=())`: lists `observe`, `intent`, `reason`, `decision`, `trace`; current `address`.
  - `Intent(id, text="", means=(), allows=(), by="")`: one confirmed meaning. `means` = keys it sets; `allows` = handler names or prefixes (`sql.run`, `sql.*`), never code. `address()` → `!tcxp:/intent/<id>?allows=@sql.run&by=manager&means.task=…&text=…`; `Intent.from_address(a)`; `permits(name)`.
  - `add_intent(intent | id | intent address, means=None, allows=(), by="", text="") -> Intent`: sets the meant keys; with `by`, the trace row is learnable (`features` = their words, value = intent id), so confirmed intents are training data.
  - `allowed(handler) -> Intent | None` (`core.*` always allowed: built-ins act only on this object) and `call("@handler?args", cause="")`: the intent gate, then the registry. Refused calls raise `IntentNotAllowed` and leave a `refuse` row; unregistered ones raise `HandlerNotFound`. Sensor actions go through `call` too.
  - `set(key, value, cause, learnable=False, features="")`, `update(values, cause)`, `confirm(key, value, by="person", features=None)` (marks the row learnable), `get`, `typed()`, `spikes()`.
  - `add_rule(rule | sentence | rule address, **compile_kw) -> Rule`, `decide(action="answer") -> Verdict`.
  - `snapshot()` (inline address, or a state pointer above `inline_limit`), `resolve(snapshot)`, `to_dict()`, `save() -> Address`, `ContextObject.load(data, registry=None)`.
  - `Observatron(context, target="query", bus=None, action="answer", debounce_ms=300)`: `feed(text) -> Observation`; `keystroke(text, t_ms)` and `tick(t_ms)` simulate debounced typing.
  - `Observation(text, spikes, highlights, verdict, address, asks)`.

```python
from tcxp import ContextObject, Observatron, Rule, Sensor

ctx = ContextObject("reason/section-41", params={"tax_year": ""})
ctx.observe.append(Sensor("tax-year", r"tax year (20\d{2})", key="tax_year",
                          actions=("@core.update?tax_year={1}",)))
ctx.add_rule(Rule.compile("Don't give the answer until the tax year is confirmed",
                          slots={"tax year": "tax_year"}))
obs = Observatron(ctx)
print(obs.feed("Estimate our credit").verdict)           # ASK: tax_year before 'answer'
o = obs.feed("Estimate our credit for tax year 2024")
print(o.verdict.kind, o.address.get("tax_year"))        # ACT 2024
print(ctx.trace.verify(ctx.registry))                   # [] (intact)
```

### `src/tcxp/convert.py`

- **Purpose:** Writes an address's key-value pairs in other formats and reads some back. JSON, dict and CSV round trips return the same canonical address.
- **Consumes:** `address`.
- **Consumed by:** `__init__`, `__main__`, `demo`, `session`; `tests/test_core.py`.
- **Key API:** `convert(a, fmt="uri") -> str` for any of `FORMATS = ("uri", "json", "dict", "csv", "sql", "python", "js", "cpp", "java")`; `to_dict` / `from_dict(d, path=None)`; `to_json(a, indent=2)` / `from_json(text, path=None)`; `to_csv` / `from_csv(text, path="")`; `to_sql(a, table="tcxp_state")`; `to_python`, `to_js`, `to_cpp`, `to_java`.

```python
from tcxp import Address
from tcxp.convert import convert, from_csv, from_json, to_csv, to_json

a = Address.parse("!tcxp:/reason?tax_year=2024&task=section_41_qre")
print(convert(a, "js"))                            # const state = {...};
assert from_json(to_json(a)) == a
assert from_csv(to_csv(a), path="reason") == a
```

### `src/tcxp/facets.py`

- **Purpose:** The Spike (one observation) with its anchor `data` facet and context facets `meaning`, `structure`, `environment`. Counts Dark facets and compares readings by string equality on canonical addresses.
- **Consumes:** `address`.
- **Consumed by:** `__init__`, `context`, `pretty`; `tests/test_core.py`.
- **Key API:**
  - `Spike(key, data="", meaning=(), structure=(), environment=(), sensor="", target="", start=-1, end=-1, time="")`: `status(facet)` → `LIT`/`DARK`; `dark`, `lit`; `compare(other, facet, equivalences=None)` → `MATCH`/`NO MATCH`/`DARK`; `with_facet(facet, *addresses)`; `to_params()`; `Spike.from_address(address, key)`.
  - `Equivalences(pairs=())`: `add(a, b)`, `same(a, b)`. A recorded equivalence turns a `NO MATCH` into a `MATCH`.
  - `spikes_in(address) -> list[Spike]`, `dark_count(address) -> int`; constants `FACETS`, `MATCH`, `NO_MATCH`, `DARK`, `LIT`.
  - In an address a slot is four keys: `date`, `date.meaning`, `date.structure`, `date.environment`.

```python
from tcxp import Address, Equivalences, Spike, dark_count, spikes_in

a = Spike("date", "05/04/2026", structure=("!tcxp:/schema/date/mm-dd-yyyy",))
b = Spike("date", "05/04/2026", structure=("!tcxp:/schema/date/dd-mm-yyyy",))
print(a.dark)                                               # ('meaning', 'environment')
print(a.compare(b, "structure"), a.compare(b, "meaning"))   # NO MATCH DARK
eq = Equivalences([("!tcxp:/units/celsius", "!tcxp:/units/degC")])
c, d = Spike("t", "4", meaning=("!tcxp:/units/celsius",)), Spike("t", "4", meaning=("!tcxp:/units/degC",))
print(c.compare(d, "meaning", eq))                          # MATCH
addr = Address.build("obs").set_many(a.to_params())
print(dark_count(addr), spikes_in(addr)[0].lit)             # 2 ('structure',)
```

### `src/tcxp/governor.py`

- **Purpose:** Rules of a fixed shape ("when `<action>`, require `<keys>`, otherwise `<verdict>`") and the Governor that returns one Verdict: `ACT`, `ASK` or `HALT`. HALT is absorbing. Rules and verdicts are addresses.
- **Consumes:** `address`, `schema`.
- **Consumed by:** `__init__`, `context`, `demo`; `tests/test_core.py`.
- **Key API:**
  - `Rule(id, when, require, verdict=ASK, text="", by="")`: verdict must be `ASK` or `HALT`. `address()`, `Rule.from_address(a)`, `Rule.compile(text, rule_id="", by="", slots=None)` for "Don't `<action>` until `<fact>`" (a sentence starting with "Never" compiles to `HALT`). Raises `RuleCompileError`.
  - `Verdict(kind, action, missing=(), rules=(), message="")`: `address()` → `!tcxp:/decision?...`.
  - `Governor(rules=[], schema=None)`: `add(rule)`, `evaluate(address, action="answer") -> Verdict`. Schema essential keys count as required too.

```python
from tcxp import Address, Governor, Rule

r = Rule.compile("Don't give the answer until the tax year is confirmed",
                 by="manager", slots={"tax year": "tax_year"})
print(r.address())   # !tcxp:/rule/answer-requires-tax-year?by=manager&require=tax_year&...
g = Governor([r, Rule("pay-needs-approval", "commit", ("approval",), "HALT")])
print(g.evaluate(Address.parse("!tcxp:/reason?tax_year="), "answer"))   # ASK: tax_year before 'answer'
print(g.evaluate(Address.parse("!tcxp:/reason?tax_year=2024")).kind)    # ACT
print(g.evaluate(Address.parse("!tcxp:/reason"), "commit").address())   # !tcxp:/decision?action=commit&kind=HALT&...
```

### `src/tcxp/ladder.py`

- **Purpose:** The check ladder: code, then Jev, then an LLM, then a person. Each rung answers a typed Question. The ladder acts on the first answer at or above `threshold`; otherwise it returns ASK. `not_stated` always routes to ASK.
- **Consumes:** nothing from tcxp.
- **Consumed by:** `__init__`, `bench`, `demo`, `fleet`, `learn`, `models`; `tests/test_fleet.py`, `tests/test_tools.py`.
- **Key API:**
  - `Question(id, text, ask="", kind="choice", options=(), descriptions={}, context="", truth=None)`.
  - `Answer(value, confidence, source, ms=0.0, tokens_in=0, tokens_out=0, cost=0.0, simulated=False, error="", raw=None)`; property `tokens`.
  - `Checker` protocol: `name`, `check(q) -> Answer | None`.
  - `CodeChecker(name, fn)`: `fn(question) -> (value, confidence) | None`.
  - `SimulatedChecker(name, accuracy=0.9, guess_rate=0.7, context_effect=0.2, calibrated=True, latency_ms=400.0, tokens_overhead=120, tokens_out=12, price_in=1.0, price_out=5.0, seed=0)`: deterministic stand-in driven by declared assumptions.
  - `Ladder(checkers, threshold=0.8)`: `run(q) -> LadderResult(verdict, answer, steps, reason)` with `ms`, `tokens`, `cost`, `decided_by`.
  - `NOT_STATED = "not_stated"`.

```python
import re
from tcxp.ladder import NOT_STATED, CodeChecker, Ladder, Question, SimulatedChecker

def fy(q):
    m = re.search(r"FY(\d{4})", q.text)
    return (m.group(1), 1.0) if m else None          # None = "can't decide"

ladder = Ladder([CodeChecker("code", fy), SimulatedChecker("llm", guess_rate=0.5)], threshold=0.8)
opts = ("2024", "2025", NOT_STATED)
r1 = ladder.run(Question("q1", "Credit for FY2024", "Which tax year?", "choice", opts))
print(r1.verdict, r1.decided_by)                     # ACT code
r2 = ladder.run(Question("q2", "Credit for last year?", "Which tax year?", "choice", opts, truth=NOT_STATED))
print(r2.verdict, r2.reason)                         # ASK no rung was confident enough, so ask a person
```

### `src/tcxp/models.py`

- **Purpose:** Real API rungs for the ladder: Jev (TypeSafe) and Claude (Anthropic). Standard library only. Network or API errors come back as an `Answer` with `error` set, so the ladder moves on.
- **Consumes:** `ladder`.
- **Consumed by:** `bench` and `fleet` (only with `mode="real"`).
- **Key API:**
  - `JevChecker(api_key=None, model="jev-latest", name="jev", price_in=0.042, timeout=30.0, url="https://api.typesafe.ai/v1/systemone")`; key from `JEV_API_KEY`.
  - `ClaudeChecker(api_key=None, model="claude-haiku-4-5-20251001", name="claude", price_in=1.0, price_out=5.0, timeout=60.0, url="https://api.anthropic.com/v1/messages")`; key from `ANTHROPIC_API_KEY`.
  - Both: `check(q: Question) -> Answer`.

```python
import os
from tcxp.ladder import Ladder, Question
from tcxp.models import ClaudeChecker, JevChecker

os.environ.pop("JEV_API_KEY", None); os.environ.pop("ANTHROPIC_API_KEY", None)   # no network in this example
q = Question("q", "Calculate the R&D credit for FY24.", "Which tax year?", "choice", ("2024", "not_stated"))
print(JevChecker().check(q).error)                 # No Jev key: pass api_key or set JEV_API_KEY
res = Ladder([JevChecker(), ClaudeChecker()]).run(q)
print(res.verdict)                                 # ASK (rungs with errors are skipped)
```

### `src/tcxp/registry.py`

- **Purpose:** Resolves what an address points to: data, a registered handler, or a content-addressed state snapshot. An address can reference a handler but never contains code.
- **Consumes:** `address`.
- **Consumed by:** `__init__`, `context`, `session`, `sql`, `trace`; `tests/test_core.py`.
- **Key API:**
  - `Registry(with_core=True)`: `put(address, resource)`, `get(address, default=None)`, `has(address)`, `addresses(prefix="")`.
  - `put_state(obj) -> Address` (`!tcxp:/state/sha256-<hash>`), `get_state(address)` (re-hashes; raises `KeyError` or `IntegrityError`).
  - `handler(name)` decorator (called as `@name?k=v`), `on(pattern)` decorator (`*` matches one path segment), `trigger(target, context=None, **extra)`, `handlers()`.
  - Built-in handlers: `@core.update`, `@core.highlight`, `@core.ask`, `@core.halt`, `@core.log`.
  - `parse_handler(text)`, `canonical_json(obj)`, `default_registry`; errors `IntegrityError`, `HandlerNotFound`.

```python
from tcxp import Registry

reg = Registry()

@reg.handler("my.double")
def double(params, ctx):
    return int(params["x"]) * 2

@reg.on("!tcxp:/reason/*")
def reason(params, ctx):
    return params

print(reg.trigger("@my.double?x=21"))                 # 42
print(reg.trigger("!tcxp:/reason/tax-year?y=2024"))   # {'y': '2024'}
p = reg.put_state({"a": 1})
print(p, reg.get_state(p))                            # !tcxp:/state/sha256-015a... {'a': 1}
```

### `src/tcxp/schema.py`

- **Purpose:** What makes tcxp typed. A Schema declares each key's type, answer space, whether it is essential, a default and a description. Invalid values are reported, never guessed.
- **Consumes:** `address`.
- **Consumed by:** `__init__`, `context`, `demo`, `governor`; `tests/test_core.py`.
- **Key API:**
  - `Field(name, type="str", values=(), essential=False, default=None, description="", many=False)`; `coerce(text)`. Types: `str`, `int`, `float`, `bool`, `date` (ISO `YYYY-MM-DD`), `address`, `handler` (`@name`).
  - `Schema(name, fields={})`, `Schema.of(name, *fields)`, `add(f)`, `essential`, `problems(address) -> list[Problem]`, `coerce(address) -> dict`, `dark(address)` (essential keys that are empty or invalid).
  - `to_address()` → `!tcxp:/schema/<name>?...`, `from_address(a)`, `to_dict()`, `from_dict(d)`; `SchemaError`, `Problem`, `TYPES`.

```python
from tcxp import Address, Field, Schema

s = Schema.of("section-41",
              Field("tax_year", "int", ("2023", "2024", "2025"), essential=True),
              Field("country", values=("US", "CA")))
a = Address.parse("!tcxp:/reason?country=FR&tax_year=")
print(s.dark(a))                                         # ('tax_year',)
print([str(p) for p in s.problems(a)])                   # ["country: 'FR' is not valid: ..."]
print(s.coerce(a.with_(country="US", tax_year=2024)))    # {'tax_year': 2024, 'country': 'US'}
print(s.to_address())                                    # !tcxp:/schema/section-41?...
```

### `src/tcxp/sql.py`

- **Purpose:** A small, versioned SQL engine (`tcxp-sql/0.1`) over CSV tables, and query cards whose `:slots` fill from context state. Every stored value is a string; comparisons are numeric when both sides are numbers.
- **Consumes:** `address`, `registry`.
- **Consumed by:** `__init__`, `__main__`, `demo`; `tests/test_tools.py`.
- **Key API:**
  - Dialect: `SELECT * | cols | SUM/COUNT/MIN/MAX(col) FROM t [WHERE col op value [AND …]]`, `BETWEEN … AND …`, values `'text'`, numbers or `:slot`. Anything else raises `SQLError`.
  - `Database(registry=None)`: `load_csv(name, source) -> Address` (CSV text or a `Path`; registers `!tcxp:/sql/table/<name>`; table names are letters, digits and `_`), `load_csv_file(name, path)` (raises `FileNotFoundError` for a missing file), `query(sql, params=None) -> Result`.
  - `Result(columns, rows, sql)`: `scalar()`. `Table.from_csv(name, source)`.
  - `QueryCard(id, title, template, derive=None, descriptions={})`: `slots`, `fill(state)`, `missing(state)`, `address(state)` → `!tcxp:/sql/card/<id>?...`, `run(db, state)`.
  - `tax_year_bounds(state)` derives `start_date` and `end_date`; `DIALECT = "tcxp-sql/0.1"`.

```python
from importlib import resources
from tcxp import Database, QueryCard
from tcxp.sql import tax_year_bounds

db = Database()
db.load_csv("payroll", resources.files("tcxp").joinpath("data/payroll.csv").read_text())
print(db.query("SELECT COUNT(*), SUM(wages) FROM payroll WHERE country = 'US'").rows)   # [['10', '144000']]
card = QueryCard("us-wages", "US wages in the tax year",
                 "SELECT SUM(wages) FROM payroll WHERE country = :country "
                 "AND pay_date BETWEEN :start_date AND :end_date", derive=tax_year_bounds)
print(card.missing({"country": "US"}))                              # ['start_date', 'end_date']
print(card.run(db, {"country": "US", "tax_year": 2024}).scalar())   # 99000
```

### `src/tcxp/trace.py`

- **Purpose:** The append-only log of every change to a context object's address. Each row holds the full address after the change (or a state pointer above `MAX_INLINE`) and a hash chained to the previous row.
- **Consumes:** `address`, `registry`.
- **Consumed by:** `__init__`, `context`, `session`, `sim`.
- **Key API:**
  - `Row(index, time, op, key, value, cause, address, prev_hash, hash, learnable=False, features="")`. `op` is `set`, `unset`, `append`, `trigger` or `decide`.
  - `Trace(clock=utc_now)`: `append(op, key, value, cause, address, learnable=False, features="") -> Row`, `verify(registry=None) -> list[str]` (empty = intact), `learnable()`, `summary()`, `to_dicts()`, `to_json()`, `to_csv()`, `to_dataframe()` (needs pandas), `Trace.from_dicts(rows)`, `last_hash`.
  - `utc_now()` returns ISO 8601 UTC with milliseconds.

```python
from tcxp.trace import Trace

t = Trace()
t.append("set", "tax_year", "", "init", "!tcxp:/reason?tax_year=")
t.append("set", "tax_year", "2024", "person:you", "!tcxp:/reason?tax_year=2024",
         learnable=True, features="FY24 credit")
print(t.verify())                  # []
print(t.summary()["changed"])      # {'tax_year': {'from': '', 'to': '2024', 'edits': 2}}
```

### `src/tcxp/session.py`

- **Purpose:** Session files (`format: tcxp-session/1`) hold a context object, every state it pointed to, and a playhead. A session file alone is enough to replay and verify it.
- **Consumes:** `address`, `context`, `convert`, `pretty`, `registry`, `trace`.
- **Consumed by:** `__main__`, `demo`, `tools/build_docs.py`; `tests/test_tools.py`.
- **Key API:**
  - `Session(context, playhead=0, path=DEFAULT_PATH)`: `save()`, `Session.load(path)` (checks every state hash), `Session.from_trace(trace, path, name="sim")`, `Session.reset(path) -> bool`.
  - Transport: `length`, `rewind(steps=None)`, `seek(step)`, `frames(steps=None)`, `play(steps=None, output="uri", speed=0.0, out=print, color=None) -> int`.
  - `frame(row, context, output="uri", total=None, color=None) -> str`; `DEFAULT_PATH = Path("tcxp-session.json")`.

```python
import tempfile
from pathlib import Path
from tcxp import ContextObject
from tcxp.session import Session

ctx = ContextObject("reason", params={"tax_year": ""})
ctx.confirm("tax_year", 2024, features="FY24 credit")
path = Path(tempfile.mkdtemp()) / "s.json"
Session(ctx, 0, path).save()
s = Session.load(path)
s.play(steps=1, color=False)     # prints step 0
s.seek(2)
print(s.playhead, s.length)      # 2 2
```

### `src/tcxp/pretty.py`

- **Purpose:** Terminal output: tables, highlights, and Lit/Dark coloring. Color is on in a terminal or notebook and off when piped; `TCXP_COLOR=1` forces it, `NO_COLOR=1` turns it off.
- **Consumes:** `address`, `facets`.
- **Consumed by:** `__main__`, `demo`, `roll`, `session`.
- **Key API:** `use_color()`, `paint(text, *styles, color=None)`, `strip(text)`, `highlight(text, spans, color=None)`, `table(headers, rows, color=None)`, `show_address(address, essential=(), color=None)`, `show_card(card, state, color=None)`, `show_verdict(verdict, color=None)`, `show_trace(trace, last=None, color=None)`.

```python
from tcxp.pretty import highlight, show_address, table

print(table(["key", "value"], [["tax_year", "2024"]], color=False))
print(show_address("!tcxp:/reason?tax_year=&tax_year.structure=", essential=["tax_year"], color=False))
print(highlight("tax year 2024", [(9, 13, "green")], color=True))
```

### `src/tcxp/roll.py`

- **Purpose:** The context roll: a piano-roll view of a trace. One column per step, one sub-row per key; a cell lights up when its value changes, and `·` marks an empty (Dark) value.
- **Consumes:** `address`, `pretty`.
- **Consumed by:** `__main__` (`roll`, `sequencer play`), `tools/build_docs.py`; `tests/test_cli_roll.py`.
- **Key API:** `Step(index, time, change, address)`; `steps_from_session(session) -> list[Step]`; `Roll(steps, past=3, future=2, key_width=26, cell_width=12)` with `render(now, color=None)`, `play(start=0, steps=None, speed=1.0, out=None, color=None, clear=None) -> int`, `to_dict()` (frames for the web docs).

```python
from tcxp import Address
from tcxp.roll import Roll, Step

a = Address.build("reason/x", {"tax_year": "", "task": ""})
steps = [Step(0, "t0", "init", a),
         Step(1, "t1", "set task", a.with_(task="s41")),
         Step(2, "t2", "set tax_year", a.with_(task="s41", tax_year=2024))]
print(Roll(steps, past=1, future=1).render(1, color=False))
```

### `src/tcxp/bench.py`

- **Purpose:** Benchmark on ten requests with known ground truth: is the tax year stated, and does each arm act or ask correctly? Scores correct, silent errors and extra asks.
- **Consumes:** `ladder`; `models` when `mode="real"`.
- **Consumed by:** `__main__` (`bench`, `learn`), `demo`, `fleet`; `tests/test_tools.py`.
- **Key API:** `run_bench(mode="simulated", seed=0, arms=None, jev_key=None, claude_key=None) -> list[BenchRow]`. Arms: `code`, `llm_alone`, `llm_with_context`, `jev_alone`, `jev_with_context`, `ladder`. `detect_tax_year(text) -> str | None`. Data: `CASES`, `OPTIONS`, `CONTEXT_RULES`, `SIM_LLM`, `SIM_JEV` (declared assumptions for simulated rungs). `BenchRow` fields: `arm`, `correct`, `silent_errors`, `extra_asks`, `errors`, `ms`, `tokens`, `cost`, `simulated`, `details`.

```python
from tcxp.bench import detect_tax_year, run_bench

print(detect_tax_year("Calculate the R&D credit for FY24."))   # 2024
for r in run_bench("simulated", arms=("code", "llm_alone", "ladder")):
    print(r.arm, r.correct, r.silent_errors, r.extra_asks)
```

### `src/tcxp/learn.py`

- **Purpose:** A small softmax perceptron that trains in milliseconds from confirmed answers (learnable trace rows). It can act as a ladder rung.
- **Consumes:** `ladder`.
- **Consumed by:** `__main__` (`learn`), `fleet`; `tests/test_tools.py`.
- **Key API:** `SoftmaxPerceptron(classes, dim=1024, epochs=40, lr=0.5, seed=7)` with `fit(texts, labels)`, `partial_fit(text, label, passes=3)`, `predict_proba(text)`, `predict(text) -> (label, confidence)`, `evaluate(texts, labels, threshold=0.6) -> Evaluation`, `as_checker(name="perceptron")`. Also `examples_from_trace(rows, key=None)`, `reliability_curve(train, test, classes, ks=None, threshold=0.6)`, `confidence_of(probs)`, `Evaluation(n, accuracy, confident_accuracy, coverage)`.

```python
from tcxp.learn import SoftmaxPerceptron

texts = ["Credit for tax year 2024", "FY25 numbers please", "Estimate our credit", "What can we deduct?"]
labels = ["stated", "stated", "not_stated", "not_stated"]
m = SoftmaxPerceptron(["stated", "not_stated"]).fit(texts, labels)
print(m.predict("QREs for tax year 2023"))        # ('stated', 0.89...)
m.partial_fit("How much did research cost?", "not_stated")
checker = m.as_checker()                           # a rung for Ladder
```

### `src/tcxp/reliability.py`

- **Purpose:** Planning estimates for how many verified examples a decision needs before it is safe to automate, and how long collecting them takes.
- **Consumes:** nothing from tcxp.
- **Consumed by:** `__main__` (`budget`); `tests/test_tools.py`.
- **Key API:** `end_to_end_error(cost, tolerated, floor_pct=95.0)`, `per_step_error(e2e, steps)`, `cases_needed(e, confidence=0.95, failures=0)`, `weeks_to(n, volume, answered_pct)`, `recommend(weeks)`, `binom_cdf(n, e, f)`, `budget(steps, cost, tolerated, volume, answered_pct, floor_pct=95.0, confidence=0.95, failures=0) -> Budget(e2e, per_step, cases, weeks, recommendation)`.

```python
from tcxp.reliability import budget, cases_needed

print(cases_needed(0.01))     # 299
b = budget(steps=6, cost=50000, tolerated=100, volume=40, answered_pct=90)
print(b.cases, round(b.weeks, 1), b.recommendation)   # 8979 249.4 Keep a person on it, or split it
```

### `src/tcxp/sim.py`

- **Purpose:** Simulates how a Dark structure facet (date format) spreads through hand-offs in an organization. With the facet Dark each reader guesses and the guess becomes the next hop's intent. `gate=True` asks at the first hop. The whole run is reproducible from its `!tcxp:/sim/org` address.
- **Consumes:** `address`, `trace`.
- **Consumed by:** `__main__` (`sim`), `tools/build_docs.py`; `tests/test_tools.py`.
- **Key API:** `SimConfig(employees=50, agents=10, tasks=20, decisions_per_task=3, steps_min=2, steps_max=7, cycles=3, ambiguity=0.3, gate=False, share_resolutions=True, cost_error=1000.0, ask_cost=5.0, seed=42)` with `to_address()` and `from_address(a)`; `Organization(config=None, **overrides)` with `run() -> SimResult` and `stream()`; `SimResult.metrics`, `SimResult.by_team()`, `SimResult.to_trace()`; `Hop.address()` → `!tcxp:/sim/hop?...`; `TEAMS`, `FORMATS`.
- **Teams:** `SimConfig(teams="marketing:2000:0.5,engineering:2000:0.2")` replaces `employees`/`agents`; each decision's Dark chance is the ambiguity of the team where it starts. `parse_teams(spec)` validates the spec.
- **Stories:** `STORIES` maps a name to `(description, address)`; `story(name, **overrides) -> SimConfig`. Built in: `launch`, `section41`, `merger`, `agent-swarm`, `startup`. A story is just a sim address, so new ones are one line. Settings never persist between CLI runs, so there is nothing to reset.

```python
from dataclasses import replace
from tcxp.sim import Organization, SimConfig

cfg = SimConfig(tasks=5, cycles=2)
for c in (cfg, replace(cfg, gate=True)):
    m = Organization(c).run().metrics
    print(c.gate, m["silent_errors"], m["asks"], m["total_cost"])   # False 8 0 8000.0 / True 0 7 35.0
print(Organization(cfg.to_address()).run().metrics == Organization(cfg).run().metrics)   # True
```

### `src/tcxp/flow.py`

- **Purpose:** Turns a manager's plain-language reasoning cards into gates you can see, approve and run. The picture is a process map: the **query** box, then one **gate** (diamond) per yes/no question, true to the right, false down, and a SQL card at the end. A gate's test is written in **TQL**; its **outcomes** are lists of `@handler` calls. Gates are addresses (`!tcxp:/gate/<id>?…`) stored in the context object's `reason` list beside rules.
- **TQL:** `known(key)`, `dark(key)`, `has(key, "text")` (whole-word, any case), `key = "v"` / `!=` / `<` / `>` / `<=` / `>=` number, combined with `and`, `or`, `not` and parentheses. A test that needs a Dark key is unknown: it follows the false branch and the key is asked for. `parse_tql`, `format_tql` (one canonical spelling), `evaluate(test, state) -> (True|False|None, dark_keys)`.
- **Reasoning cards:** `compile_card(text, gates=(), by="", target="", slots=None, proposer=None) -> CardResult(gate, new)`. Understood without a model: "If the query contains X, highlight it" · "For Section 41, require the tax year" / "Don't answer until the tax year is confirmed" · "If false, alert that … / ask for … / halt" (attaches to `target` or the last gate) · "Test: <TQL>". Anything else goes to `proposer(text)` (Jev or an LLM), whose answer is validated like typing. Otherwise `CardNotUnderstood` lists phrasings that work.
- **Approval:** new gates are `proposed` (shown and evaluated, actions don't fire). `@core.approve?gate=<id>&by=<who>` approves one; the call is the approval and the trace records who. `@core.notify` raises an alert. `@core.ask` and `@core.halt` stop the flow.
- **Consumes:** `address`, `registry`, `context`, `demo`, `pretty`, `sql`, `session`.
- **Consumed by:** `__main__` (`flow`), `tools/build_docs.py`; `tests/test_flow.py`; mirrored in `npm/flow/` (both pass `conformance/tql_vectors.json`).
- **Key API:** `Gate(id, test, if_true=(), if_false=(), next_true="", next_false="", status="proposed", card="", by="", approved_by="")` with `address()` / `from_address`; `Flow(context, query_key="query", card=None, db=None)` with `gates`, `add_card(text, by, target, proposer)`, `approve(id, by)`, `run(query) -> FlowResult(steps, stopped_at, asks, alerts, halted, highlights, address)`; `flow_demo()`; `draw_flow(flow, result)`; `describe(action)`; `repl(...)`.

```python
from tcxp.flow import flow_demo, draw_flow

f = flow_demo()                                    # query box + Section 41 SQL card, no gates yet
g = f.add_card("For Section 41 tax preparation, require the tax year.", by="manager")
f.add_card("If false, alert that it's halted and you cannot proceed.", by="manager")
f.approve(g.id, "manager")
r = f.run("What should I deduct for Section 41 US-based QREs we paid yesterday?")
print(r.stopped_at, r.asks, r.alerts)              # tax-year-required ['tax_year'] ["ALERT: it's halted and you cannot proceed"]
r = f.run("… US-based QREs for tax year 2024?")
print(r.passed)                                    # True: the card runs (SUM(wages) = 99000)
```

### `npm/flow/`

- **Purpose:** The same flow in vanilla JavaScript for the browser: `tql.js` (TQL), `gate.js` (gates as addresses), `card.js` (reasoning cards), `sql.js` (tcxp-sql/0.1 subset and query cards), `flow.js` (sensors, run, core handlers), `view.js` (the process map), `page.html` (the page; `tools/build_flow.py` writes `index.html`). No dependencies beyond `npm/index.js`.
- **Run it:** `npx tcxp docs --flow`, `npx tcxp serve` → `/flow/`, or `tcxp docs --flow` from a pip install. `npm test` runs `test-flow.js` on the shared vectors.

### `src/tcxp/expr.py`

- **Purpose:** Writes a rule as math. Infix text (`3 + 2y = 9`) becomes an expression tree (each operator is a parent of the two things it combines), and the tree becomes one flat address, one key per node. Folding evaluates bottom-up with exact fractions; a variable with no value in state is Dark, so the fold stops and lists it instead of guessing. `solve` finds the one Dark variable of a linear equation without any model.
- **Consumes:** `address`.
- **Consumed by:** `__main__` (`expr`); `tests/test_stories_expr.py`.
- **Key API:** `parse(text)`, `to_address(tree, path="expr")`, `from_address(a)`, `fold(tree_or_address, state) -> Fold(value, dark, steps)`, `solve(tree, state) -> {name: Fraction}`, `draw(tree, state)`, `Node(op, left, right)`, `OPS` (`add sub mul div eq`). Children are node ids (`n3`), numbers or variable names; names like `n2` are reserved.

```python
from tcxp.expr import parse, to_address, fold, solve

a = to_address(parse("3 + 2y = 9"))
print(a)                       # !tcxp:/expr?n1=eq&n1.l=n2&n1.r=9&n2=add&n2.l=3&n2.r=n3&n3=mul&n3.l=2&n3.r=y&root=n1
print(fold(a).dark)            # ('y',)  -> ask, don't guess
print(solve(a))                # {'y': Fraction(3, 1)}
print(fold(a, {"y": "3"}).value)   # True
```

### `src/tcxp/fleet.py`

- **Purpose:** Runs one seeded request stream through many Observatrons in four arms (`llm_alone`, `jev_alone`, `context`, `context_learning`). Reports accuracy, silent errors, asks, model cost, regret and risk taken per epoch. The learning arm uses a perceptron guard that learns online and can veto.
- **Consumes:** `address`, `bench`, `ladder`, `learn`; `models` when `mode="real"`.
- **Consumed by:** `__main__` (`fleet`); `tests/test_fleet.py`.
- **Key API:** `FleetConfig(observatrons=10000, requests_per=3, epochs=10, stated_rate=0.5, hidden_rate=0.25, trap_rate=0.3, cost_error=1000.0, ask_cost=5.0, threshold=0.8, guard_threshold=0.9, share=True, drift_epoch=5, drift_rate=0.5, seed=7)` with `to_address()` / `from_address(a)`; `Fleet(config=None, mode="simulated", limit=None, jev_key=None, claude_key=None, **overrides)` with `run() -> FleetResult` and `stream()`; `FleetResult.totals(arm)`, `FleetResult.delta()`; `generate_requests(...)`, `Request`, `ARMS`.

```python
from tcxp.fleet import ARMS, Fleet, FleetConfig

res = Fleet(FleetConfig(observatrons=100, epochs=4, drift_epoch=2)).run()
for arm in ARMS:
    t = res.totals(arm)
    print(arm, f"{t['accuracy']:.2%}", t["silent_errors"], t["asks"])
print(res.delta()["silent_errors"])   # context_learning minus llm_alone
```

### `src/tcxp/demo.py`

- **Purpose:** The Section 41 terminal demo. Each line shows highlighted sensor matches, Lit/Dark state, the SQL card and the verdict. When the manager's rule needs the tax year it asks, records a learnable row, runs the card on `payroll.csv` and saves a session. Commands: `:address [format]`, `:trace`, `:summary`, `:rule <sentence>`, `:ladder`, `:help`, `:quit`.
- **Consumes:** `address`, `bench`, `bus`, `context`, `convert`, `governor`, `ladder`, `pretty`, `schema`, `session`, `sql`, `data/payroll.csv`.
- **Consumed by:** `__main__` (`demo`), `tools/build_docs.py`; `tests/test_tools.py`.
- **Key API:** `section41(registry=None) -> (ContextObject, Observatron, Database, QueryCard)`; `run(lines=None, answer=None, session_path=DEFAULT_PATH, color=None, out=print, show_ladder=False) -> ContextObject` (pass `lines` and `answer` to script it); `MANAGER_RULE`.

```python
import tempfile
from pathlib import Path
from tcxp.demo import run, section41

ctx, obs, db, card = section41()
print(obs.feed("What should I deduct for Section 41 US-based QREs?").verdict)   # ASK: tax_year before 'answer'
path = Path(tempfile.mkdtemp()) / "demo.json"
ctx = run(["What should I deduct for Section 41 US-based QREs?", ":quit"],
          answer=lambda prompt: "2024", session_path=path, color=False, out=lambda s: None)
print(ctx.get("tax_year"), ctx.decision[-1].kind)                              # 2024 ACT
```

### `src/tcxp/data/payroll.csv`

- **Purpose:** Sample payroll table (13 rows) for the demo and docs. Columns: `employee, role, country, pay_date, wages, qualified_pct, project`. It mixes US and CA rows, 2024 and 2025 pay dates, and a project named "Atlas (2025 launch)" as a tax-year trap.
- **Consumes:** nothing.
- **Consumed by:** `demo.py` (via `importlib.resources`), `tools/build_docs.py` (copied for the SQL scene).

---

## Tools

### `tools/build_docs.py`

- **Purpose:** Builds `docs/index.html` and `docs/artifact.html` by running real commands and API calls and capturing their colored output, so the docs cannot drift from the code. Run with `python tools/build_docs.py`.
- **Consumes:** `tcxp` (`__version__`), `tcxp.demo.run`, `tcxp.roll` (`Roll`, `steps_from_session`), `tcxp.session.Session`, `tcxp.sim` (`Organization`, `SimConfig`), `src/tcxp/data/payroll.csv`, `tools/docs_template.html`; runs `python -m tcxp` in a temp directory.
- **Consumed by:** nothing in the repo (run by hand).
- **Key API:** `sh(cmd, shown=None)`, `demo_transcript()`, `roll_frames(session_path)`, `build() -> list[dict]` (scenes: version, convert, observatron, roll, sim, wave, bench, sql, budget, learn, play), `main()`.

### `tools/docs_template.html`

- **Purpose:** The page template for the generated docs. `build_docs.py` replaces `__SCENES__` (JSON scene data) and `__VERSION__`.
- **Consumes:** nothing.
- **Consumed by:** `tools/build_docs.py`.

---

## JavaScript and conformance

### `npm/index.js`

- **Purpose:** The JavaScript port of `tcxp.address`: parsing and canonical form, with the same rules as the Python reference. ES module, Node 18+.
- **Consumes:** nothing (no dependencies).
- **Consumed by:** `npm/test.js`; it is the package entry (`main` and `exports` in `npm/package.json`).
- **Key API:** `Address.parse(text)`, `Address.prefix(form, authority)`, `toString()`, `toURI()`, `get(key, fallback)`, `getAll(key)`, `toObject()`, `with(values)`; `AddressError`, `encode`, `decode`, `isAddressText`, `parseQuery`, `VIRTUAL_PREFIX`, `MAX_INLINE`, `VERSION`, `URI` (includes `runtime=js`).

### `npm/test.js`

- **Purpose:** Runs every conformance vector against `npm/index.js` and exits 1 on any failure. Run with `npm test` in `npm/`.
- **Consumes:** `npm/index.js`, `npm/vectors.json` (a copy of `conformance/vectors.json`; the files are identical).
- **Consumed by:** the `test` script in `npm/package.json`.

### `conformance/vectors.json`

- **Purpose:** Shared address test vectors (`format: tcxp-conformance/1`). 17 valid vectors (each with `input`, `canonical`, `uri`, `form`, `authority`, `path`, `params`, `note`) and 12 invalid ones (`input`, `note`) that must raise `AddressError`.
- **Consumes:** nothing.
- **Consumed by:** `tests/test_address.py`; copied to `npm/vectors.json` for `npm/test.js`.

## Tests

### `tests/`

- **Purpose:** The pytest suite (82 tests). Run with `PYTHONPATH=src python3 -m pytest tests`.
- **Files:** `test_address.py` (conformance vectors, canonical form, encode/decode, forms), `test_core.py` (schema, spikes, bus, registry, rules, governor, Observatron, trace, conversions), `test_tools.py` (reliability, SQL, query cards, sim, ladder, bench, perceptron, demo and playback), `test_cli_roll.py` (roll rendering and CLI `version`, `convert`, `sim --record`, `sequencer`, `bench`, `budget`, `sql`), `test_fleet.py` (request generation, arms, reproducibility, CLI).
- **Consumes:** `tcxp` top-level API, `address`, `convert`, `governor`, `registry`, `roll`, `__main__`, `fleet`, `ladder`, `bench`, `demo`, `learn`, `reliability`, `session`, `sim`, `sql`; `conformance/vectors.json`.
- **Consumed by:** nothing (run by developers or CI).

---

## Reserved virtual namespaces

These virtual paths are built or recognized by the library source:

- `!tcxp:/state/sha256-<hash>`: content-addressed state (`Registry.put_state`, trace snapshots, session files).
- `!tcxp:/lib/tcxp?...`: the library's own version address (`tcxp.__uri__`).
- `!tcxp:/rule/<id>?...`: a rule (`Rule.address`).
- `!tcxp:/decision?...`: a verdict (`Verdict.address`).
- `!tcxp:/schema/<name>?...`: a schema (`Schema.to_address`). The demo and simulator also use `!tcxp:/schema/year/yyyy`, `!tcxp:/schema/date/mm-dd-yyyy` and `!tcxp:/schema/date/dd-mm-yyyy` as structure facets.
- `!tcxp:/sql/table/<name>`: a loaded CSV table (`Database.load_csv`).
- `!tcxp:/expr?...`: an expression tree (`tcxp.expr`).
- `!tcxp:/sql/card/<id>?...`: a query card and its slots (`QueryCard.address`).
- `!tcxp:/sim/org?...`: an organization simulator run (`SimConfig.to_address`).
- `!tcxp:/sim/hop?...`: one simulated hand-off (`Hop.address`).
- `!tcxp:/sim/fleet?...`: a fleet run (`FleetConfig.to_address`).
