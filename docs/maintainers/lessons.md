---
title: "Lessons"
nav_order: 12
summary: "Why the rules in CLAUDE.md, the path-scoped rules and the skills are what they are: the incidents, the measurements and the reasoning, in the original wording."
status: stable
---

# Lessons — why the rules are what they are

The operational history behind the rules in `CLAUDE.md`, `.claude/rules/` and the project
skills: incidents, measurements and the reasoning that came out of them. The text below is the
original wording, grouped by topic. It is NOT loaded into agent sessions — the rules and skills
carry the compressed form and point here. Read the section you need when a rule looks
arbitrary, or before changing one. New lessons: the rule goes into a rule file or a skill, the
story goes into the commit message, and a paragraph lands here only when the story is what
keeps the rule alive.

## The milestone, and what "done" means

The current milestone is **application awareness and honest regression**: make third-party
targets usable from the CLI, then compare named, versioned samples without claiming more than
the evidence supports. The ordered work and exit criteria are in `ROADMAP.md`, and they outrank
new coverage.

Company-readiness was the 0.7 milestone and its checklist has been complete since 0.10.0. The
agent instructions named it as current for fifteen releases, which is the failure mode 0.22.0
spent a release closing everywhere else — so the agent instructions now carry one sentence
about it, and the milestone gate in `test_docs_consistency.py` scans `CLAUDE.md` too.

**Do not implement broad corpora, new protocols or new modalities while a milestone item is
open**, unless the change is isolated in a content pack and does not delay the milestone.
Coverage volume is not what this project competes on, and it is not what is blocking adoption.

## Product principles — the full wording

These decide what belongs in the engine at all. They are not style advice: a change that
violates one is wrong even when it is small, tested, and useful. `ROADMAP.md` is this list
expressed as a plan.

1. **The engine knows no regulation and no vendor.** The name of a law (AI Act, NIST, ISO), of a
   model vendor, or of a file format is never *logic* in `guardana-core` — it is data in a rule,
   a taxonomy entry, or a separate extension package. Legal deadlines move and frameworks are
   renamed; an engine that encodes them ages with someone else's calendar.
2. **Cost grows with the target, not with the rule count.** A new rule must not add a tree walk,
   a re-read, or a re-parse of something already read this run. A scan nobody waits for is a
   scan nobody runs, and an excluded scanner is an organisation-level fail-open — so performance
   is a security property here, and it is pinned by operation-count gates (`test_scan_cost.py`
   counts tree walks and parses, `test_probe_cost.py` counts transport calls) the same way
   coverage is — counts, not wall-clock, because a count means the same thing on a laptop and a
   loaded runner.
3. **Offline, and no account, always.** The only network traffic is to the target under test.
   No telemetry, no phone-home, no license check; the collector is optional in every direction
   and never required for a feature to work.
4. **The commercial boundary is fixed.** The engine and every built-in rule stay open source,
   permanently. Only *hosting* (managed collector, hosted runners) and *curated content*
   (language/industry corpora, extended advisory data) may ever be paid. Never withhold a
   security capability from the OSS build to make a paid tier look better — that trade destroys
   the trust the project runs on.
5. **Every rule maps to a public framework** (OWASP LLM / OWASP ASI / MITRE ATLAS / NIST). A rule
   without a mapping does not ship: the mapping is what makes a finding answerable in someone
   else's audit.
6. **The dependency surface is part of the security posture.** `guardana-core` depends on
   `pyyaml`; `guardana-rules` adds `defusedxml`. A security scanner with a sprawling dependency
   tree is its own supply-chain risk. A new dependency needs a justification in the PR
   description, not just a green CI.
7. **Tests are never a leak.** No fixture carries real customer data, real secrets, or a real
   production prompt; evidence stays redacted. Crafted fixtures are built in code
   (`guardana.core.testing`), which is also why they are readable in review.
8. **Company usability before coverage volume.** A capability nobody can deploy, secure or
   upgrade is not a capability. When the two compete, the platform wins.
