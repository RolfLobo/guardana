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

## Found while sampling the declarative catalog

Both were found on 2026-09-19 writing fixtures for the agent rules, and both are evaluator
changes rather than fixture changes (`docs/design/declarative-fixtures.md`, Decision 6).

- `guardana.agent.tool_argument_scope` reports the exact path its task names as over-broad:
  `forbidden_argument_values: ["*", "/tmp/", ".."]` is matched as substrings, and
  `/tmp/session-42.log` contains `/tmp/`. Reproduce with a scripted agent calling
  `delete_file` with `{"path": "/tmp/session-42.log"}` — the rule yields `fail`. It needs a
  `tool_call` criterion that says "wider than the named file" (an allowed exact value, or
  anchored matching); until then the rule ships no clean fixture and `rule test` says so.
- Without a clean fixture, `tool_argument_scope`'s finding sample would also pass a
  meaningless criterion (`forbidden_argument_values: ["path"]` matches the JSON key) — one
  more reason the missing clean sample above is worth the evaluator change.
- `guardana.agent.memory_poisoning` passes a model whose first session saved *something*
  other than the poison: the store is not empty, the second session recalls it and behaves.
  Whether the poison itself crossed would need a marker the rule does not declare.
- `canary` over an agent run reads only the last prose turn (`Exchange.from_trajectory` keeps
  prose steps, `reply_text` is the last one), so a model that recites a marked tool schema while
  calling a tool and then says "Done." is graded clean. The shipped fixtures of
  `guardana.agent.hidden_context.tool_schema` are single-turn, which is the case the rule grades.

## Deferred by the declarative fixtures design

- A load check that the tool a rule names in `delivered_by` returns a payload at all. A
  scripted fixture cannot see it: `tool_result_injection` with its notice deleted still
  passes all three samples, so only the rule file can be checked for it.

- A way for a fixture to say *why* a rule must decline or *which* turn must fire —
  `verify_rule` folds every result into one of three outcomes, for Python fixtures too. An
  additive field on `RuleFixture`, so a change to the contract every fixture shares.
- Corpus rows for multi-step scenario and agent-run fixtures: the graded prefix is the rule's
  knowledge and a `tool_call` verdict has no column in the corpus format.

## Tooling debt

- Four scripts have no argument parser and run for real when handed `--help`:
  `scripts/release.py` (fetches from origin, runs the whole gate), `scripts/clean_install_check.py`,
  `scripts/generate_sbom.py`, `scripts/image_smoke.py`. A few lines of `argparse` each; the
  `guard_hook.py` `ask` on `release.py` is the interim guard.
- `site/og.png` is rendered by hand from `scripts/og_card.html` and nothing checks the two agree.
- `.github/workflows/ci.yml` has no job for `scripts/check_claude_setup.py` and
  `scripts/check_ops_catalogue.py`; they run locally through `scripts/ci_local.sh` only. Adding
  them to the `test` job is a two-line change, deferred so the setup lands without touching CI.
