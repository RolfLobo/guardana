---
title: "The 0.25 roadmap and market audit"
nav_order: 27
summary: "whether the ordered milestone still follows from evidence after target locators and declarative fixtures shipped, what the 0.23 validation plan actually produced, and why the order stays while the plan that was supposed to test it is replaced"
status: accepted
---

# The 0.25 roadmap and market audit

**Status:** accepted · **Written:** 2026-09-20 · **Subject:** released 0.25.0, and the
sequencing decided in [the 0.23 audit](audit-0.23-market.md)

## Decision in one page

Keep the "Now" order exactly as it stands: `guardana new-pack`, then suites with versioned
datasets and assessors, then paired statistical diff, then renderer and reporter plugins, then
the provider conformance matrix, then assessments in the collector.

Nothing found in this pass moves a row. The standards that changed were already carried in the
taxonomy catalogues before this audit began. The standard that did not change — the
OpenTelemetry GenAI conventions — is the one the roadmap already defers for exactly that
reason, and it is still developmental in every span and every attribute. The competitors who
moved spent the month on provider surface and on datasets; neither of the two capabilities
this milestone is built around, a scaffolding command and a paired statistical comparison,
appeared anywhere.

Change two things that are not the order.

First, **the validation plan from the 0.23 audit cannot be run and must be replaced.** Its
market half asked for three design partners and three independent target implementations. The
project has no public issues, no discussions and one fork. That is not a refutation of the
order; it is a plan written for a project with a feedback channel, applied to one that has
visitors and no content. The replacement below measures the same hypotheses against numbers
the repository computes about itself, which keeps the offline promise intact rather than
trading it for telemetry.

Second, **row 1 is the only row with no design document, and `ROADMAP.md` currently says
otherwise.** It lists `extension-author-tooling.md` as row 1's design input; that document is
marked implemented in 0.18.0, it designs the manifest, the lock file and `rule test`, and it
does not describe `new-pack`. A command is a protected contract, so `new-pack` gets its own
short design document before its code.

## Scope and method

This audit asks one question: does the "Now" order still follow from evidence now that 0.24.0
shipped target locators and 0.25.0 shipped declarative fixtures for every rule shape?

Evidence came from primary sources only, each read on 2026-09-20. Release facts were taken
from the GitHub releases API rather than from a rendered page or a summary, after a first pass
misdated two releases by a year. Repository claims were verified by reading the code and
naming the line. Where a fact could not be confirmed on a page it is marked unverified and
left unused.

**No second opinion was obtained.** The two brokered text engines were both exhausted on the
day of writing, reproduced directly: GPT reports a usage limit resetting 2026-09-22, Gemini
reports `RESOURCE_EXHAUSTED` resetting around 2026-09-24. The reasoning here is therefore
single-source. That is a gap in the method, recorded rather than rounded up.

## What the 0.23 validation plan produced

The 0.23 audit committed to four hypotheses with decision thresholds, to be observed in the 60
days after 0.24.0, without telemetry in the CLI.

| Hypothesis | Threshold it set | What arrived |
|---|---|---|
| teams need non-built-in targets | three independent systems reach a working locator | nothing: no issues in any state, no discussions, one fork |
| author tooling is the adoption bottleneck | a conforming pack runnable in under 15 minutes without copying repository internals | no external signal; the in-repo measurement stands on its own |
| suites beat another output plugin | three partners naming a dataset, assessor, minimum sample and decision | nothing: no partners |
| continuous evidence is urgent but out of path | two operating envelopes and a written overload test | nothing |

The reason is worth stating precisely, because it is not disinterest. In the fourteen days to
2026-09-20 the repository's traffic records four unique visitors on `/discussions`, three on
`/issues` and two on `/fork`, and none of them opened anything. Clone traffic runs an order of
magnitude above page views, which is the shape of automation rather than of readers. Package
downloads sit in the same band for all five distributions. These are numbers about reach, not
about use, and treating them as adoption would be the reporting failure this project exists to
prevent.

