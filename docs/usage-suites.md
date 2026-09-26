---
title: "Quality suites"
nav_order: 255
summary: "quality suites: gate a deployed endpoint against a versioned golden dataset before release or in CI"
status: beta
---

# Quality suites

A quality suite checks whether a deployed support bot or RAG endpoint still answers a golden set before release or in CI. It is a declarative rule graded against a versioned dataset. It does not read production traffic; production traffic monitoring belongs to Guardana Control, a separate product.

## Dataset and rule

The first nonblank line of the JSONL dataset is this header:

```json
{"guardana_dataset": 1, "name": "support-golden", "version": "2026.09"}
```

Each later nonblank line is a case. The case fields are:

| Key | Meaning |
|---|---|
| `input` | Required. A nonempty string or a messages object whose last message is from the user. |
| `expect` | Optional evaluator fields for that case, overlaid on the rule's default expectation. |
| `tags` | Optional list of strings. A tag starting with `sample:` is refused. |

This rule grades the dataset and gates its pass rate:

```yaml
id: acme.quality.support_answers
title: The support bot still answers the golden set
severity: high
target_kind: endpoint
taxonomy: [LLM09:2025]
evaluator: contains
requires: [chat]
dataset: ./support-golden.jsonl
expect:
  contains_any: []
sample:
  size: 100
  seed: 7
gate:
  min_pass_rate: 0.90
  min_sample: 30
fixtures:
  - name: every answer names the setting
    dataset: ./fixtures/answers-pass.jsonl
    outcome: clean
  - name: a third of the answers miss it
    dataset: ./fixtures/answers-mixed.jsonl
    outcome: finding
  - name: the model says nothing
    reply: ""
    outcome: inconclusive
```

Fill in the evaluator's expectation before running this example: `contains` returns `inconclusive` when every substring list is empty. See [writing rules](writing-rules.md) for the rule shape.

## Run and read the suite

Run the rule with [`guardana probe`](usage-probe.md). The profile's `trials` or `probe --trials` sets how many times each case is sent. `guardana plan probe` prices cases × K target requests; it does not price judge calls.

The human report has a Measured block. A passing line can read:

```text
Measured
  acme.quality.support_answers  support-golden@2026.09: 100 of 100 cases measured, 3 trials each · pass rate 98.7% (95% CI 94 to 99.8%) · bar 90% · at or above the bar
```

A case is measured when all its planned trials were graded. Each case contributes its share of passed trials. The pass rate is the mean of those shares, so the interval is over cases rather than pooled trials. Ungraded trials stay in the denominator: `worst` counts them as failures, and `best` counts them as passes. The interval uses a 95% Wilson lower limit at `worst` and upper limit at `best`; it is conservative and does not collapse to a point when cases agree.

| Gate answer | Condition | Exit |
|---|---|---|
| Pass | `worst` meets `min_pass_rate`. | `0` |
| Fail | `best` is below `min_pass_rate`. | `1` |
| Decline | Fewer than `min_sample` cases were measured, ungraded trials could put the rate on either side of the bar, a judge's error could not be corrected (below), or the suite raised before it concluded. | `2` |

A failed suite produces one finding about the rate, whatever its severity. A declined suite produces one `unverified` entry and makes the run `indeterminate`. See [exit codes](exit-codes.md).

## Judge-graded suites

`answered` checks whether a reply to a benign task contains a refusal marker. `reference_judge` grades a reply against a reference answer. Both are judge assessors, so their rates need judge-error correction. A suite without a usable calibration declines with `uncorrected — <reason>`. Record one with [`guardana calibrate --record`](usage-calibrate.md).

A usable calibration has the same assessor and judge identity, per-class counts, and no starter corpus. It needs at least 30 graded samples in each class, abstention below half in each class, Youden's J of at least 0.1, and observed failures above the calibrated false-alarm rate. Every corner of its sensitivity/specificity 95% box must have sensitivity plus specificity greater than 1. A corrected rate uses the same gate test; when raw `worst` is below the bar, a pass also needs the corrected 95% lower limit to clear it.

## Sampling and fixtures

`sample: {size, seed}` selects a repeatable subset. Both values are whole numbers, and `seed` is required with `size`. The same seed selects the same cases across builds and Python versions. A size at or above the case count runs every case.

A `reply:` fixture answers every case with one reply. A fixture can use its own `dataset:` to supply cases and their replies. See [testing rules](usage-rule-test.md).

## Saved runs and limits

The saved run includes a suite summary; see [suite summaries](usage-run.md#suite-summaries) for its fields. Extension authors can see [extending Guardana](extending.md), and the [suite design](design/quality-suites.md) gives the design context.

- Numeric measurements are recorded and rendered, but there is no gate on their aggregate.
- `plan probe` does not price judge calls, which K and `min_agreement` multiply.
- `diff` pairs cases across runs but does not test a suite's rate statistically.
- A file holds one calibration per evaluator id.