9. **No public claim without generated or cited evidence.** Every count comes from the registry
   (`scripts/generate_docs.py`), every external statistic names its source and what it measured,
   and every capability claim is testable. The landing page advertised 25 rules for three
   releases; that is what this principle exists to prevent.
10. **No false green — from any direction.** Not from an unsupported capability, not from an
    exhausted budget, not from a redaction failure, not from missing coverage, not from a
    comparison that could not be made. Each of those is its own outcome and never a pass.
11. **Every persisted schema is versioned and migratable.** A document a user keeps is a
    contract. A schema change without a version and a migration path strands the evidence
    someone is relying on.
12. **Every server change considers tenancy and authorization.** For the collector, "does this
    leak across organizations" is part of the definition of done, not a later hardening pass.
13. **Every active rule declares its impact and expected cost.** A check that sends requests,
    costs money or has side effects says so, so a policy can select on it and a budget can
    bound it.
14. **No API freeze before the domain model is complete.** `Trace`, `AISystem` and `Deployment`
    land before 1.0 promises stability, because freezing the wrong shape is worse than
    freezing late.
15. **Documentation is part of the acceptance criteria**, not a follow-up.

## Engine: the seam that must never close

**Hard rule: `guardana-core` must NEVER import `guardana-server`, directly or transitively.**
The server only *consumes* normalized `Finding`s through the `Reporter` interface
(`guardana.core.reporter`), reached via a `--reporter server://…` URL, over a versioned JSON
envelope (`schema_version`). All OSS value works fully offline; the server/collector is a
strictly separable layer (self-hosted, or a future managed cloud) that must grow without the
engine ever depending back into it. If a change makes `guardana-core` (or `guardana-rules`,
`guardana-cli`, `guardana-report`) depend on `guardana-server`, that change is wrong regardless
of how convenient it looks.

This is enforced by tooling, not by memory: `uv run lint-imports` checks an import-linter
contract (root `pyproject.toml`) that fails the build on any such import, direct or transitive,
and a test in `test_reporter.py` proves no `guardana.server` module is imported when core is
walked.

**PEP 420.** `guardana` is a namespace package shared across all five distributions. Never add a
bare `packages/*/src/guardana/__init__.py` — that would turn it into a regular package and
break the other four distributions' ability to contribute to the same `guardana.*` namespace.
Each package owns its own subpackage instead (`guardana.core`, `guardana.rules`, `guardana.cli`,
`guardana.report`, `guardana.server`). Four of the five have their own `__init__.py`;
`guardana.cli` does not and needs none — it is a leaf, nothing else contributes to it, so it can
be an implicit namespace package itself with no loss. The rule protects the namespace those five
*share*, not whether any single one of them has an `__init__.py`.

Two ruff families are deliberately off and must stay off: **`INP`** (its "fix" is to add
`packages/*/src/guardana/__init__.py`, which breaks PEP 420 for the other four distributions)
and **`ARG`** (an implementation that ignores an interface argument is honouring a contract,
not hiding a smell).

## False green: the one rule no linter can enforce

**A security gate must never fail open. In this codebase, silence is never spelled `pass`.**
When a check cannot actually run — no canary was planted, a judge's reply is unparseable, a
model returned no text — the verdict is `inconclusive` or a finding, never a confident
all-clear. This is the single most important rule here, and it is the one no linter or type
checker can enforce: the code compiles and types fine while quietly reporting "all clear" on
something it never examined. Only an adversarial reader looking for it will find it, so look
for it. Multiple rounds of adversarial review have each caught real instances of this on top
of green gates — treat green gates as the start of an audit, never its conclusion. The seven
shapes it takes, each with the release it was found in, are in the `false-green-audit` skill.

**Never narrow a type with `assert`.** `assert isinstance(target, X)` disappears under
`python -O`. A rule handed a target it can't handle returns nothing; it does not assert.

