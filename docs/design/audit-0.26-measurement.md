---
title: "The 0.26 measurement audit"
nav_order: 28
summary: "what one trial per prompt and an uncalibrated judge let a clean result claim, what the measurement literature and five comparable tools do about it, and why rows 1 and 2 widened and a re-grading row was added"
status: accepted
---

# The 0.26 measurement audit

**Status:** accepted · **Written:** 2026-09-23 · **Subject:** released 0.26.1, and the
designs rows 1 and 2 of the "Now" milestone will be built from

## Question and the decision it informs

What engine-level work, beyond the current "Now" rows, would move Guardana furthest — and
does any of it change the two designs rows 1 and 2 will be built from
([`quality-suites.md`](quality-suites.md),
[`paired-regression-statistics.md`](paired-regression-statistics.md), both `proposed`,
neither implemented)?

The market and the standards were re-read on 2026-09-20
([`audit-0.25-market.md`](audit-0.25-market.md)) and moved no row. This pass does not repeat that; it reads the measurement and engine
literature instead, and the answer lands on rows 1, 2 and the `monitor` path.

## What exists today

- **One trial per prompt.** `yaml_rule.py:104-105` sends each prompt once;
  `estimated_requests` is `len(self.prompts)` (`yaml_rule.py:71-78`). `RuleRecord.trials`
  (`manifest/records.py:37`) counts declared calls, not repeats. No samples/epochs option on
  `probe`. The only repetition is the judge's own `min_agreement` (`llm_judge.py:121`).
- **Calibration is recorded, never applied to a rate.** `calibration/measure.py:14-44`
  computes accuracy, Brier and ECE — no sensitivity, no specificity. The record lands in
  `EvaluatorRecord.calibration` (`_run_meta.py:233-237`). A hand-entered accuracy caps the
  judge's confidence (`llm_judge.py:172`) without changing an outcome.
- **A saved run cannot be re-graded.** Evidence is written only for non-passing cases
  (`yaml_rule.py:129-137`); `Assessment` stores the verdict, not the exchange
  (`assessment.py:52-100`). `SourceKind.REPLAY` exists (`manifest/identity.py:23`) and
  nothing uses it.
- **`monitor` compares every cycle with cycle 0, categorically** (`core/monitor.py:58-83`,
  baseline at `:116-117`): any `appeared`/`escalated`/`coverage_lost`, more errors, or an
  incomparable cycle alerts. No statistics, no allowance for repeated looks.
- **`diff` reports counts, never gates on them** (`diff/measurement.py:82-117`,
  `diff/model.py:170-176`). The McNemar design assumes one boolean per case per run.
- **Agent rules grade tool calls, not text** (`trajectory/drive.py:93-112`,
  `evaluator/tool_call.py`). The only state a double keeps is `AgentMemory`
  (`trajectory/memory.py:11-48`).
- **No attack transforms in code**; [`attack-techniques.md`](attack-techniques.md) is `proposed`.
- **MCP `2026-07-28` is already handled** — both eras, settled by `server/discover`
  ([`mcp-protocol-eras.md`](mcp-protocol-eras.md), `target/_mcp_wire.py:23-24`). Nothing to do.

## Evidence

Quotes were read through a web extractor on 2026-09-23; re-check a quote on its page before
citing it publicly.

**One sample understates attack success, by a lot.**
- Best-of-N: "89% on GPT-4o and 78% on Claude 3.5 Sonnet when sampling 10,000 augmented
  prompts"; ASR vs N "follows power-law-like behavior". [arXiv 2412.03556]
- Decoding alone: "increase the misalignment rate from 0% to more than 95% across 11
  language models". [arXiv 2310.06987]
- Boa: greedy evaluation "suggests only 10.3% success—yet … 90% of these prompts can produce
  jailbreaks through alternative generation paths". [arXiv 2506.17299]
- SABER: single-shot evaluation "underestimates real-world risk"; a per-prompt Beta fit on
  n=100 predicts ASR@1000 with MAE 1.66 vs 12.04. [arXiv 2601.22636]
- Frontier practice reports k=1, 10 and 100 attempts (Opus 4.5 system card, Gray Swan).
  τ-bench adds pass^k — success on all k trials — for reliability. [arXiv 2406.12045]

