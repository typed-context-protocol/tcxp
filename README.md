# tcxp: the Typed Context Protocol

**A decision's context, as an address you can read, share, check and replay.**

`tcxp` is the reference implementation of the Typed Context Protocol, the specification
developed in the W3C Typed Context Protocol Community Group. It keeps everything a
decision depends on in one typed **context object** whose state is always a single
address:

```
!tcxp:/reason/s41?country=US&task=section_41_qre&tax_year=
```

`tax_year=` is **Dark**: the key is known to matter but has no value. A rule such as
*"Don't give the answer until the tax year is confirmed"* turns that into a question
for a person instead of a guess. Every change is a row in a hash-chained trace, so any
step can be replayed, checked or used to train a small model.

- **Standard library only.** No dependencies; Python 3.10+.
- **Works in a terminal, a notebook (Jupyter, Colab) and from Node** (`npx tcxp`).
- **Deterministic first.** Code answers what it can. Jev, then an LLM, then a person
  only answer what's left.

## Install

```bash
pip install tcxp          # Python library + the `tcxp` command
npx tcxp demo             # or from npm: installs the bundled Python library on first use
```

From a source checkout, `sh install.sh` installs both and puts `tcxp` on your PATH.

## Sixty seconds

```bash
tcxp demo                 # the Section 41 question; the Observatron catches the missing tax year
tcxp roll                 # replay it as a context roll: a piano roll for state
tcxp sim --compare        # an organization's hand-offs, with and without the gate
tcxp fleet                # 10,000 Observatrons: accuracy, cost and risk, with and without context
tcxp flow                 # type a query; reasoning cards become yes/no gates
tcxp docs --flow          # the same flow in your browser, as you type
tcxp docs                 # the animated docs, served locally
```

```python
from tcxp import Address, ContextObject

ctx = ContextObject("reason/s41", params={"task": "section_41_qre", "tax_year": ""})
ctx.add_rule("Don't give the answer until the tax year is confirmed", slots={"tax year": "tax_year"})

ctx.decide().kind           # 'ASK'   (tax_year is Dark)
ctx.confirm("tax_year", "2024")
ctx.decide().kind           # 'ACT'
print(ctx.address)          # !tcxp:/reason/s41?task=section_41_qre&tax_year=2024
```

## Addresses

| Form | Meaning |
| --- | --- |
| `!tcxp:/reason?…` | Virtual, in-memory pointer. The `!` says *this is not a network address*. |
| `tcxp://host/path?…` | A registry address. |
| `https://host/…/tcxp/path?…` | The same address carried over HTTPS. |
| `!tcxp:/state/sha256-…` | Content-addressed full state, for anything too long to inline. |
| `@core.update?tax_year=2024` | A reference to a registered handler. Addresses never contain code. |
| `!tcxp:/intent/us-wages?allows=@sql.run&…` | A confirmed intent: what someone meant, and which handlers that allows. |

**Who decides what runs.** The *registry* is shared and lists what can run. A context
object's *intent map* lists what this decision meant to run. `ctx.call("@sql.run?…")`
runs only when both agree; built-in `@core.*` handlers act on the object itself and are
always allowed.

Canonical form: keys sorted, repeated keys kept in order, UTF-8 percent-encoding with
uppercase hex. Python and JavaScript produce byte-identical output; both pass
`conformance/vectors.json`.

## What's inside

| Module | Purpose |
| --- | --- |
| `address` | Parse, build and canonicalize addresses. |
| `schema` | Types, answer spaces and essential keys (what makes it *typed*). |
| `facets` | Spikes: the `data` anchor and `meaning`, `structure`, `environment` facets; Lit/Dark; MATCH. |
| `context` | `ContextObject` (observe, intent, reason, decision, trace), the intent gate, and the `Observatron` sensor loop. |
| `governor` | Rules (`when`/`require`/`verdict`) and ACT/ASK/HALT. HALT is absorbing. |
| `trace`, `session`, `roll` | The hash-chained trace, play/rewind/seek, and the context roll. |
| `registry`, `bus` | Content-addressed state, `@handler` routing, an event bus. |
| `ladder`, `models` | Code → Jev → LLM → person, with real (Jev, Claude) and simulated rungs. |
| `learn` | A sparse perceptron trained from confirmed trace rows, with a reliability curve. |
| `flow` | Reasoning cards in plain language become gates (yes/no diamonds) you can see, approve and run; TQL. |
| `sql` | `tcxp-sql/0.1`, a tiny SELECT-only engine over CSV, and query cards with slots. |
| `sim`, `fleet`, `bench` | Organization simulator, 10,000-Observatron fleet, and the arm benchmark. |
| `reliability` | How many verified examples a decision needs before you automate it. |
| `convert`, `pretty` | JSON, CSV, SQL, Python, JS, C++ and Java; terminal pretty printing. |

Full API and every file's purpose, inputs and consumers:
[docs/REFERENCE.md](https://github.com/typed-context-protocol/tcxp/blob/main/docs/REFERENCE.md).
A runnable tour: [examples/quickstart.ipynb](https://github.com/typed-context-protocol/tcxp/blob/main/examples/quickstart.ipynb).

## Real models

Simulated rungs are the default and declare their assumptions. To call real models,
set keys in your environment (never in code you share):

```bash
export JEV_API_KEY=…  ANTHROPIC_API_KEY=…
tcxp bench --real
tcxp fleet --real --limit 50      # --limit caps spend
```

## License

Licensed under the **W3C Software and Document License (W3C-20150513)**. See `LICENSE`.