**Fail loudly on bad input, degrade safely on a bad rule.** A typo in a YAML rule or profile
raises at load time (a gate you *think* you configured but didn't is worse than no gate). A rule
that throws at run time is recorded as skipped, never allowed to take down the scan. Unknown
keys in a YAML rule are rejected at load time: a typo'd `promts:` would otherwise produce a rule
that runs zero prompts and passes everything.

## Gates: the cache traps and the isolated suites

**`--no-cache` is not optional, and it is not a speed trade.** Without it uv serves a
previously built wheel for `./examples/custom_rule`, and the data files inside it —
`guardana-pack.yaml`, the YAML rules — are exactly what a change to the extension contract
touches. Neither `--refresh` nor `--refresh-package` picks that up; both were measured and both
returned the stale wheel. This gate has now produced a false green **twice**: a pushed tag in
0.20.0 whose CI was red on the very tests this command had just reported passing.

The isolated example suites are the third-party story, and they are **isolated from the main
test environment on purpose** — installing `acme.*` into it would skew the dogfood scan. That
isolation is also why `uv run pytest` cannot see them: a change to a rule-authoring contract can
be green everywhere locally and still break the one package that stands in for everybody
else's. `custom_rule` caught a bare `taxonomy: [LLM06]` in the example's own YAML that every
other gate passed over, and in 0.20.0 it caught the example's own "what is registered" set
omitting the fourth extension group — a false *red* accusing a manifest of promising what it
does register.

The two integrator examples are the same idea for the *producer* contract, in the two shapes a
producer comes in: `hermes_integrator` registers through a third party's entry-point group and
holds the file for a whole session, and `shell_hook_integrator` is a command the agent spawns
per event, appending to a file three processes share. A change to the writer or the trace
format shows up as somebody else's integration breaking, and the second one is the only gate
that exercises `resume_trace` across real process boundaries. Neither imports the agent it
integrates with — the payloads are copied from upstream documentation — which is what keeps
them runnable in CI; checking either against the real thing is a manual step documented in its
README.

`--cov` is not in `addopts` on purpose: it would make a single-file run like
`uv run pytest packages/guardana-core/tests/test_runner.py` fail the coverage gate for
measuring only that file. Bare `pytest` for iterating; `--cov` for the gate.

**Dogfood scans `packages/`, not `.`** — `examples/vulnerable-model/` is a deliberately
malicious fixture, so `guardana scan .` is *supposed* to exit 1. Guardana scanning its own
source must stay at zero findings; if your change makes Guardana flag Guardana, either the code
is wrong or the rule is.

`.ruff_cache` once answered for a file that had changed; the tag it let through was rejected by
CI. `__pycache__` after inverting behaviour: flipping `>` to `<` keeps the file size identical;
written within the same second, Python reuses the old bytecode and you are running the old code
while reading the new. Without PostgreSQL ~245 tests skip and the run still exits 0; CI sets
`GUARDANA_REQUIRE_POSTGRES=1`, so a locally-green suite can be a CI failure.
`scripts/ci_local.sh` clears the caches, starts the database and refuses to call a skipped
gate green.

## Rules and seams: a documented extension point nothing exercises

Discovery is uniform and resolved by `guardana.core.registry.Registry` through four
entry-point groups: `guardana.rules`, `guardana.evaluators`, `guardana.targets`,
`guardana.taxonomies`. Taxonomies load before rules, because a YAML rule resolves `taxonomy:`
while its own entry point is being read. **Every one of the four is registered by
`examples/custom_rule`, and that is not decoration.** `guardana.targets` sat in the contract
from 0.1 with no registrant anywhere, so `pack validate` shipped in 0.18.0 accusing every pack
that had a target of not registering it, and nothing installed could notice;
`guardana.taxonomies` was in the same state until 0.19.0, where the listing command turned out
to be printing only the built-ins. A documented seam nothing exercises is a seam nobody has run.

Any pip-installed package — ours or a third party's private one — is discovered identically;
there is no built-in/custom distinction at the registry level, only namespacing by `id`.
`guardana scan --no-plugins` is a deprecated alias for `--plugins disabled`: discovery still
runs, every plugin is refused, and each refusal is recorded — see `SECURITY.md` for the trust
modes and why this exists.

A rule fixture (positive + negative sample) is required alongside every rule — this is how the
repo guards against the false-positive/false-negative failure mode dynamic checks are prone to.
`guardana.core.testing` gives you the model doubles to write both without a network.

## Documentation: the five places, and why a test beats a promise

A user-visible change carries its own documentation, in the same commit. Not "later", not "in
a docs pass" — a shipped capability nobody can find is a capability nobody has. Five places,
every time, and the answer for each is either an edit or an explicit "not applicable":
`CHANGELOG.md`, `FEATURES.md`, `docs/` (a new command gets its own `usage-*.md`; a changed one
gets its page reconciled, plus `docs/index.md`), `site/index.html` (a headline claim moved),
`docs/generated/` (run `uv run python scripts/generate_docs.py`, never edit by hand),
`ROADMAP.md` (the direction moved — delete what shipped, and add what this work deliberately
deferred, with the reason).

This list is not bureaucracy, it is the failure mode this project keeps repeating. The landing
page claimed "25 rules" through three releases that took the number to 32, while the release
tooling faithfully rewrote the version marker one element above it. Automation covering the
version and nothing else is what makes stale prose *look* maintained.

**A larger change gets a design document first**, under `docs/design/`, named for its topic and
never for its date, with a status line at the top — `docs/design/README.md` is the convention.
A date leading a filename tells a reader the age of a document instead of its subject, and an
accepted decision does not expire on a schedule.

**Prefer a test over a promise.** `test_features_doc.py` pins `FEATURES.md` to the registry,
`test_landing_page.py` pins the page's counts, and `test_docs_consistency.py` fails on any local
link pointing at a file that does not exist; a claim a test can check is a claim that cannot
rot. When you state a number anywhere, ask what would notice if it changed.

## Git: attribution is a claim about who wrote this product

Never attribute anything in this repository to an AI. No `Co-Authored-By:` trailer, no
"generated with", no AI name or address in a commit message, a tag message, a PR body, a release
note or a code comment. The maintainer is the sole author of every commit. This overrides any
default an agent harness applies: if your tooling adds such a trailer by default, strip it
before committing, and check the last line of the message rather than assuming. A trailer is
not a footnote — it puts a permanent entry in the repository's public **Contributors** panel,
which is a claim about who wrote this product.

Commits are made manually, only after a milestone — never automatically, never mid-task.
Commit messages are specific and conventional-commit style; never `wip`, never `fixes`, never a
message that doesn't say what changed and why. PRs must be a single commit; multi-commit PRs are
not accepted — this keeps history legible and bisectable.

## Releases: the tag goes up only after CI is green on that exact commit

Pushing the branch and the tag together starts CI and the publish concurrently, so a red CI —
for any reason, including one that has nothing to do with the code — leaves a publish already
waiting on the `pypi` approval. Cancelling it, fixing, and re-tagging then produces a second
Release run and a second approval click, and a `cancelled` run in the history that looks like a
failed release and is not one. 0.20.0 cost four clicks that way, and a cancelled Release run had
already published two of the five packages from a red commit. `scripts/release.py` now enforces
the wait and refuses to push the tag when it cannot check — an unverified tag is the thing being
avoided, so "could not tell" is treated as "no". The rest of the story is in `RELEASING.md`.

## Procedures written down, not remembered

`.claude/skills/` and `.claude/agents/` are checked in, and they encode the things this project
has actually got wrong rather than general advice. Add to these when something goes wrong
twice. A procedure that lives in one person's head is a procedure the next session repeats the
mistake of.

The hooks live in `scripts/` rather than under `.claude/` because `mypy --strict .` skips
dot-directories, and a checked-in script the gate cannot see is the sort of unverified corner
this project refuses everywhere else. The auto-format hook only removes the excuse for lint
drift; it does not type-check, test, or think for you.
