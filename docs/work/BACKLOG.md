# Backlog — open work with no owner right now

Each item says where it stands IN THE CODE, as verified on 2026-09-18 when the agent setup was
rebuilt. An item leaves this file by becoming a work file (`/plan`) or by being dropped with a
reason in the commit message. Priorities live in `ROADMAP.md`; this file is the inventory.
Re-verify an item before starting it — several sessions work in this repo.

## Accepted designs the roadmap does not carry

Both are `proposed`, written as cycles 4 and 5 of the extensibility program
(`docs/design/audit-0.22.md`), and have no code behind them. Neither appears in the "Now"
table of `ROADMAP.md`, so they are neither scheduled nor rejected — a decision, then either a
roadmap row or a `superseded by` line.

- `docs/design/attack-techniques.md` — a `Technique` abstraction shared by rules; zero hits in
  `packages/` for the names it introduces.
- `docs/design/namespaced-extension-ids.md` — an open id registry for third-party extensions;
  the `guardana.*` reservation is enforced, the registry is not built.

## Tooling debt

- Four scripts have no argument parser and run for real when handed `--help`:
  `scripts/release.py` (fetches from origin, runs the whole gate), `scripts/clean_install_check.py`,
  `scripts/generate_sbom.py`, `scripts/image_smoke.py`. A few lines of `argparse` each; the
  `guard_hook.py` `ask` on `release.py` is the interim guard.
- `site/og.png` is rendered by hand from `scripts/og_card.html` and nothing checks the two agree.
- `.github/workflows/ci.yml` has no job for `scripts/check_claude_setup.py` and
  `scripts/check_ops_catalogue.py`; they run locally through `scripts/ci_local.sh` only. Adding
  them to the `test` job is a two-line change, deferred so the setup lands without touching CI.
