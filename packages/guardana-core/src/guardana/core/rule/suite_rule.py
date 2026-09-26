"""A quality suite: every case of a versioned dataset, sent K times, gated on its pass rate.

The fourth declarative shape, picked by `dataset:`. It grades each reply with an ordinary
evaluator, records one assessment per trial with the pass included, and yields at most
one finding, about the rate rather than a case. Why, and what was rejected:
[`docs/design/quality-suites.md`](../../../../../../docs/design/quality-suites.md).
"""

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from functools import cache

from guardana.core.assessment import Assessment, from_verdict
from guardana.core.budget import BudgetExhausted
from guardana.core.calibration.corpus import bundled_corpus
from guardana.core.calibration.store import corpus_digest
from guardana.core.evaluator.base import Expectation, Verdict
from guardana.core.exchange import Exchange
from guardana.core.manifest.records import SuiteOutcome, SuiteSummary
from guardana.core.report import Evidence, Finding
from guardana.core.rule.base import Rule, RuleContext, RuleMeta
from guardana.core.rule.errors import RuleError, RuleLoadError
from guardana.core.rule.fixture import DeclaredFixture, RuleFixture, materialise
from guardana.core.suite import SuiteGate, describe, measure_suite
from guardana.core.target import ChatMessage, Target
from guardana.core.target.protocols import ChatEndpoint
from guardana.core.trials import check_trials

_EVIDENCE_CASES = 3
"""How many failing cases a finding quotes: enough to act on, few enough to read."""


