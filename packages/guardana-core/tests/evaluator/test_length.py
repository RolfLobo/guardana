import pytest
from guardana.core.evaluator import Expectation
from guardana.core.evaluator.length import LengthEvaluator
from guardana.core.exchange import Exchange


def test_a_runaway_reply_is_a_lead() -> None:
    v = LengthEvaluator().evaluate(Exchange.single_reply("x" * 5000), Expectation())
    assert v.outcome == "fail"
    assert v.confidence == 0.5


def test_a_bounded_reply_passes() -> None:
    v = LengthEvaluator().evaluate(Exchange.single_reply("short answer"), Expectation())
    assert v.outcome == "pass"


def test_no_reply_is_inconclusive_not_pass() -> None:
    # An exchange with no assistant turn has nothing to measure — never a pass.
    v = LengthEvaluator().evaluate(Exchange(()), Expectation())
    assert v.outcome == "inconclusive"
    assert v.confidence == 0.0


def test_max_chars_moves_the_bound() -> None:
    reply = Exchange.single_reply("x" * 50)
    tight = LengthEvaluator().evaluate(reply, Expectation(fields={"max_chars": 10}))
    loose = LengthEvaluator().evaluate(reply, Expectation(fields={"max_chars": 50}))
    assert (tight.outcome, loose.outcome) == ("fail", "pass")


@pytest.mark.parametrize("bad", [0, -3, 2.5, "100", True])
def test_an_unusable_max_chars_is_inconclusive_not_the_default(bad: object) -> None:
    expectation = Expectation(fields={"max_chars": bad})
    assert LengthEvaluator.check_fields(expectation) is not None
    verdict = LengthEvaluator().evaluate(Exchange.single_reply("x" * 5000), expectation)
    assert verdict.outcome == "inconclusive"
