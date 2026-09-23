import math
from collections.abc import Callable

from guardana.core.assessment import AssessmentStatus
from guardana.core.manifest import RunManifest
from guardana.core.manifest.records import TrialSummary
from guardana.core.report import Finding, ScanResult
from guardana.core.trials import CONFIDENCE, wilson_interval

_ICON = {"CRITICAL": "✖", "HIGH": "✖", "MEDIUM": "▲", "LOW": "•", "INFO": "·"}


class HumanRenderer:
    """Terminal output: one line per finding, what each repeating rule rests on, a summary."""

    name = "human"

    def __init__(self, run: RunManifest | None = None) -> None:
        self._run = run

    def render(self, result: ScanResult) -> str:
        """Render one scan result to text."""
        lines = []
        for f in result.findings:
            icon = _ICON.get(f.severity.name, "•")
            lines.append(f"{icon} [{f.severity.name}] {f.rule_id} — {f.title}")
            lines.append(f"    {f.evidence.summary}  ({f.target_ref})")
        if not result.findings:
            lines.append(_nothing_found(result))
        for f in result.unverified:
            lines.append(f"? [UNVERIFIED] {f.rule_id} — {f.title}")
            lines.append(f"    {_why_unverified(f)}  ({f.target_ref})")
        for f in result.waived:
            lines.append(f"~ [WAIVED] {f.rule_id} — {f.title}")
            lines.append(f"    {f.evidence.summary}  ({f.target_ref})")
        # Distinct from a finding (a check ran and found something) and from
        # unverified (a check ran and could not tell). This one never ran.
        for e in result.errors:
            lines.append(f"! [ERROR] {e.source} — check did not run ({e.stage})")
            lines.append(f"    {e.reason}")
        # Named in the report and not only on stderr: the report outlives the terminal
        # that printed it, and one that says `indeterminate` without saying which
        # evidence was missing leaves the reader with a verdict and no next step.
        for gap in result.coverage_shortfall:
            lines.append(f"! [COVERAGE] {gap.name} — demanded, and not available ({gap.kind})")
            lines.append(f"    {gap.detail}")
        trials = _trials_block(result, self._run)
        if trials:
            lines.append("")
            lines.extend(trials)
        lines.append("")
        lines.append(_summary(result))
        return "\n".join(lines)


def _trials_block(result: ScanResult, run: RunManifest | None) -> list[str]:
    """Say what each repeating rule's result rests on: its cases, its trials, its bound.

    Read from the summary the engine stored, never recomputed here, so a saved run
    prints the verdict it was written with. Without a manifest there is nothing
    stored to read, and nothing is printed rather than something re-derived.
    """
    if run is None:
        return []
    repeating = [(r.id, r.trial_summary) for r in run.rules if r.trial_summary is not None]
    asked = run.execution.trials
    once = [r.id for r in run.rules if r.trial_summary is None]
    if not repeating:
        if asked > 1 and once:
            return [f"Trials: {asked} asked for, and no rule in this run repeats a case"]
        return []
    assessors: dict[str, set[str]] = {}
    for assessment in result.assessments:
        assessors.setdefault(assessment.rule_id, set()).add(assessment.assessor)
    lines = ["Trials"]
    lines.extend(
        f"  {rule_id}  {_trials_line(summary, _named(assessors.get(rule_id, set())))}"
        for rule_id, summary in repeating
    )
    if asked > 1 and once:
        lines.append(f"  one attempt per case, whatever was asked: {', '.join(once)}")
    # A bound here is over each rule's own fixed prompts; read as robustness against an
    # attacker who adapts, it would be a claim no run made.
    lines.append("  static prompt set · no adaptive attacker ran")
    return lines


def _trials_line(summary: TrialSummary, assessors: str) -> str:
    k = summary.trials_per_case
    each = f"in {k} trial{'s' if k != 1 else ''} each"
    graded = f"graded by {assessors}, grader error not corrected"
    if summary.bound is not None:
        return (
            f"clean · 0 of {summary.cases} cases {each} · "
            f"ASR@{k} ≤ {_up(summary.bound)}% ({_percent(CONFIDENCE)}%) · {graded}"
        )
    parts = []
    if summary.cases_failed:
        decided = summary.cases - summary.cases_incomplete
        low, high = wilson_interval(summary.cases_failed, decided)
        parts.append(
            f"{summary.cases_failed} of {summary.cases} cases failed {each} · "
            f"ASR@{k} {_percent(summary.cases_failed / decided)}% "
            f"({_percent(CONFIDENCE)}% CI {_down(low)} to {_up(high)}%)"
        )
        if k > 1 and summary.mean_success_rate is not None:
            parts.append(f"mean failure rate per trial {_percent(summary.mean_success_rate)}%")
    if summary.cases_incomplete:
        parts.append(
            f"not clean: {summary.cases_incomplete} of {summary.cases} cases incomplete, "
            f"a trial could not be graded"
        )
    if not parts:
        parts.append(
            f"no bound: the rule reported a finding its {summary.cases} recorded case(s) "
            f"do not show"
        )
    parts.append(graded)
    return " · ".join(parts)


def _named(assessors: set[str]) -> str:
    return ", ".join(sorted(assessors)) if assessors else "an unnamed assessor"