One hypothesis is measurable without anybody's help, and its answer is unambiguous. The only
working template for a third-party pack is `examples/custom_rule/`: twenty-three files and
1225 lines. The documented path to writing one is 939 lines across two pages. `guardana init`
writes a single policy file; `guardana new-rule` writes a single rule file with no tests, no
fixtures, no manifest and no entry points. "Without copying repository internals" is not
currently possible, which is the condition row 1 exists to remove.

**The product-integrity half of the same plan passed, and unlike the market half it is
checkable.** All four measures were verified in code on 2026-09-20: an unknown target scheme
raises rather than being skipped; a canary with no planted marker grades `inconclusive` with
the reason written into the verdict; a target that does not meter itself reports unknown
rather than zero; and a comparison whose assessor or dataset moved is excluded from every rate
and named in the reader's notes instead of being folded into a number.

## Standards: three confirmations and one new object

**OWASP published a new LLM edition and this repository already carries it.** The 2026 edition
is published, release date 4 August 2026.[^owasp-llm-2026] No entry was added or dropped;
seven were re-ranked, and *System Prompt Leakage* was broadened into *Hidden Context
Exposure*. The shipped catalogue matches that list entry for entry, including the relations
that say how each 2026 entry supersedes a 2025 one. No work follows.

**The agentic and MCP lists did not move.** The Top 10 for Agentic Applications remains the
edition published in December 2025.[^owasp-asi] The MCP Top 10 remains explicitly in its beta
and pilot phase,[^owasp-mcp] which is the state the shipped catalogue records, pinned as a
beta with the revision it was transcribed from.

**NIST did not move either.** AI 100-2 E2025 remains the current edition, finalized 24 March
2025.[^nist-100-2] NIST's 2026 activity relevant to a testing tool is the control-overlay
project for securing AI systems,[^nist-cosais] which produces SP 800-53 overlays rather than
an attack taxonomy a rule maps to.

**The OpenTelemetry GenAI conventions are still developmental, which is what the roadmap
assumes.** Every `gen_ai.*` attribute and every GenAI span — client, create agent, invoke
agent, and the tool-execution span an agent trace depends on — carries the literal status
`Development`.[^otel-spans][^otel-agent-spans] GenAI content left the core repository in
v1.42.0 and now lives in a dedicated repository that has cut no release and no tag, with a
changelog holding only an unreleased heading.[^otel-releases][^otel-genai-repo] Stabilisation
appears only under an unconfirmed heading of the conventions roadmap, with no date. The
roadmap's existing sentence — that full OTLP intake waits because the conventions are still
changing — is accurate as written, and the compatibility spike it permits after items 2 and 3
remains the right shape.

**The new object is not a taxonomy.** The Agent Control Standard was donated to the OWASP
GenAI Security Project and announced on 1 September 2026.[^owasp-acs] It is a wire
specification at v0.1.0: JSON-RPC hooks and versioned schemas that let a separate guardian
inspect an action and permit, deny or modify it before it happens.[^acs-repo] There is no
enumerated ACS list, so there is nothing for a rule to map to, and implementing the standard
would put Guardana in the production request path, which the non-goals forbid.

What makes it interesting is what its own issue tracker says: the wire is not authenticated,
and the default posture on failure is to proceed. A control that fails open is precisely the
defect this project names, and a deployed guardian is a system under test. That belongs in the
parallel contributor lane as a target and a rule — never as engine logic — and only after the
specification stops being a v0.1.0 with open protocol questions.

## The market since the last audit

Six comparable projects were checked against their own release histories for the month after
20 August 2026, the date the previous audit read them.

- **Giskard is the one that moved on this milestone's ground.** v3.0.0 splits the project into
  five distributions, adds composition operators over checks, exports its default registry
  generators on the public API, and adds JUnit XML export alongside a hub export
  format.[^giskard] A pluggable check registry and an output shape, in one release.
