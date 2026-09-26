# Guardana roadmap

This file is the ordered plan. It intentionally does not repeat the feature
catalog, framework coverage, release history, or design debates:

- [FEATURES.md](FEATURES.md) says what ships;
- [the generated rule summary](docs/generated/rule-summary.md) and
  [rule catalog](docs/generated/rule-catalog.md) are the coverage source of truth;
- [CHANGELOG.md](CHANGELOG.md) records history;
- [docs/design/](docs/design/) records accepted and rejected design choices.

Items are ordered by dependency, not promised dates. Work moves up when user
evidence changes the order.

## Product constraints

Every roadmap item must preserve these properties:

1. A check that did not run or could not decide is never reported as a pass.
2. Offline scanning stays offline; active checks run only when requested.
3. Guardana remains outside the production request path.
4. Cost and side effects are bounded before a run starts.
5. Application-specific risk remains expressible without forking the engine.
6. Public schemas are versioned and migratable.

## What ships today (0.28.0)

The current release is beta. It provides artifact scanning, controlled endpoint and MCP
probing with repeated trials, recorded-trace analysis, regression comparison, policy and
baseline gates, extension APIs with scaffolding for a new pack, and an optional
authenticated PostgreSQL-backed collector; a judge-graded rate is corrected for the
judge's measured error when a matching calibration exists, and otherwise the report says
so. See [FEATURES.md](FEATURES.md) for the concise overview and
[Product status](docs/product-status.md) for limitations.

## Now: repeatable application assurance

Target locators are complete since 0.24.0 and declarative fixtures since 0.25.0,
and one command now writes an installable pack whose rules already grade their own
finding, clean, and inconclusive samples. The remaining milestone turns a
repeatable extension into measurement a team can compare and operate. The order below reflects the
[0.23 repository and market audit](docs/design/audit-0.23-market.md): author
workflow and honest measurement come before additional output destinations. The
[0.25 audit](docs/design/audit-0.25-market.md) re-read the standards and the
comparable projects a month later and moved no row. The
[0.26 measurement audit](docs/design/audit-0.26-measurement.md) widened the suite
and diff rows and added re-gradable evidence: a clean result that rests on one trial
per prompt, graded by a judge whose error was never measured, is not yet a measurement.
Suites, versioned datasets and assessors, with repeated trials and judge-error
correction, have shipped; [FEATURES.md](FEATURES.md) describes them.

| Order | Deliverable | Done when |
|---:|---|---|
| 1 | Paired statistical diff | comparison refuses unequal or undersized samples and unequal trials, prints the smallest effect its sample can detect, adjusts for several gated suites, and gates only on a declared minimum effect |
| 2 | Re-gradable evidence | an opted-in run keeps its redacted exchanges, and `guardana run regrade` grades them with a new assessor without target traffic |
| 3 | Renderer and reporter plugins | outputs are discoverable entry points and every output remains behind the common redaction boundary |
| 4 | Provider conformance matrix | documented endpoint support is backed by repeatable capability tests |
| 5 | Assessments in the collector | trends are keyed by system, deployment, dataset, and assessor version; findings and quality measurements stay separate |

Design inputs exist for everything shipped so far and for rows 1 to 3:

- [target locators](docs/design/target-locators.md)
- [declarative fixtures](docs/design/declarative-fixtures.md)
- [pack scaffolding](docs/design/pack-scaffolding.md)
- [output plugins](docs/design/output-plugins.md)
- [extension author tooling](docs/design/extension-author-tooling.md)
- [quality suites](docs/design/quality-suites.md)
- [paired regression statistics](docs/design/paired-regression-statistics.md)
- [repeated trials](docs/design/repeated-trials.md)
- [judge error in a measured rate](docs/design/judge-error-correction.md)
- [re-grading stored exchanges](docs/design/regrading-stored-exchanges.md)

Live OTLP intake is not planned: supervising agents in production is Guardana
Control's ([Guardana and Guardana Control](docs/design/guardana-and-control.md)).
Reading an exported recording stays, as an explicit supported subset of the
OpenTelemetry GenAI conventions behind an adapter, never as a persisted Guardana
schema.

### Milestone exit criteria