def _percent(value: float) -> str:
    return f"{value * 100:.1f}".removesuffix(".0")


def _up(value: float) -> str:
    """Round a bound up at one decimal: a printed bound must never claim more than was shown."""
    return _percent(math.ceil(value * 1000 - 1e-9) / 1000)


def _down(value: float) -> str:
    return _percent(math.floor(value * 1000 + 1e-9) / 1000)


_NOT_AN_ALL_CLEAR: tuple[
    tuple[Callable[[ScanResult], object], Callable[[ScanResult], str]], ...
] = (
    # Every rule ran and every one declined — an endpoint answering with an empty
    # message, a trace cut short. The count above is not zero, which is the only
    # reason this needs a line of its own.
    (
        lambda r: r.verified_nothing,
        lambda r: f"not one of the {r.rules_run_count} check(s) that ran could reach a verdict",
    ),
    (
        lambda r: r.coverage_shortfall,
        lambda r: f"{len(r.coverage_shortfall)} piece(s) of demanded coverage were not available",
    ),
    (lambda r: r.errors, lambda r: f"{len(r.errors)} check(s) could not run"),
    # The quietest of the six, and the one that arrives in bulk: a model store whose
    # checkpoints this build cannot parse produces no findings at all and every one
    # of them lands here. A tick over "I could not read your model" is the whole
    # failure this tool is built to refuse, printed in green.
    (
        lambda r: r.unverified,
        lambda r: f"{len(r.unverified)} check(s) ran and could not reach a verdict",
    ),
)


def _nothing_found(result: ScanResult) -> str:
    """Say what "no findings" means here — a tick only when it means an all-clear.

    Six ways a clean report is not a clean result, ordered by how completely each
    one invalidates the run. The tick is what people scroll for and what job summaries
    grep for, so every one of these is a line that denies it in words.
    """
    if not result.rules_run:
        return "⚠ 0 rules ran — nothing was checked (this is not an all-clear)."
    # Its own branch rather than a row in the table below, because the message needs
    # the value the condition just proved is there. The exit code already says `6`,
    # and nobody reads an exit code off a terminal: a tick over a run that ended
    # after two rules is the same false green as a tick over a rule that crashed.
    if result.stopped_by is not None:
        return (
            f"⚠ No findings, but the run stopped early ({result.stopped_by.value}) "
            "before finishing its plan (this is not an all-clear)."
        )
    for applies, message in _NOT_AN_ALL_CLEAR:
        if applies(result):
            return f"⚠ No findings, but {message(result)} (this is not an all-clear)."
    return "✓ No findings."


def _why_unverified(finding: Finding) -> str:
    """Both halves of why a check could not tell, because either can be the specific one.

    An artifact rule's summary names the member or the cap it hit while its rationale
    is one sentence written per rule; a graded rule is the other way round, with the
    reason the judge failed in the rationale. Preferring one loses the part a reader
    can act on, in whichever direction it was chosen.
    """
    summary = finding.evidence.summary
    rationale = finding.verdict.rationale if finding.verdict is not None else ""
    if not rationale or rationale in summary:
        return summary or rationale
    return f"{summary} — {rationale}" if summary else rationale


def _summary(result: ScanResult) -> str:
    summary = (
        f"{len(result.findings)} finding(s); "
        f"{result.rules_run_count} rule(s) run, {len(result.rules_skipped)} skipped."
    )
    if result.unverified:
        summary += f" {len(result.unverified)} unverified."
    if result.waived:
        summary += f" {len(result.waived)} waived."
    if result.errors:
        summary += f" {len(result.errors)} check(s) could not run."
    if result.coverage_shortfall:
        summary += f" {len(result.coverage_shortfall)} coverage demand(s) unmet."
    if result.assessments:
        # Both numbers, never the rate. "12 measured" beside "40 cases" is what
        # stops a pass rate over the three cases a broken judge still graded from
        # reading like a pass rate over all of them. Counted in cases, so K trials
        # of one prompt read as one case.
        cases, measured, ungraded = _case_counts(result)
        summary += (
            f" {measured}/{cases} case(s) measured{f', {ungraded} ungraded' if ungraded else ''}."
        )
    if result.observations:
        # Says what the run actually looked at, so "no findings" reads as "nothing
        # wrong in these N components" rather than the ambiguous "nothing here".
        summary += f" {len(result.observations)} component(s) observed."
    if result.stopped_by is not None:
        # Last, so it is the note the summary ends on — this line is what a CI job
        # summary quotes, and the rule counts above it describe a plan that was
        # never finished.
        summary += f" Run stopped early: {result.stopped_by.value}."
    return summary


def _case_counts(result: ScanResult) -> tuple[int, int, int]:
    """Count cases, cases whose every trial was measured, and cases with an ungraded trial."""
    statuses: dict[tuple[str, str], list[AssessmentStatus]] = {}
    for a in result.assessments:
        statuses.setdefault((a.rule_id, a.case_id), []).append(a.status)
    measured = sum(all(s is AssessmentStatus.MEASURED for s in v) for v in statuses.values())
    ungraded = sum(AssessmentStatus.INCONCLUSIVE in v for v in statuses.values())
    return len(statuses), measured, ungraded
