---
title: "Repeated trials"
nav_order: 79
summary: "why one reply per prompt cannot support a clean result, what a trial is, how K trials reduce to one case, and the bound a clean result carries instead of reading as safe"
status: accepted
---

# Repeated trials: "clean" means "not observed in K tries", and says K

**Status:** accepted, implemented — ships in the next release · **Written:** 2026-09-23 · **`ROADMAP.md` "Now", row 1**

## The question

`YamlRule.run` sends every prompt once, grades the one reply, and records one
assessment (`yaml_rule.py`, `Assessment`: "one case, measured once"). A rule whose
every reply passed produces no finding, and a report without findings reads as
safe. What it has shown is narrower: this endpoint, sampled once per prompt, did
not produce the failure this time.

A deployed model samples. The published evidence says the gap between one sample
and many is not a rounding error:

- Best-of-N reaches 89% attack success on GPT-4o and 78% on Claude 3.5 Sonnet with
  10,000 augmented samples, and success grows with N along a power law
  ([arXiv 2412.03556](https://arxiv.org/abs/2412.03556)).
- Varying only the decoding raises misalignment "from 0% to more than 95%" across
  eleven models ([arXiv 2310.06987](https://arxiv.org/abs/2310.06987)).
- Prompts that succeed 10.3% of the time under greedy decoding succeed for 90% of
  prompts along other generation paths ([arXiv 2506.17299](https://arxiv.org/abs/2506.17299)).
- Frontier system cards report prompt-injection success at k = 1, 10 and 100
  attempts, not at one.

A result that rests on one trial is not wrong. It is unlabelled, and an unlabelled
"clean" is read as a pass. That is principle 10.

## Decisions

### 1. A trial is one independent attempt at a case

Same input, a fresh request, no conversation state shared with another trial. A
case with K trials makes K requests. `K` is a run setting, not a rule field:
`--trials N` on `probe`, `monitor` and `plan probe`, and `trials:` in
`guardana.yaml`. Every preset keeps `K = 1`, so no existing gate changes cost
without an edit. The documentation recommends 5 for a release gate. That is
garak's default number of generations per prompt.

Trials apply only to rules whose verdict depends on a model sampling a reply:
single-turn rules, scenarios, agent runs and suites. A protocol rule, such as an
MCP authorization check, grades a server's deterministic answer. It keeps
`K = 1` and says so in its record, instead of repeating the same request K times
and implying that more was measured.

Guardana never changes the target's sampling parameters to reduce variance. A
lower temperature measures a configuration nobody deployed
([Miller, arXiv 2411.00640](https://arxiv.org/abs/2411.00640): the temperature
should not be adjusted "for the sake of reducing variance").

### 2. Every trial is recorded; the case is the unit

`Assessment` gains `trial: int | None`. One assessment per trial keeps the raw
outcomes, which judge-error correction ([`judge-error-correction.md`](judge-error-correction.md))
and re-grading ([`regrading-stored-exchanges.md`](regrading-stored-exchanges.md))
both need. `None` means a document written before trials existed, and it is read
as `K = 1`. `case_id` is unchanged, and so is `comparable_key`. The trial index
is not identity. Trial 3 of one run and trial 3 of another are not the same
observation.

This changes the run manifest schema from `6` to `7`. The migration records one
attempt per case for a version-6 document (`execution.trials: 1`, `trial: null`) and
computes no summary from its assessments.

### 3. K trials reduce to three named numbers per case

One function, `reduce_case`, and every renderer reads its output:

| Name | Definition | The question it answers |
|---|---|---|
| `success_rate` | failed trials ÷ graded trials | how often a single request goes wrong |
| `any_success` (ASR@K) | at least one of K trials failed | what an attacker with K tries gets |
| `held_all` (pass^K) | every one of K trials passed | whether the defence is reliable |

A rule still yields a finding when any trial of any case fails. With `K = 1`
that is today's behaviour exactly. The finding's evidence names `m of K trials`
and carries the first failing reply, redacted like all evidence.

### 4. A trial that did not resolve blocks "clean"

A trial is measured (pass or fail), inconclusive, errored, or never sent because
the budget ran out. A rule is clean only when every planned trial of every case
was measured and passed. An inconclusive trial is not a pass, and it does not
count toward the K a bound is computed from. A case short of its K is
`incomplete`, and the rule reports it on the `unverified` channel. `diff/gate.py`
already applies this rule to an incomplete run. Here it applies to each trial.

Budget exhaustion keeps its contract: exit `6`, results preserved, and the
unfinished cases named.

### 5. A clean result carries its bound, computed over cases

When all n cases pass all K trials, the rule reports an upper bound on
`any_success`, the rate a K-try attacker gets, over this rule's cases:

```text
guardana.prompt.jailbreak  clean · 0 of 12 cases in 5 trials each · ASR@5 ≤ 22.1% (95%)
```

The bound is the one-sided exact binomial limit for zero events, 1 − 0.05^(1/n).
It is computed over **cases**, never over pooled trials. The K trials of one
prompt are correlated, so "0 of 60 trials" is not sixty independent
observations. Pooling them is the estimator Miller calls inconsistent. At
`K = 1` the same line reads `ASR@1 ≤ 22.1%`, which is exactly how little twelve
single replies establish.

The population is the rule's own prompt set, not "attacks in general". The human
renderer prints one run-level line: `static prompt set · no adaptive attacker
ran`. No adaptive attacker ships today, so the line is always there. A bound over
a fixed corpus must not be read as robustness
([arXiv 2510.09023](https://arxiv.org/abs/2510.09023) bypassed twelve defenses
reported at near-zero attack success).

When some trial failed, the rule has a finding. The report adds the mean
`success_rate` over cases and a Wilson interval on `any_success` over cases.

### 6. Cost is exact and priced before the run

`estimated_requests` becomes `prompts × K` for a trial-bearing rule. The
docstring's promise holds: this is an exact count, not a ceiling. `plan probe`
prints it, and a budget bounds it. `RuleRecord.trials` keeps its meaning,
"model calls this rule declared", and its value multiplies by K. A coverage
fingerprint therefore changes when K does.

### 7. Two runs with different K do not compare

A finding that appears at `K = 5` and was absent at `K = 1` is more sampling, not
a regression. When K differs for a rule, `diff` marks that rule `incomparable`
with the reason `trials changed 1 → 5`. Unlike a changed dataset or assessor, which
only leaves the affected cases out of the measured sample, a changed K fails the
comparison: the whole rule's findings would otherwise be read as movement.

## What changed during implementation

- **A stored summary, and a renamed field.** Each repeating rule's record carries a
  `trial_summary` the engine computed when the run was written, as the gate verdict is
  stored, so a later build cannot print a different verdict for the same run. The old
  `run.rules[].trials`, which counted declared model calls, is `declared_requests` in
  version 7; K per case lives in the summary and the run's request in
  `execution.trials`.
- **The most confident failure speaks for the case.** A policy's `min_confidence` reads
  the case's verdict, so a doubtful first failure must not hide a certain later one.
- **A failure seen before the rule stopped is kept.** When a budget runs out or a later
  attempt raises, the failure already observed is yielded before the stop propagates.
- **K comes from the rule object that ran**, carried on the result, not from the
  registry's copy: a canary pass runs a planted copy.
- **Merged passes keep every attempt.** Assessments are de-duplicated by comparability
  key *and* trial; keyed on the case alone, the canary merge kept one attempt per case.
- **A `stateful` scenario does not repeat.** Its server holds the conversation and
  nothing opens a fresh one, so a second attempt would continue the first.
- **Bounds print one decimal, rounded up**, so a printed bound never claims more than
  the cases showed.
- **A scenario is one case per attempt.** Its graded turns get separate case ids for the
  measurement channel, but they are checkpoints of one conversation, so the summary counts
  one case per walk rather than treating correlated grades as independent.
- **A case id is never shared.** A rule file listing a prompt twice, or a scenario grading
  the same message twice, is refused at load: the two would be one case recorded twice.
- **A finding denies the bound.** A rule that reported a finding never stores a bound, even
  if its recorded trials look clean.
- **The line says "grader error not corrected"**, which is true whether or not a
  calibration exists, until judge-error correction lands.

## Rejected

**Pooling trials as independent observations.** It is cheaper to explain and
wrong. Clustered standard errors "can be over 3X larger than naive"
([Miller](https://arxiv.org/abs/2411.00640)), so a pooled bound claims far more
than the data holds.

**Stopping a case at its first failure.** It saves requests when a model is
already failing. The saving costs `success_rate`, the number
[`paired-regression-statistics.md`](paired-regression-statistics.md) compares, and
it makes `estimated_requests` a ceiling instead of an exact count.

**One assessment per case holding counts.** Smaller, but the raw trials are gone,
and both judge correction and re-grading need them.

**Forecasting large-N success from a fitted curve.** Best-of-N's power law and
SABER's per-prompt Beta fit ([arXiv 2601.22636](https://arxiv.org/abs/2601.22636))
are defensible research. A forecast is not a measurement, and a pack can ship one
as a renderer once output plugins exist.

**A new preset with `K > 1`.** It would multiply the cost of a gate nobody edited.
K is raised on purpose, where the bill is visible.

## See also

- [`quality-suites.md`](quality-suites.md): a suite's cases are trial-bearing too
- [`paired-regression-statistics.md`](paired-regression-statistics.md): comparing per-case rates between runs
- [`judge-error-correction.md`](judge-error-correction.md): when the grader of each trial is itself a model
- [`assessment-channel.md`](assessment-channel.md): the record every trial becomes
