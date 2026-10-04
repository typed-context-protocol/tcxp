# Changelog

## 0.1.0 (unreleased)

First release of the reference library.

- Addresses: `!tcxp:/` virtual pointers, `tcxp://` registry addresses and the `https://…/tcxp/…`
  carrier form; one canonical spelling; content-addressed state (`!tcxp:/state/sha256-…`).
- Context objects with observe, intent, reason, decision and trace; the intent map gates which registered
  handlers a decision may call; the Observatron sensor loop;
  `@handler` references; ACT/ASK/HALT governor with absorbing HALT.
- Hash-chained trace with integrity checks on load; play, rewind, seek, reset; the context roll.
- Check ladder (code → Jev → LLM → person) with real and simulated rungs; benchmark across six arms.
- Sparse perceptron trained from confirmed trace rows; reliability curve; reliability budget.
- `tcxp-sql/0.1` SELECT-only engine over CSV; SQL query cards with slots.
- Organization simulator and the 10,000-Observatron fleet.
- Decision flows: reasoning cards in plain language compile into gates (TQL yes/no tests with
  true/false outcomes), proposed until approved via `@core.approve`; `tcxp flow` in the terminal and a
  vanilla-JS flow page (`tcxp docs --flow`, `npx tcxp serve` → /flow/), sharing conformance vectors.
- Simulated stories and per-team settings; expression trees (`tcxp expr`).
- Converters: JSON, dict, CSV, SQL, Python, JavaScript, C++, Java.
- npm package `tcxp`: JavaScript address parser (same conformance vectors), the `tcxp` command,
  a local docs/API server, and the bundled Python wheel.
- Licensed under the W3C Software and Document License (W3C-20150513).