**How to put error bars on it** (Miller, [arXiv 2411.00640]): standard errors over
*question-level means* when resampling K answers ("a pooled standard error across all KN
answers will be inconsistent"); clustered SEs "can be over 3X larger than naive"; paired
differences are "a 'free' reduction in estimator variance"; power analysis gives a minimum
detectable effect — at n=198, K from 1 to 10 cuts the MDE from 13.2% to 7.5%. Never lower
temperature to reduce variance.

**The judge's error is measurable and correctable.**
- Red-teaming judges: LLM judges "show erratic recall (0.06 to 0.65)"; benign wrappers flip
  every judge "between 57% and 100% of the time"; recommends reporting "ASR corrected for
  judge precision". [arXiv 2606.25487]
- Rogan–Gladen with sensitivity and specificity from a labelled set, uncertainty from both
  sets propagated. [arXiv 2511.21140] Two limits the paper states for its own setting: the
  shift-robustness assumes the judge behaves the same *given the true label* in both
  populations, and "m ≈ 200 calibration examples" for an interval under 0.1 is one
  illustrated configuration, not a general requirement.
- Prediction-powered inference gives valid intervals from few labels plus many judge
  outputs. [arXiv 2301.09633, 2311.01453, 2403.07008]
- Shared calibration across two compared models "can introduce severe bias, including …
  the wrong direction with high apparent confidence". [arXiv 2605.06939]

**Repeated looks inflate false alarms.** p-values "are wholly unreliable if users …
continuously monitor" [arXiv 1512.04922]; confidence sequences are "uniformly valid over an
unbounded time horizon" [arXiv 1810.08240], with a betting construction for bounded means
[arXiv 2010.09686] and an ML-monitoring use that does not raise the false-alarm rate
[arXiv 2110.06177].

**What the comparable tools ship** (docs and source at HEAD):
- Repeats: Inspect (epochs + reducers incl. `pass_at_k`, `pass_k`), garak (`generations`
  default 5), promptfoo (`--repeat`, cached unless `--no-cache`), lm-eval (`repeats`).
- Clustered SE: Inspect only. garak bootstraps over attempts pooled across generations.
- Paired comparison of two runs: **none of the five**. lm-eval compares with an unpaired z;
  Inspect suggests interval overlap; promptfoo's compare is a text diff.
- Judge-error correction: garak only — point estimates, a silent `(1.0, 1.0)` fallback when
  detector metrics are missing, uncorrected CI when Se+Sp−1 ≈ 0. PyRIT measures judges and
  does not correct rates.
- Anytime-valid monitoring: **none of the five**.
- Re-grading stored transcripts: Inspect (`inspect score --scorer`), PyRIT (on main, not
  released), promptfoo (Enterprise only), garak (not found).

**Attack engine and agents, for the deferred lane.** PyRIT 1.0 is "dataset × techniques ×
jailbreaks"; garak buffs, promptfoo strategies — all a transform registry with a small
default set, none documented as priced against a budget before the run. "The Attacker Moves
Second" bypasses 12 defenses at >90% ASR, most of which "originally reported near-zero"
[arXiv 2510.09023]. AgentDojo, AgentHarm and WASP grade environment state or tool calls,
report utility and utility-under-attack beside ASR, and keep partial success apart.

## Options

**A. Trials as an engine concept (rows 1 and 2).** A case becomes a prompt with K trials; an
assessment records every trial. A rule reports the finding on any success (ASR@K), and a clean
result carries its bound instead of reading as safe. The bound is computed over *cases*, never
over pooled trials: K trials of one prompt are correlated, so "0 of 60 trials" is not sixty
independent observations. Statistics cluster on the case: suites use per-case means, and
`diff` uses a paired difference of per-case means (McNemar remains the K=1 special case) with
the minimum detectable effect printed. It refuses to compare runs with unequal K. A planned
trial that did not resolve to pass, fail or inconclusive is counted and blocks "clean", which
extends to trials the run-level rule `diff/gate.py` already applies to an incomplete run.
Costs ×K requests, which `plan` already prices and a budget already bounds, plus a manifest
schema bump. This serves principle 10 directly: today "clean" means "not observed in
one trial".

**B. Judge-aware rates (row 1).** `calibrate` records per-class counts: sensitivity,
specificity, m₀, m₁. A rate graded by a non-deterministic evaluator is Rogan–Gladen corrected,
with the calibration uncertainty in the interval. A missing calibration, or Se+Sp−1 near zero,
never falls back silently to the raw number; it is its own outcome. Two runs that share one
calibration are flagged in `diff`. No new dependency. It extends a record that already exists.

**C. Re-gradable evidence (a new row before output plugins).** Persist the redacted exchange
for every assessed case, passes included, and add `guardana run regrade <run> --evaluator …`
on the unused `REPLAY` source kind. A judge upgrade then costs no target traffic. Grading the
same transcripts under two assessors measures assessor drift on its own, the one change `diff`
currently can only refuse. Costs a persisted schema change and more stored text, which argues
for opt-in and redaction on write.

**D. Anytime-valid `monitor` (Next item 3, own design).** Rate checks in `monitor` use a
confidence sequence, betting over a bounded mean with only `math`, so a schedule of looks does
not buy false alarms. Categorical changes (a new finding) stay as they are. The design rejected
sequential testing because it "belongs with the intake lane", but `monitor` already looks
repeatedly today. The estimand is still open: cycle versus a fixed baseline on a target that
may be redeployed between looks tests a moving hypothesis, and many rules looked at together
still need multiplicity control. That is a design question, not a formula. Until it is
answered, an alpha-spending rule keeps the false-alarm rate bounded over any number of cycles.

**Not now — techniques, adaptive attackers, stateful agent doubles.** Each adds coverage
volume. The milestone outranks coverage, and each becomes honest only once A and B exist:
Best-of-N is K trials over transforms, and an adaptive attacker needs a judge whose error is
known. One cheap piece belongs in A: the human report states K and "static prompt set, no
adaptive attacker", so a clean result is never read as robustness.

## Decision

Amend the two proposed designs before any code: fold **A** and **B** into row 1, and
**A's statistics** into row 2. Add **C** as a new row between the paired diff and the output
plugins. **D** gets its own design document in the Next lane, where the sequential question
already lives, and row 2 applies alpha-spending to `monitor` meanwhile. Nothing shipped
changes shape.

The designs that carry it:

- [`repeated-trials.md`](repeated-trials.md) — A, row 1
- [`judge-error-correction.md`](judge-error-correction.md) — B, row 1
- [`quality-suites.md`](quality-suites.md) and
  [`paired-regression-statistics.md`](paired-regression-statistics.md) — amended for A and B,
  plus the minimum detectable effect, Holm across gated suites, and alpha-spending in `monitor`
- [`regrading-stored-exchanges.md`](regrading-stored-exchanges.md) — C, row 3
- [`anytime-valid-monitoring.md`](anytime-valid-monitoring.md) — D, Next item 3 The order of the existing rows stays. The
milestone's exit criteria gain one clause: "a clean result states its trials and its judge's
measured error".

Why: all four close a gap by the project's own definition of a false green, and A–C land in
shapes still on paper. Three of the four are absent from all five comparable tools: paired
comparison, propagated judge correction and anytime-valid monitoring. That matches the
audit's finding that rows 1–3 are where Guardana follows no one.

Defers: techniques and adaptive attackers stay under "Researched after the foundations", now
with a stated prerequisite (A and B). Stateful agent doubles go to the parallel lane.

## Second opinion

GPT answered. Gemini did not: its quota was exhausted on the day of writing. This is one
model family's view, not a consensus, recorded as a gap in the method. GPT orders A+B, then C,
then D, and says B must ship with A because judge error compounds across K. Its objections are
folded in above: correlated trials, unequal K, the limits of Rogan–Gladen, and D's estimand.
Its C objection is not resolved: redaction is not a dependable privacy boundary, and
persisting every passing transcript widens what a leak exposes. It argues for opt-in, and
possibly for storing only what a regrade needs. Its one addition, a completeness gate for
trials, is now part of A.

## Decided defaults

1. **K is 1 in every preset** (`ci`, `pre-training`, `monitor`), recorded and printed. K is
   raised with `--trials` or `trials:` in `guardana.yaml`, and the documentation recommends 5
   for a release gate, which is garak's default. No preset raises it, because a preset that
   multiplied requests would change the cost of a gate nobody edited.
2. A gate over a judge-graded rate with no usable calibration is **inconclusive**, with the
   uncorrected rate shown and labelled, never gated.
3. Keeping passing exchanges for re-grading is **opt-in, redacted on write**, in a sidecar the
   collector never receives.

## Sources

arXiv 2412.03556 · 2310.06987 · 2506.17299 · 2601.22636 · 2406.12045 · 2411.00640 ·
2606.25487 · 2511.21140 · 2301.09633 · 2311.01453 · 2403.07008 · 2605.06939 · 1512.04922 ·
1810.08240 · 2010.09686 · 2110.06177 · 2510.09023 · 2406.13352 (AgentDojo) · 2410.09024
(AgentHarm) · 2504.18575 (WASP). Inspect: inspect.aisi.org.uk/metrics.html,
/scoring-workflow.html. garak: reference.garak.ai, `garak/analyze/bootstrap_ci.py`.
promptfoo: promptfoo.dev/docs (configuration/caching, releases). PyRIT:
github.com/microsoft/PyRIT `doc/code/framework.md`. lm-eval: `scripts/model_comparator.py`.
All read 2026-09-23.
