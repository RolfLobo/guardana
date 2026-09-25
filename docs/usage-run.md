---
title: "guardana run"
nav_order: 200
summary: "`guardana run inspect|migrate`: reading a saved run and its manifest"
status: stable
---

# `guardana run` — reading a saved run

`guardana run inspect` shows a saved run when you need to review its manifest or compare it with `guardana diff`. A run saved with `--output` records its target, configuration, limits, cost, and gate.

```bash
guardana scan . --format json --output run.json
guardana run inspect run.json
```

```text
run 0191d4c2-8f1a-7c3e-9b21-6f0a2d8e4c11
  started:   2026-08-02 09:14:02+00:00
  completed: 2026-08-02 09:14:03+00:00
  source:    ci (github)
  guardana:  0.7.0
  target:    artifact .
  profile:   ci
  gate:      pass
  findings:  0 (0 unverified, 0 waived, 0 error(s))
  rules run: 19 (0 skipped)
  trials:    1 per case asked; 0 rule(s) repeated
  requests:  0
  tokens:    in not recorded, out not recorded
  wall time: 0.42
  evidence:  full
```

`--format json` prints the manifest. `requests: 0` is measured; tokens are `not recorded`.

## What a run costs

`usage` carries what the run actually spent: requests sent, tokens in and out,
and wall time.

The counting happens on the **target**, not on the transport, so every request to
a model is counted whatever transport is in use — a custom adapter, a scripted
double in a test, or one of the built-ins. A target that does not meter itself
(anything you wrote yourself, unless you override `Target.usage()`) reports
nothing rather than zero.

Token counts depend on the provider. The built-in OpenAI, Ollama and TGI paths
read them from the response; a transport that does not implement the optional
`UsageReportingTransport` protocol leaves them unknown. Where only *some*
requests reported tokens, the manifest carries the sum **and**
`requests_missing_token_counts`, so the number is never mistaken for the whole
bill. See [`docs/writing-rules.md`](writing-rules.md) for the protocol.

## What "not recorded" means

It means **nobody measured this**, and it is deliberately not printed as `0`.
A file scan that sends zero requests and a run from a version that never counted
requests are different facts; only one of them lets you budget the next run. The
same distinction runs through the whole document: `null` is always "not known",
never "not applicable" and never zero.

## What a run could check

`coverage` is the other half of the promise `rules_run` started. A run whose corpus
was trimmed, whose evaluator stopped being installed, whose target lost a capability
or whose MCP server answered an older protocol revision reports fewer findings — and
subtracting two lists reads every one of those as an improvement.

So the manifest carries one fingerprint over all of it, plus the framework
catalogues that were installed, each pinned by digest. That is what lets a report be
read years later without asking which edition of a framework was in use: `LLM07`
means System Prompt Leakage in `OWASP-LLM-2025` and Misinformation in
`OWASP-LLM-2026`, and the run says which one it held. `guardana diff` compares the
fingerprint and reports a difference as *the reach changed*, separately from what
was found. A run that recorded none is reported as **unknown reach**, never as equal
reach.

## Older runs still load

A run written by 0.6 uses schema version 1, and one written by 0.12 uses version 2.
`guardana diff` and `guardana run inspect` **migrate them forward in memory** as they
read them, one step at a time, so upgrading Guardana does not strand the evidence you
already have.

What an older version never recorded arrives as an explicit unknown rather than as a
default — version 1 has no usage, no execution settings and **no gate verdict**;
version 2 has no coverage fingerprint and no declared request counts; version 3 could
not name a `trace` target, because that kind did not exist; version 6 made one attempt
per case, so it arrives with `execution.trials: 1`, `trial: null` on every assessment
and no `trial_summary` on any rule — the summary is not recomputed from its
assessments. Recomputing any of them during migration would apply today's build to
another build's run, which is exactly what storing them as fields exists to prevent.
`inspect` says so at the bottom of its output, and `diff` adds a note.

A schema-7 run migrates to schema 8 with the correction fields `null`; nothing is
recomputed. Its trials line still prints
`graded by <assessor>, grader error not corrected`, as it was written.

One thing *is* recovered: the **title** of a framework reference, which version 3
onward records beside its framework and id. It is looked up from the installed
catalogue for the exact `(framework, id)` pair the document already carries, so
nothing is guessed and no reference is remapped — a `LLM07` recorded under
`OWASP-LLM-2025` stays System Prompt Leakage. A reference from a rule pack this build
does not have stays titleless, because nothing here knows what it was called.

To rewrite an old file on disk at the current schema:

```bash
guardana run migrate old-run.json --output new-run.json
guardana run migrate old-run.json          # in place
```

