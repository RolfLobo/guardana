---
paths:
  - "packages/guardana-cli/**"
  - "packages/guardana-report/**"
---
# The CLI and the renderers

Why: `docs/maintainers/lessons.md` § CLI and outputs. Contract: `docs/exit-codes.md`.

- **Exit codes are a contract.** A new outcome gets its own code and a row in
  `docs/exit-codes.md` and the design table; a code is never reused for a different meaning.
- **No false green from any direction**: an unsupported capability, an exhausted budget, a
  redaction failure, missing coverage, a comparison that could not be made — each is its own
  outcome and exit code, never a pass. `diff` says better, worse, unchanged or incomparable.
- **Every output stays behind the common redaction boundary.** A renderer never learns a
  threat and never re-derives a verdict; it renders the `Finding`s it is given.
- **The layer contract**: CLI over packages over core. A renderer importing a rule, or a rule
  reaching for a CLI helper, breaks `uv run lint-imports`.
- **A target is selected by locator** (`--target scheme://locator`); malformed, unknown,
  reserved or mismatched schemes are refused before a rule runs, and the command owns the kind.
- **Plugin trust**: discovery always runs; `--plugins disabled` refuses and records every
  refusal (`SECURITY.md`). `import-observations` runs with plugins disabled and no flag.
- **Styled output is normalised in tests** — assert on the normalised text, never on escape
  sequences or column widths that differ between a laptop and a CI runner.
- A new command or flag: `docs/usage-<command>.md`, `docs/index.md`, `FEATURES.md`,
  `CHANGELOG.md`, and `scripts/clean_install_check.py` runs the documented invocation in an empty
  environment — the only gate that sees an undeclared import.
- `probe`, `monitor`, `target inspect` and `calibrate` contact whatever endpoint the user names;
  `plan probe` never does. A budget bounds requests before the first one is sent, and sending
  more than `--max-requests` is a defect that has shipped once.
