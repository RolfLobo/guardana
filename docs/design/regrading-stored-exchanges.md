---
title: "Re-grading stored exchanges"
nav_order: 82
summary: "keeping the redacted exchange behind every assessment so a new assessor can grade an old run without touching the target, why it is opt-in, and why an exchange redaction altered cannot be re-graded into a pass"
status: proposed
---

# Re-grading stored exchanges: a new judge, the same replies

**Status:** proposed · **Written:** 2026-09-23 · **`ROADMAP.md` "Now", row 3**

## The question

A team upgrades its judge: a new rubric, a new judge model, or a calibrated
`reference_judge`. The next `diff` correctly refuses to compare the old run with
the new one, because the assessor changed
([`assessment-channel.md`](assessment-channel.md)). The only way forward today is
to probe again. That costs the target traffic a second time, and it mixes two
changes, since the target may have moved as well. The question "how different is
the new judge from the old one on the same replies" has no answer at all.

A saved run cannot answer it. Evidence is written only for a non-passing case
(`yaml_rule.py`), and `Assessment` stores a verdict, not the exchange behind it.
`SourceKind.REPLAY` exists in the manifest and nothing produces it.

Among comparable tools, Inspect re-scores a stored log with a different scorer
(`inspect score --scorer`), PyRIT has stored-response scoring on its main branch,
and promptfoo sells re-grading in its Enterprise tier.

## Decisions

### 1. Keeping exchanges is opt-in

`evidence.keep_exchanges: true` in `guardana.yaml`, or `--keep-exchanges` on
`probe` and `monitor`. The default is off. Redaction is not a dependable privacy
boundary, and keeping every passing reply widens what a leaked run exposes. That
is a decision an operator makes for their data, not a default this tool makes for
them. `keep_exchanges` with `evidence: metadata_only` is a load error. The two
settings contradict each other, and choosing one silently would betray whichever
the operator meant.

### 2. What is kept, and where

For every assessed trial ([`repeated-trials.md`](repeated-trials.md)), the file
keeps the exchange as the evaluator saw it. For a chat rule that is the messages.
For an agent rule it is the trajectory, meaning every tool call and result. The
file also keeps the per-run inputs grading needs and the rule's declaration does
not hold, such as a planted canary. Each exchange passes the same
`EvidenceRedactor` as a finding, once, before it is written.

The file is a sidecar, `<run>.exchanges.jsonl`, with its own `schema_version`.
The run manifest records its digest. A sidecar that does not match the digest is
refused, not re-graded. A separate file lets an operator delete the replies and
keep the verdicts, give the two different retention periods, and keep `run.json`
small. The collector never receives the sidecar. The reporter seam carries
findings and assessments, and it stays that way.

### 3. `guardana run regrade`

```bash
guardana run regrade run.json --evaluator llm_judge --profile guardana.yaml --output regraded.json
```

The command writes a new run document with `source: replay`, the original
subject, cases and trials, and the new assessor on every assessment. It sends no
request to the target. An evaluator that calls its own model, such as a judge,
makes that call as it does during a probe, to the endpoint the profile configures.

### 4. What cannot be re-graded says so

Only a verdict that is a function of the exchange and the rule's expectation can
be recomputed. A protocol rule, such as an MCP authorization check, grades a live
server's behaviour, and an artifact rule is cheaper to re-scan. Those rules
become `skipped` with the reason `not regradable`. They are never carried over
from the original run as if they had been graded again.

**An exchange that redaction altered is not re-graded into a pass.** A
`guardana.output.*` rule looks for a secret in a reply. The stored reply has had
that secret replaced by `[redacted:…]`, so a naive re-grade finds nothing and
passes a run that originally failed. Every kept exchange records whether
redaction changed it. A re-grade of an altered exchange is `inconclusive` with
the reason `exchange altered by redaction`, unless the run kept `evidence: full`.
A trial whose redaction failed was never written, and its re-grade is
`inconclusive` too. Principle 10 names a redaction failure as its own outcome.

### 5. Same replies, two assessors: a comparison that measures the judge

`diff original.json regraded.json` pairs on `(case_id, trial)`. It recognises that
the exchanges are identical, because the sidecar digests match, and answers a
different question from a normal diff. It reports agreement between the two
assessors, and the discordant counts in each direction with the exact test from
[`paired-regression-statistics.md`](paired-regression-statistics.md). Today this
pair of runs is simply incomparable. Afterwards it is the only measurement of
assessor drift that holds the target fixed.

### 6. The labelled slice judge correction will need

With the exchanges kept, a human can label a sample of *this* run's replies. That
is the input prediction-powered inference needs, which
[`judge-error-correction.md`](judge-error-correction.md) defers. This design only
keeps the replies. The labelling workflow is later work.

## Rejected

**Keeping exchanges by default.** It is the one decision here that is not ours to
make for somebody else's data.

**Storing them inside `run.json`.** One file cannot have two retention periods,
and a run document that grows with every passing reply stops being something
people attach to a pull request.

**Storing hashes instead of text.** A hash proves two runs saw the same reply. It
cannot be graded.

**Re-grading by re-sending the recorded prompts.** That is a new run against a
target that may have changed, which is the confound this design removes.

**Forwarding the sidecar to the collector.** The collector's tenancy and retention
were designed for findings and measurements, not for model output
([`collector-tenancy.md`](collector-tenancy.md),
[`audit-retention-and-deletion.md`](audit-retention-and-deletion.md)). Widening
that is its own design.

## See also

- [`privacy-and-redaction.md`](privacy-and-redaction.md): the one redactor every kept exchange passes
- [`repeated-trials.md`](repeated-trials.md): the trials a sidecar line belongs to
- [`judge-error-correction.md`](judge-error-correction.md): what a labelled slice of kept replies enables
- [`run-manifest-v2.md`](run-manifest-v2.md): the document the sidecar's digest lives in
