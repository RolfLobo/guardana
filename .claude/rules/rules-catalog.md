---
paths:
  - "packages/guardana-rules/**"
  - "examples/custom_rule/**"
---
# Rules, evaluators and the catalogue

Procedure: the `add-a-rule` skill. Why: `docs/maintainers/lessons.md` § Rules and seams.

- **YAML is the default** for "send this prompt, grade with this evaluator"; a Python plugin only
  for logic YAML cannot express. Unknown keys are rejected at load time — a typo'd `promts:`
  would otherwise run zero prompts and pass everything. `steps:` makes a `ScenarioRule`.
- **A framework mapping in edition form, or it does not ship**: `LLM07:2025`, `AML.T0056`,
  never a bare `LLM07`. `guardana taxonomy` lists what is installed; taxonomies load before
  rules because a YAML rule resolves `taxonomy:` while its entry point is read.
- **A positive and a negative fixture** (and an inconclusive one where the rule can be unable
  to decide). `guardana rule test` reports a rule with only a positive as `indeterminate`, not
  green. `guardana.core.testing` scripted transports make the negative three lines, no network.
- **Declare `impact`, `destructive` and `estimated_requests`.** The last is an upper bound and a
  gate measures every shipped rule against its own declaration.
- **Record what you measured**: a rule that grades a reply calls `ctx.record(from_verdict(...))`
  for every case, passes included — without the passes there is no denominator. A rule that
  only reads a file records nothing.
- **`guardana.*` is reserved for built-ins and enforced at load**; third parties namespace
  (`acme.*`). `examples/custom_rule/` is the stand-in for every third party and registers all
  four entry-point groups on purpose — a documented seam nothing exercises is a seam nobody has
  run.
- After any change here: `uv run python scripts/generate_docs.py` (never edit
  `docs/generated/`), `FEATURES.md` if the surface moved (a registry test refuses a built-in
  missing from it), and `uv run guardana scan packages` stays at zero findings.
- Test the example in isolation: `uv run --isolated --no-cache --with … pytest
  examples/custom_rule/tests -q`; `--no-cache` is load-bearing (`scripts/ci_local.sh` runs it).
