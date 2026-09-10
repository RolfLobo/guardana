---
title: "The 0.23 repository and market audit"
nav_order: 26
summary: "what the released 0.23.0 code, roadmap and documentation say, what current agent-security demand adds, and why target locators stay first while repeatable measurement moves ahead of output plugins"
status: accepted
---

# The 0.23 repository and market audit

**Status:** accepted · **Written:** 2026-09-09 · **Subject:** released 0.23.0 at
`946f2ef`, with the unreleased repository cleanup at `0b05d56`

## Decision in one page

Keep target locators first and ship them in 0.24.0. They close a real product
gap: Guardana has discovered custom targets since 0.1 but no CLI command could
build one. Current buyers also operate heterogeneous agent stacks, while the
closest open-source products treat custom targets as a basic integration
surface, not an advanced feature.[^csa-enterprise][^pyrit][^promptfoo][^garak]

Change the order after that:

1. YAML fixtures for scenario and trajectory rules;
2. `guardana new-pack`;
3. suites, versioned datasets, and assessors;
4. paired statistical diff;
5. renderer and reporter plugins;
6. provider conformance matrix;
7. assessments in the collector.

This moves repeatability and statistically honest regression ahead of adding
more output destinations. Begin the OpenTelemetry compatibility and production
intake work after the suite and comparison shapes settle, in parallel with the
later extension work. Do not make today's developmental GenAI semantic
conventions a persisted Guardana schema.[^otel-agent][^otel-releases]

Do not move live RAG to the next release. It remains valuable, but it is one
target category. The stronger cross-market need is to connect the systems teams
already have, know which agents and permissions exist, repeat evaluations, and
retain evidence over time.[^csa-autonomous][^csa-governance][^nist-ai-rmf]

## Scope and method

The repository audit read the engine, CLI, rule pack, collector, example packs,
release automation, root documentation, task guides, generated references, and
accepted/proposed designs. Claims about behavior were checked with static
analysis, strict typing, targeted tests, the full repository gate, and isolated
installation tests. The release gate results belong in the 0.24.0 changelog and
release record, not in this time-stable audit.

The market review used primary or first-party sources: NIST, the EU AI Act,
OWASP, OpenTelemetry, official competitor documentation, and two Cloud Security
Alliance surveys. The CSA surveys were sponsored by security vendors; their
percentages are useful directional signals, not neutral market sizing. No
customer interviews were conducted.

Public repository evidence is thin: the project had no open public issues at the
time of review.[^guardana-issues] That means this order is a researched product
hypothesis, not a claim that Guardana users voted for it. The validation plan
below is part of the decision for that reason.

## Repository audit

### What is strong

| Area | Evidence in the repository | Assessment |
|---|---|---|
| Verdict integrity | findings, inconclusive results, errors, skips, coverage shortfalls, and assessments remain separate; default gates do not translate missing evidence into a pass | a credible differentiator, and the principle every new feature should preserve |
| Bounded execution | planning, request/token/duration ceilings, safety levels, explicit destructive permission, and offline artifact scanning | aligned with enterprise requirements for controlled testing rather than autonomous attack execution |
| Evidence model | versioned run, trace, baseline, lock, contract, calibration, and collector documents with migration/round-trip gates | unusually mature for a beta CLI; suitable foundation for audit evidence |
| Extensibility | entry points for rules, evaluators, targets, and taxonomies; transactional discovery; plugin trust; pack validation and locking; conformance helpers | strong Python embedding surface, but incomplete user workflow before 0.24.0 |
| Verification discipline | 264 test modules, aggregate and per-area coverage floors, strict typing, import boundaries, CodeQL, dogfood scanning, generated-doc checks, three isolated examples, and a clean-install gate | release engineering is a product strength, not only a maintainer convenience |
| Deployment boundary | engine remains out of the request path; collector is optional and separated by a data-only protocol | coherent with the stated non-goal of becoming an inline firewall or APM |

### Findings and action