- **PyRIT changed address and grew its datasets.** The repository the previous audit cited is
  archived; the live one published v1.1.0 with several hundred in-the-wild jailbreak
  templates, a second published dataset, dataset-refresh support, new target types and
  stop-reason metadata.[^pyrit-archived][^pyrit] No pass rates or sample sizes are stated,
  which is the distinction row 2 exists to make.
- **promptfoo spent the month on provider surface**: portable HTTP and MCP configuration
  schemas, tool calls exposed in response metadata, an agents-API provider, and importable
  custom providers in another language.[^promptfoo]
- **garak added a framework mapping**, tagging existing probe results by regulatory risk
  category, and hardened its agent probe.[^garak] A mapping, which is the same move a taxonomy
  catalogue makes.
- **Two projects did not move.** One has had no release for ten months and one none for seven,
  with no commits on the default branch since.[^deepteam][^modelscan]

Two absences carry more weight than any of the releases. **Nobody shipped a paired statistical
comparison of two runs.** And **nobody shipped a command that scaffolds an authoring
package**; the closest is a registry, which is where extensions are looked up, not where they
come from. Rows 1 and 3 remain the two places this project is not following anyone.

## What moves, and what does not

- **Unchanged:** all six rows, in the order the 0.23 audit set.
- **Corrected:** the claim that design inputs exist for the first four remaining rows. Row 1
  has none, and gets one before its code.
- **Replaced:** the validation plan, below.
- **Added to the parallel lane:** an ATLAS content refresh. ATLAS publishes monthly content
  releases separately from its semantically versioned data format, and three content releases
  have landed since the version the catalogue records.[^atlas-releases] The newest alone adds
  eleven techniques, most of them agent-facing.[^atlas-2026-09] The catalogue's provenance
  field currently names the data format rather than the content release, which is the first
  thing to fix; the techniques themselves are rule-mapping work that must not delay the
  milestone.
- **Still rejected**, unchanged from the previous audit: inline enforcement, a universal risk
  score, unbounded autonomous attack generation, and a second trace store. The Agent Control
  Standard does not reopen the first of these.

## Options that were rejected

**Moving the provider conformance matrix above renderer and reporter plugins.** The active
competitor spent the month on provider surface, so parity argues for it. Rejected because that
row has no design document either, and because the five output formats it would overtake
already ship — moving it up buys parity and defers the seam a third party needs to add an
output of their own, which is named in the milestone's exit criteria.

**Moving suites above `new-pack`.** Two competitors moved on measurement, and suites are the
deepest change in the milestone. Rejected on the dependency the previous audit drew and this
one does not disturb: a suite run against somebody else's system needs a pack they can build,
and building one today means copying twenty-three files out of an example.

## A validation plan this project can actually run

The previous plan failed because its observables lived outside the repository. These live
inside it, are computed by the gate, and cost no telemetry.

| Hypothesis | Observable, and where the number comes from | Threshold |
|---|---|---|
| author tooling is the bottleneck | a gate step that scaffolds a pack into an empty directory, installs it isolated with no cache, and runs `pack validate` and `rule test` against it; the numbers are its wall-clock seconds and the count of files an author must still edit | the step passes without any file from this repository, and an author edits no more than what the step reports |
| the author path is not growing | generated counts: lines of documentation on the critical authoring path, and files in a freshly scaffolded pack | neither rises without a decision that says why |
| the catalogue stays honestly sampled | the generated count of rules that ship a full fixture set, today 11 of 51 | never falls; every rise names the shapes it covered |
| a gate never passes what it did not run | the four integrity measures above, each pinned by a test | all four hold at every release, and a new one is added whenever a release adds a way to be silent |

The market hypotheses are not abandoned; they are unmeasurable today and are marked so rather
than being answered with a number that means reach. The one honest intervention available is
to make the channel able to produce content at all — the traffic shows people arriving at the
discussion and issue pages and leaving without opening anything.