@dataclass(frozen=True, slots=True)
class SuiteCase:
    """One case of a suite, ready to send: its identity, its messages and its yardstick."""

    case_id: str
    messages: tuple[ChatMessage, ...]
    expectation: Expectation
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SuiteRule(Rule):
    """A dataset of cases sent to a chat endpoint and gated on the share that pass."""

    meta: RuleMeta
    cases: tuple[SuiteCase, ...]
    """The cases this suite sends, after sampling."""

    gate: SuiteGate
    dataset: str
    """The dataset's declared identity, `name@version`, recorded on every assessment."""

    dataset_digest: str
    sample: tuple[int, int] | None = None
    """(size, seed) when a subset of the dataset runs; None when every case does."""

    source_digest: str = ""
    """Hash of the declaration and the dataset file; see `Rule.digest`."""

    declared_fixtures: tuple[RuleFixture | DeclaredFixture, ...] = ()
    trials_per_case: int = 1

    def fixtures(self) -> Iterable[RuleFixture]:
        """Build this suite's samples, each with a fresh double."""
        return materialise(self.declared_fixtures)

    def digest(self) -> str:
        """Return the declaration and dataset hash, falling back to the metadata-only default."""
        return self.source_digest or Rule.digest(self)

    @property
    def estimated_requests(self) -> int:
        """One request per case per trial: every case is sent every time, none is skipped."""
        return len(self.cases) * self.trials_per_case

    def with_trials(self, trials: int) -> "Rule | None":
        """Send every case `trials` times: a pass rate over one sampled reply is one draw."""
        return replace(self, trials_per_case=check_trials(trials))

    def declared_expectations(self) -> Iterable[tuple[str, Expectation]]:
        """Report every case's expectation, so a third-party evaluator's contract is checked."""
        evaluator = self.meta.evaluator or ""
        return ((evaluator, case.expectation) for case in self.cases)

    def run(self, target: Target, ctx: RuleContext) -> Iterable[Finding]:
        """Send each case once per trial, record every grade, and yield the gate's finding.

        Nothing is yielded when the suite passes: the passes are in the assessment
        channel and in the conclusion handed to `ctx.conclude`. A suite that raises
        before it concludes still concludes, as declined, so an error never leaves its
        demand unanswered; a spent budget is a stop, and the run says so itself.
        """
        # A context can outlive one run (fixtures share one), so the suite reads only what
        # it recorded itself.
        start = len(ctx.recorded())
        try:
            yield from self._measure(target, ctx, start)
        except BudgetExhausted:
            raise
        except Exception as exc:
            ctx.conclude(self._unfinished(ctx, start, exc))
            raise

    def _unfinished(self, ctx: RuleContext, start: int, exc: Exception) -> SuiteSummary:
        summary = self._summary(ctx, ctx.recorded()[start:])
        return replace(
            summary,
            outcome=SuiteOutcome.INCONCLUSIVE,
            reason=f"suite did not finish: {type(exc).__name__}: {exc}",
        )

    def _summary(self, ctx: RuleContext, recorded: Sequence[Assessment]) -> SuiteSummary:
        return measure_suite(
            recorded,
            rule_id=self.meta.id,
            case_ids=[case.case_id for case in self.cases],
            trials_per_case=self.trials_per_case,
            gate=self.gate,
            dataset=self.dataset,
            dataset_digest=self.dataset_digest,
            evaluators=ctx.evaluators,
            calibrations=ctx.calibrations,
            sample=self.sample,
            starter_digest=_starter_digest(),
        )

    def _measure(self, target: Target, ctx: RuleContext, start: int) -> Iterable[Finding]:
        if not isinstance(target, ChatEndpoint):
            raise RuleError(f"{self.meta.id} needs a chat endpoint, got {type(target).__name__}")
        evaluator_id = self.meta.evaluator or ""
        evaluator = ctx.evaluators.get(evaluator_id)
        if evaluator is None:
            raise RuleLoadError(f"unknown evaluator: {evaluator_id!r}")
        failing: dict[str, str] = {}
        for case in self.cases:
            for trial in range(1, self.trials_per_case + 1):
                reply = target.chat(list(case.messages))
                exchange = Exchange((*case.messages, ChatMessage(role="assistant", content=reply)))
                verdict = evaluator.evaluate(exchange, case.expectation)
                ctx.record(
                    from_verdict(
                        verdict,
                        case_id=case.case_id,
                        subject_ref=target.ref,
                        rule_id=self.meta.id,
                        dataset=self.dataset,
                        tags=case.tags,
                        trial=trial,
                    )
                )
                if verdict.outcome == "fail" and len(failing) < _EVIDENCE_CASES:
                    failing.setdefault(case.case_id, reply)
        recorded = ctx.recorded()[start:]
        summary = self._summary(ctx, recorded)
        ctx.conclude(summary)
        if summary.outcome is not SuiteOutcome.PASS:
            assessor = summary.correction.assessor or next(
                (a.assessor for a in recorded), evaluator_id
            )
            yield self._finding(summary, failing, assessor, target.ref)

    def _finding(
        self, summary: SuiteSummary, failing: dict[str, str], assessor: str, target_ref: str
    ) -> Finding:
        declined = summary.outcome is SuiteOutcome.INCONCLUSIVE
        statement = describe(summary)
        return Finding(
            rule_id=self.meta.id,
            severity=self.meta.severity,
            title=self.meta.title,
            taxonomy=self.meta.taxonomy,
            target_ref=target_ref,
            evidence=Evidence(summary=statement, detail=_failing_cases(failing)),
            # Certain when it failed: the verdict is a comparison of a measured rate with
            # the bar, and a lower number would let a policy's `min_confidence` drop it.
            verdict=Verdict(
                outcome="inconclusive" if declined else "fail",
                confidence=0.0 if declined else 1.0,
                rationale=statement,
                evaluator_id=assessor,
            ),
        )


def _failing_cases(failing: dict[str, str]) -> str:
    return "\n".join(f"{case_id}: {reply}" for case_id, reply in failing.items())


def select_sample(cases: Sequence[SuiteCase], size: int, seed: int) -> tuple[SuiteCase, ...]:
    """Choose `size` cases by a hash of the seed and each case id, keeping dataset order.

    A hash rather than `random.sample`, whose algorithm is not promised across Python
    versions: the same seed must choose the same cases on every build.
    """
    ranked = sorted(
        cases,
        key=lambda case: hashlib.sha256(f"{seed}:{case.case_id}".encode()).hexdigest(),
    )
    chosen = {case.case_id for case in ranked[:size]}
    return tuple(case for case in cases if case.case_id in chosen)


@cache
def _starter_digest() -> str:
    """Return the digest of the bundled starter corpus, which never corrects a real run."""
    return corpus_digest(bundled_corpus())