| Priority | Finding | Evidence and risk | Action |
|---:|---|---|---|
| P0 | A discovered custom target cannot be selected by the CLI | `guardana.targets`, manifests, locks, and conformance tests exist, but nine target-building command paths used only literal built-ins. A documented extension could work from Python and remain unusable in normal CI | ship target locators in 0.24.0 across scan, baseline, plan, probe, monitor, inspection, and trace analysis; refuse unknown/conflicting schemes and target-kind mismatches |
| P0 | Canary rules need a construction contract on custom endpoints | grading a canary without planting it is a false pass; constructing one target per rule can multiply the budget | add `SystemPromptPlanter`; skip canary checks honestly when absent; require planted views to share usage and budget state |
| P1 | The roadmap sequence optimized extension breadth before repeatable outcomes | renderer/reporter plugins were ahead of fixtures, author scaffolding, suites, and paired statistics | move fixtures, scaffolding, suites, and paired diff ahead of output plugins |
| P1 | The public direction contradicted itself | `README.md` called live RAG and sink-aware output “next”; `ROADMAP.md` called target locators next | make `ROADMAP.md` authoritative and make the README summarize it rather than maintain a second order |
| P1 | Several old design records still said “ships in the next release” | implemented MCP, taxonomy, adapter, and trace designs looked unreleased years of milestones later | replace those stale status lines with the release that actually contains each decision |
| P1 | Continuous evidence is deferred too coarsely | `monitor` re-runs synthetic probes and the collector stores findings, but neither consumes bounded production samples or trends assessments | start a compatibility layer and intake spike once suite/paired shapes settle; keep the full intake behind explicit backpressure, redaction, retention, and deletion gates |
| P2 | Product prioritization has no direct user-evidence loop | zero open issues is not proof of zero unmet needs; the roadmap says evidence changes order but defines no collection cadence | publish the hypotheses and metrics below; recruit design partners before promoting target-specific work |

## Market needs

### 1. Heterogeneous agents need adapters and inventory first

The 2026 CSA enterprise survey reports that 87% of responding organizations use
two or more agent platforms, while 54% report unsanctioned agent use. Only 15%
say almost all agents have an assigned owner.[^csa-enterprise] A separate CSA
survey reports 40% already running autonomous agents in production and only 21%
having real-time agent registry or inventory capability.[^csa-autonomous]

The implication for Guardana is not to embed every vendor. It is to make a
private gateway, artifact store, or trace export a first-class target selected
by the same CLI and governed by the same plugin trust policy. Target locators do
that while preserving Guardana's small core.

### 2. Identity, permissions, tool use, and ownership are the urgent risk surface

In the enterprise survey, 53% report agents exceeding intended permissions at
least occasionally, 47% report an agent-related security incident, and 58% say
detection and response take five hours or longer.[^csa-enterprise] OWASP's 2026
agentic guidance emphasizes goal hijacking, tool misuse, identity and privilege
abuse, supply-chain exposure, and unexpected code execution.[^owasp-agentic]

Guardana already has meaningful checks and trace dimensions in this area. The
gap is operational: run those checks against each organization's system, prove
which capability was actually available, and make the result repeatable. That
supports locators, fixtures, conformance, suites, and continuous evidence before
another broad category of built-in checks.

### 3. Continuous, attributable evidence is becoming a requirement

NIST's AI RMF materials call for testing before deployment and regularly during
operation, using objective and repeatable TEVV, documented metrics, uncertainty,
and formal reporting.[^nist-ai-rmf][^nist-core] Article 72 of the EU AI Act
requires active, systematic post-market collection, documentation, and analysis
for high-risk systems; the Act also establishes logging obligations for relevant
deployers.[^eu-ai-act][^eu-summary]

That does not justify turning Guardana into an APM. It supports the roadmap's
existing out-of-path model: named systems and deployments, bounded samples,
versioned datasets and assessors, paired comparisons, retention rules, and
auditability. The collector should receive assessments only after their
denominator and comparability keys are stable.

### 4. The interoperability standard is useful and still moving

OpenTelemetry defines experimental GenAI agent spans for agent creation,
invocation, workflow planning, and tool execution. The specification marks this
work as developmental, and GenAI conventions recently moved into a dedicated
repository.[^otel-agent][^otel-releases]