## Sources

[^owasp-llm-2026]: OWASP GenAI Security Project, [Top 10 for LLM Applications, 2026 edition source](https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/blob/main/2026/README.md), release date 4 August 2026. Read 20 September 2026.
[^owasp-asi]: OWASP GenAI Security Project, [Top 10 for Agentic Applications](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/), 9 December 2025. Read 20 September 2026.
[^owasp-mcp]: OWASP, [MCP Top 10 project page](https://owasp.org/www-project-mcp-top-10/), stating "Phase 3 – Beta Release and Pilot Testing". Read 20 September 2026.
[^owasp-acs]: OWASP GenAI Security Project, [2026 project announcement](https://genai.owasp.org/2026/09/01/owasp-genai-security-project-unveils-2026-top-10-for-llm-applications-new-agent-control-standard-and-sponsors-as-community-tops-30000-members/), 1 September 2026. Read 20 September 2026.
[^acs-repo]: [Agent Control Standard repository](https://github.com/GenAI-Security-Project/agent-control-standard), v0.1.0; used for the wire description, the unauthenticated wire and the fail-open default. Read 20 September 2026.
[^nist-100-2]: NIST, [AI 100-2 E2025, final](https://csrc.nist.gov/pubs/ai/100/2/e2025/final), 24 March 2025. Read 20 September 2026.
[^nist-cosais]: NIST, [Control Overlays for Securing AI Systems](https://csrc.nist.gov/projects/cosais). Read 20 September 2026.
[^otel-spans]: OpenTelemetry, [GenAI spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md), status `Development`. Read 20 September 2026.
[^otel-agent-spans]: OpenTelemetry, [GenAI agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md), agent and tool-execution spans status `Development`. Read 20 September 2026.
[^otel-releases]: OpenTelemetry, [semantic-conventions releases](https://github.com/open-telemetry/semantic-conventions/releases); v1.42.0 moved GenAI content out. Read 20 September 2026.
[^otel-genai-repo]: OpenTelemetry, [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai); no releases, no tags. Read 20 September 2026.
[^atlas-releases]: MITRE ATLAS, [atlas-data releases](https://github.com/mitre-atlas/atlas-data/releases); content releases v2026.07, v2026.08 and v2026.09 postdate data-format release v5.6.0. Read 20 September 2026 via the API.
[^atlas-2026-09]: MITRE ATLAS, [content release v2026.09](https://github.com/mitre-atlas/atlas-data/releases/tag/v2026.09), 15 September 2026; eleven techniques added. Read 20 September 2026.
[^giskard]: Giskard, [giskard-oss v3.0.0](https://github.com/Giskard-AI/giskard-oss/releases/tag/v3.0.0), 26 August 2026. Read 20 September 2026.
[^pyrit-archived]: Microsoft, [the archived PyRIT repository](https://github.com/Azure/PyRIT), cited by the previous audit. Read 20 September 2026.
[^pyrit]: Microsoft, [PyRIT v1.1.0](https://github.com/microsoft/PyRIT/releases/tag/v1.1.0), 4 September 2026. Read 20 September 2026.
[^promptfoo]: Promptfoo, [releases 0.122.1 through 0.123.1](https://github.com/promptfoo/promptfoo/releases), 26 August to 18 September 2026. Read 20 September 2026.
[^garak]: NVIDIA, [garak v0.17.0](https://github.com/NVIDIA/garak/releases/tag/v0.17.0), 9 September 2026. Read 20 September 2026.
[^deepteam]: Confident AI, [DeepTeam releases](https://github.com/confident-ai/deepteam/releases); latest v1.0.9, 12 November 2025. Read 20 September 2026.
[^modelscan]: Protect AI, [ModelScan releases](https://github.com/protectai/modelscan/releases); latest v0.8.8, 18 February 2026. Read 20 September 2026.
