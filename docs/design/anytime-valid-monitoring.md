---
title: "Anytime-valid monitoring"
nav_order: 83
summary: "why a monitor that tests every cycle at a fixed level eventually alerts on noise, the alpha-spending rule that keeps it honest now, and the questions a confidence sequence must answer before it replaces that rule"
status: proposed
---

# Anytime-valid monitoring: a schedule of looks must not buy false alarms

**Status:** proposed · **Written:** 2026-09-23 · **`ROADMAP.md` "Next", item 3**

## The question

`guardana monitor` re-probes a deployment on a schedule and compares every cycle
with the first (`core/monitor.py`). Today the comparison is categorical: a new
finding, an escalation, lost coverage, more errors, or an incomparable cycle.
[`paired-regression-statistics.md`](paired-regression-statistics.md) adds rate
regressions and says `monitor` "inherits everything through `compare`". Taken
literally, every cycle then runs a test at the same fixed level against the same
baseline.

Repeated looks at a fixed level do not keep that level. Under no change, the
chance of at least one false alarm grows with every cycle, towards certainty:
p-values "are wholly unreliable if users … continuously monitor"
([arXiv 1512.04922](https://arxiv.org/abs/1512.04922)). The cycles are correlated
through their shared baseline, so the growth is slower than for independent
tests, but it does not stop. A monitor that pages on noise is soon ignored. An
alert that is ignored is worse than no alert, because it looks like coverage.

## Decided now, for row 2: spend the error rate over the cycles

Until the design below is accepted, a rate alert in `monitor` tests cycle *i*
(counting from 1) at

```text
α_i = 6·α / (π²·i²)
```

The sum of α_i over every cycle, however many there are, is exactly α, because
Σ 1/i² = π²/6. The union bound then keeps the chance of any false alarm over an
unbounded schedule at or below the policy's `max_p_value`. It uses only `math`,
it is exact to state, and it needs no assumption about how cycles depend on each
other.

Its cost is power. Cycle 1 tests at 0.61α and cycle 10 at 0.006α, so a regression
that appears late in a long watch must be large before it is reported. `monitor`
states this once at start-up, beside its existing notice about suites below
`min_sample`. A monitor that has quietly become unable to alert is the blind
spot [`production-intake.md`](production-intake.md) names first.

Categorical changes are unaffected. A finding that appears is an observed
failure, not an estimate, and it alerts on the cycle it appears.

## Proposed: a confidence sequence on the paired difference

A confidence sequence is "a sequence of confidence intervals that is uniformly
valid over an unbounded time horizon" ([arXiv 1810.08240](https://arxiv.org/abs/1810.08240)).
For a bounded mean there is a betting construction
([arXiv 2010.09686](https://arxiv.org/abs/2010.09686)). Each cycle contributes its
paired per-case differences against the baseline, each in [−1, 1] and signed so
that positive is worse. The sequence alerts when its lower bound clears
`min_effect`. The same idea has been applied to monitoring deployed models
without raising the false-alarm rate ([arXiv 2110.06177](https://arxiv.org/abs/2110.06177)).
The computation is a running product and a search over a bounded interval, all
with `math`.

It keeps power where alpha-spending loses it, because evidence accumulates
across cycles instead of each cycle being tested alone against a shrinking
threshold.

### Why this is proposed, not accepted

The formula is the easy part. The estimand is not settled yet:

1. **A redeploy changes the hypothesis.** A sequence measures one stable process.
   `monitor` already takes `--deployment-id`. Leaning: a change of deployment id
   ends the sequence, compares the new deployment with the old baseline once, as
   a one-shot paired test, and starts a fresh sequence with a fresh baseline.
2. **The baseline is itself one sample.** Every cycle shares its noise. Leaning:
   the baseline is the pooled first *B* cycles, with *B* declared in the policy,
   instead of cycle 0 alone.
3. **Several suites watched at once.** Each sequence at α gives a family-wise rate
   above α. Leaning: split α evenly across the gated suites, which matches Holm
   in `diff`. Averaging e-values is the more powerful alternative, and it needs a
   reader to understand e-values.
4. **What the operator reads.** "The pass rate is at least 4 points worse than
   baseline, valid at any time" has to be one line a person on call can act on.

## Rejected

**A fixed level on every cycle.** That is the inherited reading of the row 2
design, and it guarantees false alarms in a long enough watch.

**Comparing each cycle with the previous one.** It removes the shared baseline
and misses a slow decline in which every step is below `min_effect`.

**Stopping the watch after the first alarm.** Sequential tests are usually built
to stop. A monitor exists to keep watching, and it keeps reporting after an
alert.

**A Bayesian sequential test.** It is defensible, but a prior is a policy decision
this tool has no standing to make for somebody else's deployment. That is the
reason [`paired-regression-statistics.md`](paired-regression-statistics.md)
already gives.

## See also

- [`paired-regression-statistics.md`](paired-regression-statistics.md): the paired test each cycle runs
- [`repeated-trials.md`](repeated-trials.md): per-case rates, the quantity being watched
- [`guardana-and-control.md`](guardana-and-control.md): why samples of live traffic are Guardana Control's, and synthetic cycles are this rule's