Guardana should consume a conservative subset behind a versioned adapter and
preserve unknown attributes, not copy the current attribute set into its own
public schema. This is why intake work is accelerated but the persisted suite
and comparison model is settled first.

### 5. Custom targets and repeatable evaluations are competitive table stakes

| Product | First-party documented strength | Consequence for Guardana |
|---|---|---|
| Microsoft PyRIT | custom targets, scenarios, datasets, multi-turn orchestration, database storage, and a UI[^pyrit] | target integration and dataset workflow must be easy; Guardana should differentiate on bounded execution and evidence integrity |
| Promptfoo | custom HTTP/Python/JavaScript targets, RAG and agent workflows, configurable plugins/strategies, and CI evaluation[^promptfoo][^promptfoo-config] | a custom target that requires user-written orchestration is below the market baseline |
| NVIDIA garak | CLI-selected generator targets plus probes, detectors, evaluators, and harness plugins[^garak] | extensibility is expected at the command line, not only from a library API |
| Giskard | agent evaluation/red teaming and a continuous enterprise collaboration layer[^giskard] | Guardana's collector needs repeatable measurements and ownership, not only finding storage |

The response should not be feature parity. Guardana's defensible position is:
out of the request path, explicit budgets and side effects, honest unknowns,
versioned evidence, and a small extension surface that private systems can use.

## Revised sequencing and dependencies

```text
target locators (0.24)
        |
        v
scenario/trajectory fixtures --> new-pack
        |
        v
versioned suites + assessors --> paired statistical diff
        |                              |
        +--------------+---------------+
                       v
          collector assessment trends

output plugins -----------------------> Prometheus/webhooks
provider conformance -----------------> trusted target coverage
stable measurement shapes ------------> bounded OTLP intake
```

The sequence is not a promise that independent work must wait. Provider
conformance and the OpenTelemetry compatibility spike may proceed in parallel
after the target contract ships. The dependency that must not be bypassed is
persisting or alerting on quality trends before dataset, assessor, denominator,
uncertainty, and paired-sample semantics are stable.

## What moved, and what did not

- **Stayed first:** target locators, because they unblock private systems and
  match a multi-platform market.
- **Moved up:** complete YAML fixtures and `new-pack`, because an extension that
  is possible but expensive to prove will not create an ecosystem.
- **Moved up:** suites and paired statistics, because continuous evaluation
  without a denominator and uncertainty is dashboard theater.
- **Moved down:** renderer/reporter plugins. They matter for integrations, but
  the current JSON, SARIF, JUnit, human, and collector outputs are enough to
  prove the measurement model first.
- **Accelerated in parallel:** provider conformance and the production-intake
  compatibility spike.
- **Stayed later:** full OTLP intake, collector quality trends, Helm/RBAC, and
  live RAG, each behind its named dependency.
- **Still rejected:** inline enforcement, a universal risk score, unbounded
  autonomous attack generation, and a second trace store.

## Validation plan

The next order should change again if evidence disproves it. For the first 60
days after 0.24.0, collect these product signals without telemetry in the CLI:

| Hypothesis | Observable signal | Decision threshold |
|---|---|---|
| teams need non-built-in targets | design-partner target implementations and support discussions naming a private gateway/store/export | keep conformance work high if at least three independent systems reach a working locator; otherwise interview the failed adopters before adding schemes |
| author tooling is the adoption bottleneck | elapsed time from an empty directory to an isolated, passing pack; points where authors leave the guide | `new-pack` should make a conforming pack runnable in under 15 minutes without copying repository internals |
| suites answer a more frequent question than another output plugin | design partners able to name a dataset, assessor, minimum sample, and decision they make from the result | build suites before output plugins when at least three partners can provide real cases and thresholds |
| continuous evidence is urgent but must remain out of path | requests for production sampling that include volume, retention, redaction, and acceptable loss/backpressure behavior | start implementation only with two concrete operating envelopes and a written overload test |

Also measure product integrity on every release: zero unknown target schemes that
are silently ignored; zero canary rules graded without a planted marker; all
custom-target runs recording target identity and usage as known or explicitly
unknown; and no regression comparison crossing dataset or assessor versions.

