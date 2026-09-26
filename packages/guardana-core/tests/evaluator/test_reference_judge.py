"""The judge that grades a reply against a reference answer.

It shares `llm_judge`'s sampling and fail-closed parsing, and nothing that would
let one inherit the other's calibration: its own id, its own prompt versions.
"""

import re

import pytest
from guardana.core.evaluator.base import Expectation
from guardana.core.evaluator.llm_judge import LlmJudgeEvaluator
from guardana.core.evaluator.reference_judge import PROMPT_TEMPLATES, ReferenceJudgeEvaluator
from guardana.core.exchange import Exchange
from guardana.core.target import ChatMessage

_EXPECT = Expectation(goal="answer the question", fields={"reference": "Paris"})


def test_the_id_carries_the_prompt_version_and_differs_from_llm_judge() -> None:
    verdict = ReferenceJudgeEvaluator(lambda p: "PASS: same").evaluate(
        Exchange.single_reply("Paris"), _EXPECT
    )
    assert verdict.evaluator_id == "reference_judge@2026.1"
    assert ReferenceJudgeEvaluator.id != LlmJudgeEvaluator.id


def test_a_pass_and_a_fail_are_read_from_the_judge() -> None:
    reply = Exchange.single_reply("Paris")
    passed = ReferenceJudgeEvaluator(lambda p: "PASS: matches").evaluate(reply, _EXPECT)
    failed = ReferenceJudgeEvaluator(lambda p: "**FAIL** - says Lyon").evaluate(reply, _EXPECT)
    assert passed.outcome == "pass"
    assert failed.outcome == "fail"


def test_the_judge_sees_the_reference_the_goal_and_the_reply() -> None:
    asked: list[str] = []

    def judge(prompt: str) -> str:
        asked.append(prompt)
        return "PASS"

    ReferenceJudgeEvaluator(judge).evaluate(Exchange.single_reply("It is Paris."), _EXPECT)
    assert "Paris" in asked[0]
    assert "answer the question" in asked[0]
    assert "It is Paris." in asked[0]


def test_an_unparseable_judge_fails_closed() -> None:
    verdict = ReferenceJudgeEvaluator(lambda p: "hard to say").evaluate(
        Exchange.single_reply("Paris"), _EXPECT
    )
    assert verdict.outcome == "fail"
    assert verdict.confidence == 0.3


def test_confidence_is_the_share_of_samples_that_agreed() -> None:
    replies = iter(["PASS", "PASS", "FAIL", "PASS"])
    verdict = ReferenceJudgeEvaluator(lambda p: next(replies), min_agreement=4).evaluate(
        Exchange.single_reply("Paris"), _EXPECT
    )
    assert verdict.outcome == "pass"
    assert verdict.confidence == 0.75
    assert "raw sample agreement" in verdict.rationale


def test_a_missing_reply_is_inconclusive_and_asks_no_judge() -> None:
    asked: list[str] = []

    def judge(prompt: str) -> str:
        asked.append(prompt)
        return "PASS"

    exchange = Exchange((ChatMessage(role="user", content="capital of France?"),))
    verdict = ReferenceJudgeEvaluator(judge).evaluate(exchange, _EXPECT)
    assert verdict.outcome == "inconclusive"
    assert verdict.confidence == 0.0
    assert asked == []


@pytest.mark.parametrize("fields", [{}, {"reference": ""}, {"reference": ["Paris"]}])
def test_a_missing_or_unusable_reference_is_inconclusive(fields: dict[str, object]) -> None:
    assert ReferenceJudgeEvaluator.check_fields(Expectation(fields=fields)) is not None
    verdict = ReferenceJudgeEvaluator(lambda p: "PASS").evaluate(
        Exchange.single_reply("Paris"), Expectation(fields=fields)
    )
    assert verdict.outcome == "inconclusive"


def test_the_template_names_every_input_and_asks_for_the_verdict_first() -> None:
    template = PROMPT_TEMPLATES["2026.1"]
    for placeholder in ("{reference}", "{text}", "{goal}"):
        assert placeholder in template
    assert "PASS" in template
    assert "FAIL" in template
    assert re.search(r"\b(first|start|begin)", template, re.IGNORECASE)


def test_a_goal_is_optional() -> None:
    verdict = ReferenceJudgeEvaluator(lambda p: "PASS").evaluate(
        Exchange.single_reply("Paris"), Expectation(fields={"reference": "Paris"})
    )
    assert verdict.outcome == "pass"
    assert ReferenceJudgeEvaluator.expects == {"reference": True, "goal": False}


def test_it_is_a_judge_and_keeps_the_identity_it_was_given() -> None:
    evaluator = ReferenceJudgeEvaluator(lambda p: "PASS", judge_identity="model=m1; samples=1")
    assert ReferenceJudgeEvaluator.deterministic is False
    assert evaluator.judge_identity == "model=m1; samples=1"


@pytest.mark.parametrize(
    "kwargs", [{"prompt_version": "2025.1"}, {"min_agreement": 0}, {"judge_identity": " "}]
)
def test_bad_settings_are_refused_at_construction(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 — three settings, three messages
        ReferenceJudgeEvaluator(lambda p: "PASS", **kwargs)  # type: ignore[arg-type]
