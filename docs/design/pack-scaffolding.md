---
title: "Scaffolding a pack"
nav_order: 78
summary: "what `guardana new-pack` writes, why it writes a working pack rather than a skeleton, and the gate step that proves an author never has to copy a file out of this repository"
status: accepted
---

# Scaffolding a pack

**Status:** accepted · **Written:** 2026-09-20 · **Roadmap "Now", row 1**

## The problem, measured

Guardana has had an extension contract since 0.18.0 and target locators since 0.24.0, and
since 0.25.0 every declarative rule shape can ship its own samples. What it has never had is a
way to start. `guardana init` writes one policy file. `guardana new-rule` writes one rule file
with no tests, no fixtures, no manifest and no entry points. Everything else an author needs
exists only as an example in this repository: twenty-three files and 1225 lines, which they
copy and then edit until the names stop saying Acme.

That is the gap, and it is the milestone's first row: a pack that is *possible* but expensive
to prove will not create an ecosystem. The [0.25 audit](audit-0.25-market.md) confirmed it is
also the one hypothesis about adoption this project can measure without telemetry.

## What already works, so this document does not rebuild it

- The manifest, its schema version and the separately versioned extension API range —
  [extension author tooling](extension-author-tooling.md), shipped in 0.18.0 and 0.20.0.
- `guardana pack validate`, which compares what a manifest declares against what the entry
  points actually register, and `guardana pack lock`.
- `guardana rule test`, and the three declared samples every rule shape can carry —
  [declarative fixtures](declarative-fixtures.md).
- Target locators, so a pack's target is reachable from the CLI —
  [target locators](target-locators.md).

`new-pack` writes files that use all four. It adds no engine capability.

## Decision 1 — the command is `guardana new-pack`, beside `new-rule`

The `pack` group exists, and both of its verbs — `validate`, `lock` — act on a pack that is
already there. Creation lives at the top level in this CLI: `init` writes a policy, `new-rule`
writes a rule, `new-pack` writes a pack. `ROADMAP.md` and `README.md` have promised the name
in that form since 0.22, and a CLI name is a protected contract, so the published promise wins
over the tidier grouping.

Rejected: `guardana pack new`, which reads better next to its siblings and would rename a
promise nobody has been given a reason to relearn.

## Decision 2 — it writes a pack that passes, not a skeleton that compiles

The generated pack must satisfy `guardana pack validate` and `guardana rule test` with zero
edits, before the author has renamed anything. A scaffold whose first run is red teaches the
author to distrust the tooling at the exact moment they have the least context to judge it,
and it makes the fifteen-minute threshold unmeasurable — the clock would be measuring their
debugging, not the path.

This also fixes what the command is allowed to leave out. Anything that cannot be generated in
a passing state does not ship in the scaffold; it ships as a commented block in the generated
README with the command that adds it.

## Decision 3 — all three declarative shapes, each with its three samples

One rule per shape: a single-prompt rule, a multi-step `steps:` scenario, and an agent run with
`task:` and `tools:`. Each carries the full sample set — one that must produce a finding, one
that must stay clean, one that must decline — because that triple is what `rule test` grades
and what the milestone's exit criterion names.

Three rules is more than a minimum, and that is deliberate: the shapes differ in how their
scripts are written (`reply`, `replies`, `turns`), and an author who starts from the one shape
they happened to ask for will write the other two by guessing. `--shape` narrows the set when
somebody knows what they want.

**The positive sample of each generated rule is evidence, not an absence.** A keyword-graded
rule whose finding sample is any reply without a refusal marker passes trivially, and a
scaffold built to be green on the first run selects for exactly that: the author's first green
would certify a tautology and teach them that this is what a sample looks like. The generated
rules therefore plant a marker and grade its appearance, so the finding sample is proof and
the clean sample fails to fire for a stated reason.

Because `--shape` produces a combination the default run never installs, the gate runs the
default *and* at least one narrowed invocation. A flag whose output is never executed is
machinery nothing verifies.

## Decision 4 — the id namespace comes from the name, and `guardana.*` is refused

`guardana new-pack acme-rules` produces the distribution `acme-rules`, the importable module
`acme_rules` and rule ids under `acme.*`. Four names are refused at the argument, before
anything is written, because a scaffold that emits an invalid pack and relies on a second
command to notice is a false green in its documentation form:

- one that would place ids in the reserved `guardana.*` namespace;
- one whose prefix is a reserved target scheme — `file`, `http`, `https`, `mcp`, `trace` —
  because the generated locator target would then raise at discovery and the pack would not
  load at all;
- one that is not a valid distribution name, or whose module form is not a Python identifier;
- one already installed in this environment, because two origins claiming one id is a registry
  error and the author would meet it as a broken install rather than as a naming mistake.

Each refusal names what it refused and why, and exits 3.

## Decision 5 — the generated rules map to a published framework

Principle 5 says every rule maps to a public framework in edition form, and a scaffold that
emitted `taxonomy: [ACME-01]` would teach the opposite on the author's first read. The three
generated rules therefore map to entries of a shipped catalogue, in edition form. The
`guardana.taxonomies` entry point is still declared and still wired, returning nothing, with
the README explaining that a private control set goes there and how `provides.taxonomies`
names the framework rather than each control.