## Sources

[^csa-enterprise]: Cloud Security Alliance, [*Enterprise AI Security Starts with AI Agents*](https://cloudsecurityalliance.org/artifacts/enterprise-ai-security-starts-with-ai-agents), 15 April 2026. Survey sponsored by Zenity; used as directional adoption, ownership, permission, and incident evidence. Accessed 9 September 2026.
[^csa-autonomous]: Cloud Security Alliance, [*Securing Autonomous AI Agents*](https://cloudsecurityalliance.org/artifacts/securing-autonomous-ai-agents), 4 February 2026. Used for production adoption, IAM confidence, inventory, and budget signals. Accessed 9 September 2026.
[^csa-governance]: Cloud Security Alliance, [*The State of AI Security and Governance*](https://cloudsecurityalliance.org/artifacts/the-state-of-ai-security-and-governance), December 2025. Used for governance maturity, multi-model strategy, and data-exposure priorities. Accessed 9 September 2026.
[^nist-ai-rmf]: NIST, [*AI Risk Management Framework*](https://www.nist.gov/itl/ai-risk-management-framework). Used for the Govern/Map/Measure/Manage risk model and lifecycle testing context. Accessed 9 September 2026.
[^nist-core]: NIST AI Resource Center, [*AI RMF Core*](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/). Used for repeatable TEVV, metrics, uncertainty, monitoring, and reporting expectations. Accessed 9 September 2026.
[^eu-ai-act]: European Union, [Regulation (EU) 2024/1689, Article 72](https://eur-lex.europa.eu/eli/reg/2024/1689/oj?locale=en). Used for the post-market monitoring obligation. Accessed 9 September 2026.
[^eu-summary]: European Commission, [*AI Act regulatory framework*](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai). Used for the Commission's current implementation overview, including monitoring, logging, and human oversight. Accessed 9 September 2026.
[^owasp-agentic]: OWASP GenAI Security Project, [*OWASP Top 10 for Agentic Applications*](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/), 9 December 2025, and [2026 project release announcement](https://genai.owasp.org/2026/09/01/owasp-genai-security-project-unveils-2026-top-10-for-llm-applications-new-agent-control-standard-and-sponsors-as-community-tops-30000-members/), 1 September 2026. Used for the current agentic threat categories and ecosystem direction. Accessed 9 September 2026.
[^otel-agent]: OpenTelemetry, [*Semantic conventions for GenAI agent spans*](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md). Used for the developmental agent/workflow/tool span model. Accessed 9 September 2026.
[^otel-releases]: OpenTelemetry, [semantic-conventions releases](https://github.com/open-telemetry/semantic-conventions/releases). Used to verify the current release stream and GenAI repository transition. Accessed 9 September 2026.
[^pyrit]: Microsoft, [PyRIT documentation](https://microsoft.github.io/PyRIT/). Used for documented targets, scenarios, datasets, orchestration, storage, and UI capabilities. Accessed 9 September 2026.
[^promptfoo]: Promptfoo, [red-team quickstart](https://www.promptfoo.dev/docs/red-team/quickstart/) and [custom plugins](https://www.promptfoo.dev/docs/red-team/plugins/custom/). Used for custom target and CI evaluation capabilities. Accessed 9 September 2026.
[^promptfoo-config]: Promptfoo, [red-team configuration](https://www.promptfoo.dev/docs/red-team/configuration/). Used for target, plugin, strategy, context, language, and framework configuration. Accessed 9 September 2026.
[^garak]: NVIDIA, [garak repository and documentation](https://github.com/NVIDIA/garak). Used for its CLI target and plugin taxonomy. Accessed 9 September 2026.
[^giskard]: Giskard, [Giskard documentation](https://docs.giskard.ai/). Used for documented agent evaluation, red teaming, collaboration, and continuous enterprise workflows. Accessed 9 September 2026.
[^guardana-issues]: Guardana, [public issue tracker](https://github.com/guardana/guardana/issues). No open public issues in the review snapshot; used only to state the evidence limitation. Accessed 9 September 2026.
