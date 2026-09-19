---
paths:
  - "examples/**"
---
# Examples — the third-party story, and one deliberate poison

Why: `docs/maintainers/lessons.md` § Rules and seams.

- **`examples/vulnerable-model/` is deliberately malicious** (a pickle that calls `os.system`).
  `guardana scan .` is supposed to exit 1; the dogfood gate scans `packages/`. Never "fix" the
  fixture, never exclude it from a scan to make a demo green; ruff excludes it on purpose.
- **The three isolated suites are the extension contract as somebody else sees it**:
  `custom_rule` (consumer: rules, evaluators, targets, taxonomies through all four entry-point
  groups), `hermes_integrator` (producer: a third party's entry-point group, one file per
  session) and `shell_hook_integrator` (producer: a command spawned per event, three processes
  sharing a file — the only gate that exercises `resume_trace` across real process boundaries).
- **Run them isolated and with `--no-cache`**: `uv run --isolated --no-cache --with
  ./packages/guardana-core … --with ./examples/<name> --with pytest pytest
  examples/<name>/tests -q`. A cached wheel hides exactly the data files (`guardana-pack.yaml`,
  the YAML rules) an extension change touches; `--refresh` does not help. Installing `acme.*`
  into the main environment would skew the dogfood scan, which is why `uv run pytest` cannot
  see these.
- **Integrators never import the agent they integrate**; payloads are copied from upstream
  documentation, which keeps them runnable in CI. Checking against the real thing is a manual
  step each README documents.
- A change to `Rule`, `Evaluator`, `Target`, an entry-point group, the pack manifest or the
  trace format is not done until all three suites are green here.
