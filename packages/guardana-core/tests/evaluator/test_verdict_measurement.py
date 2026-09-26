"""The number behind a verdict: validated once, carried by the evaluators that have one."""

import math

import pytest
from guardana.core.assessment import Direction
from guardana.core.evaluator.amplification import AmplificationEvaluator
from guardana.core.evaluator.base import Expectation, Measurement, Verdict
from guardana.core.evaluator.length import LengthEvaluator
from guardana.core.exchange import Exchange
from guardana.core.target import ChatMessage


def test_a_positional_verdict_still_builds_and_carries_no_measurement() -> None:
    verdict = Verdict("pass", 0.5, "fine", "acme_eval")
    assert verdict.measurement is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"value": math.nan},
        {"value": math.inf},
        {"threshold": -math.inf},
        {"unit": ""},
        {"unit": "   "},
    ],
)
def test_a_measurement_refuses_a_value_it_cannot_compare(kwargs: dict[str, object]) -> None:
    fields: dict[str, object] = {
        "value": 1.0,
        "unit": "chars",
        "direction": Direction.LOWER_IS_BETTER,
        "threshold": 10.0,
    }
    with pytest.raises(ValueError, match="measurement"):
        Measurement(**{**fields, **kwargs})  # type: ignore[arg-type]


def test_a_measurement_refuses_a_direction_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="Direction"):
        Measurement(1.0, "chars", "lower_is_better")  # type: ignore[arg-type]


def test_a_length_verdict_carries_the_reply_length_in_chars() -> None:
    verdict = LengthEvaluator().evaluate(Exchange.single_reply("abcde"), Expectation())
    assert verdict.measurement == Measurement(5.0, "chars", Direction.LOWER_IS_BETTER, 4000.0)


def test_a_failed_length_verdict_carries_its_measurement_too() -> None:
    verdict = LengthEvaluator().evaluate(
        Exchange.single_reply("x" * 12), Expectation(fields={"max_chars": 10})
    )
    assert verdict.outcome == "fail"
    assert verdict.measurement == Measurement(12.0, "chars", Direction.LOWER_IS_BETTER, 10.0)


def test_an_ungraded_length_verdict_measures_nothing() -> None:
    verdict = LengthEvaluator().evaluate(Exchange(()), Expectation())
    assert verdict.measurement is None


def _asked(prompt: str, reply: str) -> Exchange:
    return Exchange(
        (ChatMessage(role="user", content=prompt), ChatMessage(role="assistant", content=reply))
    )


@pytest.mark.parametrize(("reply", "outcome"), [("x" * 30, "pass"), ("x" * 300, "fail")])
def test_an_amplification_verdict_carries_its_ratio(reply: str, outcome: str) -> None:
    verdict = AmplificationEvaluator().evaluate(
        _asked("x" * 10, reply), Expectation(fields={"max_amplification": 20})
    )
    assert verdict.outcome == outcome
    assert verdict.measurement == Measurement(
        len(reply) / 10, "ratio", Direction.LOWER_IS_BETTER, 20.0
    )


def test_an_unbounded_amplification_ceiling_records_no_threshold() -> None:
    verdict = AmplificationEvaluator().evaluate(
        _asked("x" * 10, "x" * 300), Expectation(fields={"max_amplification": math.inf})
    )
    assert verdict.outcome == "pass"
    assert verdict.measurement is not None
    assert verdict.measurement.threshold is None