This is a convenience, not a requirement. Nothing needs migrating to be compared.

**A migration that cannot carry a field refuses, and writes nothing.** The default
destination is the file itself, so a half-done migration would overwrite the only copy
of the evidence. In 0.7.0 a version-1 run that never recorded its target kind was
migrated into the literal string `"None"` — a document that fails this schema, written
over the original, with exit `0`. Every unit test around migration passed, because
they asserted on the objects the migration loaded and the objects were fine; what was
published was the file. There is now a test that validates the *artifact*,
parametrised over every field a version-1 run could be missing.

## The document

The saved-run schema lives at
[`schemas/run-v8.schema.json`](../schemas/run-v8.schema.json), identified by
`https://guardana.dev/schemas/run/v8.schema.json`, and the site serves every schema
at the URL its identifier names. The version is in the identifier,
so a consumer can tell which contract it is holding before parsing anything; it
changes whenever the change is not backwards-compatible. A test validates what
Guardana writes against that file, so the schema cannot drift away from the tool.

Every superseded version stays published — `run-v2` and `run-v3` are still in
[`schemas/`](../schemas/) — because a saved run has to keep validating against the
schema it was written to. Version 4 exists for one reason: it permits a `trace` target
kind. Widening version 3's enum in place was the alternative, and it would have
changed a contract under a name that promised it had not. Version 6 adds the
`assessments` channel and `run.rules[].origin`; a version-5 document migrates forward
with the first empty and the second `null`, because that is what it knew. Version 7
records repeated trials: `run.execution.trials`, `assessments[].trial` and
`run.rules[].trial_summary`, and renames `run.rules[].trials` to `declared_requests`,
which is what it always counted. Version 8 records the `correction` block on
`trial_summary` and the calibration fields on `run.evaluators[]`.

Top level:

