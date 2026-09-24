"""Which evaluators are judges, and what stands behind a judge's verdict.

A deterministic evaluator states a fact about the reply; a judge states an opinion
whose error rate has to be measured before a rate it graded can be corrected. An
evaluator that does not say which it is counts as a judge: claiming determinism by
default would let a third-party opinion skip the correction.
"""

import pytest
from guardana.core.evaluator.amplification import AmplificationEvaluator
from guardana.core.evaluator.base import Evaluator, Expectation, Verdict
from guardana.core.evaluator.canary import CanaryEvaluator
from guardana.core.evaluator.guard import GuardEvaluator
from guardana.core.evaluator.keyword import KeywordEvaluator
from guardana.core.evaluator.length import LengthEvaluator
from guardana.core.evaluator.llm_judge import LlmJudgeEvaluator
from guardana.core.evaluator.tool_call import ToolCallEvaluator
from guardana.core.exchange import Exchange
from guardana.core.registry import Registry


class _UndeclaredEvaluator(Evaluator):
    """A third-party evaluator that says nothing about how it grades."""

    id = "acme_undeclared"

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        """Pass everything; the verdict is irrelevant here."""
        return Verdict("pass", 0.5, "canned", self.id)


def _judge(prompt: str) -> str:
    return "PASS: fine"


def test_an_evaluator_that_does_not_declare_determinism_is_a_judge() -> None:
    assert _UndeclaredEvaluator.deterministic is False
    assert _UndeclaredEvaluator().judge_identity is None


@pytest.mark.parametrize(
    "evaluator",
    [CanaryEvaluator, LengthEvaluator, AmplificationEvaluator, ToolCallEvaluator],
)
def test_the_evaluators_that_read_facts_are_deterministic(evaluator: type[Evaluator]) -> None:
    assert evaluator.deterministic is True


@pytest.mark.parametrize("evaluator", [KeywordEvaluator, LlmJudgeEvaluator, GuardEvaluator])
def test_keyword_llm_judge_and_guard_are_judges(evaluator: type[Evaluator]) -> None:
    assert evaluator.deterministic is False


def test_every_registered_builtin_evaluator_is_classified() -> None:
    evaluators = Registry.discover().evaluators()
    deterministic = {eid for eid, ev in evaluators.items() if ev.deterministic}
    assert deterministic == {"canary", "length", "amplification", "tool_call"}


def test_an_llm_judge_keeps_the_identity_it_was_given() -> None:
    identity = "model=m1; endpoint=3f2a; samples=3"
    evaluator = LlmJudgeEvaluator(judge=_judge, judge_identity=identity)
    assert evaluator.judge_identity == identity


def test_an_llm_judge_given_no_identity_states_none() -> None:
    assert LlmJudgeEvaluator(judge=_judge).judge_identity is None


def test_a_guard_keeps_the_identity_it_was_given() -> None:
    evaluator = GuardEvaluator(lambda text: "safe", judge_identity="model=g1; endpoint=9c0d")
    assert evaluator.judge_identity == "model=g1; endpoint=9c0d"
    assert GuardEvaluator(lambda text: "safe").judge_identity is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_judge_identity_is_refused(blank: str) -> None:
    # Two blank identities would compare equal and match two different judges.
    with pytest.raises(ValueError, match="judge_identity"):
        LlmJudgeEvaluator(judge=_judge, judge_identity=blank)
    with pytest.raises(ValueError, match="judge_identity"):
        GuardEvaluator(lambda text: "safe", judge_identity=blank)


def test_the_deterministic_evaluators_state_no_judge_identity() -> None:
    for evaluator in (CanaryEvaluator(), LengthEvaluator(), ToolCallEvaluator()):
        assert evaluator.judge_identity is None