## Decision 6 — the manifest is written, not generated from the code

Guardana's own manifest is generated from the registry because it lists fifty-six ids.
A third party's is short, and `pack validate` is what keeps it honest. The scaffold writes the
manifest with the ids it just generated, and the generated test suite includes the accuracy
test — a pack that promises a check it does not register is a false green arriving through
documentation.

One constraint makes that test evidence rather than a mirror: **the manifest is rendered from
the catalogue files on disk, after they are written, not from the id list the generator holds
in memory.** Rendered from one list, the manifest and the catalogue agree by construction and
every test comparing them passes whatever the generator does. Rendered from the files, a
catalogue that failed to write is a manifest that does not claim it.

## Decision 7 — the templates are data, not string literals

A template is the text of somebody else's package, and it contains code that would be
wrong inside this one. The generated test suite discovers plugins the way a third
party's test does; a command in this package may not, and a check in this repository
reads every command module looking for exactly that. Keeping the templates as data
files inside the package means the check is right about both: a command that
discovers without a trust policy is still caught, and a template that shows a third
party how to write their own test is not mistaken for one.

It costs one thing, which is worth stating: data has to reach the wheel. The clean
installation gate runs `new-pack` from built distributions in an empty environment,
so a template that stopped shipping is a red build rather than a broken command in
somebody else's terminal.

## Decision 8 — it refuses a directory that is not empty

Writing into an occupied directory risks overwriting an author's work to save them one
argument. The command refuses with exit code 3 — invalid configuration or CLI usage — naming
the path and what it found. `--force` is not offered; `rm -rf` is the author's decision to
state out loud.

"Not empty" ignores `.git` and the editor and platform droppings that would otherwise refuse
the most likely real invocation: `mkdir mypack && cd mypack && git init && guardana new-pack
mypack --dir .`. The ignore set is written down in the usage page rather than discovered by
whoever hits it.

## Decision 9 — the proof is a gate step, and it is the point

Row 1's done-criterion now reads that the pack is proven from an empty directory by a step
that uses no file from this repository. That step:

1. runs `guardana new-pack` into a temporary empty directory, and once more with `--shape`
   narrowed, so the flag's output is executed rather than merely written;
2. installs each result in an isolated environment with no cache, alongside this checkout's own
   packages by path — the same way the three existing example suites install `guardana-core`
   and its siblings. **This is deliberate.** Installing the published engine instead would
   test the last release rather than this commit, so the step would go red one release after
   the contract moved, and it would put a network fetch inside a gate that runs offline;
3. runs `guardana pack validate` **against the generated manifest by path**, and requires the
   generated pack's name in the output. Validating whatever happens to be installed is the
   hole described below;
4. runs `guardana rule test` scoped to the generated pack's id prefix, and asserts the rendered
   counts — fixtures passed, rules not fully sampled — rather than the exit code alone;
5. runs the generated test suite.

**Step 3 exists in that shape because of a real hole.** `installed_manifests()` drops an
installed distribution that ships no manifest, and `pack validate` reports itself
indeterminate only when it found *no* manifest at all. In an environment where any other pack
is installed, a generated pack whose `guardana-pack.yaml` never made it into the wheel is
therefore not a failure — it is a pack the validator never saw, reported as "0 with problems".
Naming the manifest and requiring the pack's own name in the output is what turns that silence
back into an answer. The generated test suite carries the same check from the inside.

"Uses no file from this repository" is a claim about **the generated pack**: no path into
`examples/`, no import of a private module, nothing an author would have had to copy. The
engine is a dependency, and in this gate it is this checkout's copy of it.

`guardana-core` is the only dependency the generated `pyproject.toml` declares, because that is
where the evaluators and the taxonomy catalogues the generated rules resolve against live. The
commands that verify the pack — `pack validate`, `rule test` — ship in `guardana-cli`, which an
author already has if they are running `guardana` at all; the generated README says so rather
than adding a dependency a pack does not import.

The template pins the extension API range the build supports, and a test asserts that the range
in the template still accepts `EXTENSION_API_VERSION`. Without it the scaffold keeps emitting a
range that was right once, and every pack generated after the API moves is refused in both
directions with nothing to point at.

A fourth isolated suite costs roughly what the existing three cost, and it is the only
mechanism that keeps the scaffold honest as the extension contract moves.

## Deferred, with the reason

| Deferred | Reason |
|---|---|
| **A generated Python rule** | the three declarative shapes plus a locator target already exercise both halves of the contract; a fourth example adds a file to read without adding a mechanism to learn |
| **A generated evaluator** | an evaluator worth shipping encodes a judgement, and a scaffolded one would be a keyword matcher wearing a new name — the entry point is wired and empty, which is the honest form of "yours goes here" |
| **Publishing the pack** | naming a registry, a version policy and a signing story is its own decision; the scaffold stops at a pack that installs from a path |
| **A cookiecutter-style template repository** | a template drifts from the contract silently, and nothing runs it; a command in the CLI is covered by the same gate as the contract it writes for |