| Key | What it is |
|---|---|
| `schema_version` | `8`. Stated once, for the whole document. |
| `run` | the manifest — everything below |
| `findings` / `unverified` / `waived` / `errors` / `observations` | the problem, evidence and inventory channels |
| `assessments` | what the run *measured*, pass included — see [assessments](#assessments) |

Inside `run`:

| Block | Answers |
|---|---|
| `run_id`, `created_at`, `started_at`, `completed_at` | which run is this, and when |
| `migrated_from` | which older schema it came from, or `null` |
| `source` | who started it — a laptop, CI, a schedule |
| `guardana` | which software produced it |
| `target` | what was examined, with a fingerprint and the fields that fingerprint covers |
| `deployment` | which deployment of which AI system this verifies |
| `configuration` | which settings produced it, **by digest** |
| `execution` | what limits it ran under, and `trials`: the attempts per case the run asked for |
| `usage` | what it actually consumed |
| `rules` / `evaluators` | what did the checking, with digests, declared request counts, a `trial_summary` for each rule that repeated, and calibration |
| `coverage` | what the run was *able* to check: one fingerprint, the framework catalogues it mapped against by digest, and any protocol versions the target negotiated |
| `result_summary` | the counts, the gate, and whether the run was cut short |
| `privacy` | which evidence policy was in force |

Three conventions hold everywhere in it:

**Timestamps are UTC, RFC 3339.** A local-time timestamp in an evidence record is a
bug waiting for a timezone.

**Digests name their algorithm** — `sha256:…`, never a bare hex string, so a digest
can be migrated when the algorithm moves.

**The target fingerprint says what it covers.** `target.fingerprint_inputs` lists the
fields the digest was computed from. A digest of a URL and a model name identifies a
*declared* target; it attests nothing about the weights behind it, and the document
says so rather than leaving a reader to assume the stronger reading.

## Assessments

The channel that is not about problems. Every other one — findings, unverified,
errors, coverage shortfall — records something wrong; a check that ran and was
satisfied used to leave nothing but its id in `rules_run`.

That is enough to gate a build and not enough to answer *did this get better*,
because fewer findings has three causes and the count cannot separate them: the
system improved, the test got weaker, or the sample changed.

```json
{
  "case_id": "guardana.prompt.jailbreak#b94d27b9934d",
  "assessor": "keyword",
  "subject_ref": "http://localhost:11434#llama3",
  "status": "measured",
  "rule_id": "guardana.prompt.jailbreak",
  "passed": true,
  "value": null,
  "unit": null,
  "direction": null,
  "threshold": null,
  "confidence": 0.6,
  "dataset": "5435b77094cde319",
  "rationale": "Response contains a refusal marker.",
  "tags": [],
  "trial": 1
}
```

| Field | What it is |
|---|---|
| `case_id` | the identity two runs are paired on. A hash of what distinguishes the case, so reordering prompts changes nothing and rewording one is a new case. It does not carry the text it was built from, so it is safe in a redacted report |
| `assessor` | what produced the verdict — an evaluator id, or a rule grading in its own code |
| `status` | `measured`, `inconclusive`, `error` or `skipped`. The last three are statuses, never zeros, and are excluded from the denominator |
| `passed` | the boolean reading, or `null` when nothing could be graded. Never `false` for a case that was not measured |
| `value`, `unit`, `direction`, `threshold` | the numeric reading, which way is better, and the bound applied on *this* run |
| `confidence` | how much the assessor trusts itself, when it can say. Never invented |
| `trial` | which attempt at the case this was, from `1`, for a rule that can repeat; `null` for a rule that cannot, and for a run saved before trials existed. Not part of a case's identity: two runs pair on `case_id` |
| `dataset` | which versioned corpus the case came from. For a YAML rule this is its declaration digest, so an edited expectation makes the two runs incomparable rather than making the model look worse |

`run.result_summary` carries `assessments` and `measured` as two numbers rather
than one rate. Both count records, one per attempt, so a rule that repeats five times
adds five per case. Their difference is the fact that matters: 40 assessments and 3
measured is a pass rate over three cases, and a summary carrying only the pass
count would present it with the same confidence as a full run.

An artifact scan records none of these, and that is correct — reading a file and
finding nothing is not a measurement. See
[`design/assessment-channel.md`](design/assessment-channel.md) for the reasoning,
and [`usage-diff.md`](usage-diff.md) for what a comparison does with them.

## Trial summaries

Each rule that repeated carries what its attempts added up to, over cases, as the engine
reduced them when the run was written:

```json
"trial_summary": {
  "trials_per_case": 5,
  "cases": 12,
  "cases_failed": 0,
  "cases_incomplete": 0,
  "bound": 0.2209,
  "mean_success_rate": 0.0,
  "correction": {
    "status": "uncorrected",
    "assessor": "keyword",
    "reason": "judge error not measured: no calibration recorded for keyword",
    "rate": null,
    "low": null,
    "high": null,
    "sensitivity": null,
    "specificity": null,
    "dataset_digest": null,
    "positives": null,
    "negatives": null
  }
}
```

| Field | What it is |
|---|---|
| `trials_per_case` | the attempts this rule made at every case. It can be lower than `execution.trials`: a rule that cannot repeat has no summary at all |
| `cases`, `cases_failed`, `cases_incomplete` | how many cases, how many had a failed attempt, and how many had an attempt nobody could grade and no failure |
| `bound` | the 95% upper bound on the share of cases where any attempt fails, over cases, set only when every attempt of every case passed |
| `mean_success_rate` | the mean, over cases, of each case's share of failed attempts |

The `correction` block records how judge error was handled:

| Field | What it is |
|---|---|
| `status` | `deterministic`, `corrected`, or `uncorrected` |
| `assessor` | the id carried by the rule's verdicts and used to match the calibration |
| `reason` | why a rate stays uncorrected |
| `rate`, `low`, `high` | corrected `ASR@K` and its 95% interval; a clean rule has a one-sided interval with `low` at `0` |
| `sensitivity`, `specificity` | the per-class rates applied to the correction |
| `positives`, `negatives` | the graded class counts behind those rates |
| `dataset_digest` | the calibration corpus digest |

A corrected block states all these fields. A `null` `correction` means the document was
written before schema 8.

`run.evaluators[].calibration` also gains `assessor`, `judge_identity`,
`starter_corpus`, `positives`, `negatives`, `positives_inconclusive`,
`negatives_inconclusive`, `sensitivity` and `specificity`.

The summary is stored rather than recomputed by each reader, as the gate verdict is, so
a later build prints the verdict this run was written with. A rule that stopped part-way
is not in `rules`, so it has no summary to misread. `run.rules[].declared_requests` is
the number of requests the rule declared, attempts included.

## Field names borrowed on purpose

`usage.input_tokens` and `usage.output_tokens` are the OpenTelemetry GenAI
convention's [`gen_ai.usage.input_tokens` /
`gen_ai.usage.output_tokens`](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)
without the namespace; `execution.seed` and `execution.temperature` match
`gen_ai.request.*`. If you already collect those, the manifest needs no
translation.

The SARIF output carries the same facts in SARIF's own vocabulary: `runs[].invocations[0]`
with `startTimeUtc`, `endTimeUtc`, `exitCode`, `exitCodeDescription` and
`executionSuccessful`.

## See also

- [`usage-diff.md`](usage-diff.md) — comparing two saved runs
- [`usage-scan.md`](usage-scan.md) and [`usage-probe.md`](usage-probe.md) — producing them