- A third-party target, rule, evaluator, renderer, and reporter are usable without
  modifying Guardana; target locators satisfy the target part from 0.24.0, and
  `guardana new-pack` scaffolds the rest.
- `guardana diff` can say better, worse, unchanged, or incomparable with an
  auditable statistical reason.
- The collector can plot measurements without turning missing samples into zero.

## Next: continuous re-verification

Keep verifying after release without watching production. Intake of live agent
traffic, supervision, and alerts on production runs belong to Guardana Control;
Guardana keeps what it controls: the requests it sends and the files it is handed
([Guardana and Guardana Control](docs/design/guardana-and-control.md)).

1. Continuous rules over synthetic runs, alerting through a confidence sequence
   rather than a fixed level on every look
   ([anytime-valid monitoring](docs/design/anytime-valid-monitoring.md)).
2. Grading an exported sample offline: a recording or a sample of answers, exported
   by the team, becomes a versioned dataset a suite grades, with redaction before
   anything is stored. OpenTelemetry GenAI input stays an explicit supported subset
   behind an adapter.
3. Prometheus and webhook outputs for Guardana's own results, through the reporter
   seam.
4. Retention, deletion, and audit behavior proven under the new data volume.

This lane starts as soon as suite and statistical shapes are stable; it does not
wait for every provider-matrix entry.

Exit criteria: every alert names its sample, its deployment revision, and the rule
that made it an alert; a sample that cannot be graded is reported as unverified,
never as clean; raw sensitive payloads are not retained by default.

## Then: self-hosted platform fit

- Helm deployment with tested upgrade, rollback, backup, and restore.
- OIDC/SSO and role-based access for human users.
- Live RAG targets with safe fixtures and explicit data boundaries.
- Central distribution of signed, versioned gate policies and profiles.
- Integrations through output plugins rather than product-specific engine code.

## 1.0: compatibility, not a feature count

Guardana reaches 1.0 when external authors can rely on it:

- the extension API and package manifest are frozen with a deprecation policy;
- schemas have published compatibility guarantees and migration tests;
- a standalone conformance kit covers targets, rules, evaluators, and outputs;
- two release candidates ship without an unplanned public API change;
- security and recovery runbooks are exercised, not merely documented.

## Parallel contributor lane

New artifact formats, deterministic rules, framework adapters, and taxonomy
updates may proceed in parallel when they do not delay the ordered milestone.
Prefer extension packs when a feature adds a large dependency, a niche corpus, or
an experimental evaluator.

One taxonomy update remains open: the MITRE ATLAS catalogue records a data-format
version rather than the content release from which its entries were transcribed.

Stateful tool doubles are open in this lane too. Agent rules grade tool calls
today; a double that keeps state would let a rule assert on what an agent left
behind, and report utility under attack beside attack success.

## Researched after the foundations

- probing multi-agent protocols and delegated identity (enforcing delegation at run
  time is Guardana Control's);
- multimodal attack carriers;
- adaptive attack generation inside a strict sandbox;
- reusable attack techniques composed with rules
  ([design](docs/design/attack-techniques.md));
- broader multilingual and domain-specific corpora.

These need measured evaluation quality and bounded execution first. They are not
shortcuts around the current milestone. Repeated trials and judge-error
correction are that measurement: sampling many transformed attacks is trials over
techniques, and an adaptive attacker is only as honest as the judge that scores
it.

## Non-goals

Guardana is not planned to become:

- an inline firewall, WAF, or guardrail proxy;
- a supervisor of agents in production: live intake, deviation alerts, and
  stopping an agent are [Guardana Control](https://github.com/guardana/control)'s;
- a general SAST, CVE, secret, or network-discovery scanner;
- a second trace store competing with observability platforms;
- a compliance certification or legal-advice engine;
- a marketplace of unverified prompts;
- an autonomous production attacker.

## Release gate for roadmap work

Every increment needs tests, user documentation, explicit exit behavior, redacted
evidence, and a changelog entry. The full repository gate in
[CONTRIBUTING.md](CONTRIBUTING.md) must pass. A feature that cannot distinguish
"safe" from "not measured" is incomplete.

## Changing the order

Open an issue or design document with the user problem, evidence, affected exit
criterion, dependencies, and what moves down. New work is not prioritized by
adding more prose to this file.
