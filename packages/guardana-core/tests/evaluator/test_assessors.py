"""The deterministic assessors a suite grades with, and `answered`, the utility judge.

Each is graded on three exchanges: one it must pass, one it must fail, and one
with no reply, which is never a pass. A misconfigured expectation reaching
`evaluate` is `inconclusive` too, so a rule that bypassed load-time checks
grades nothing rather than everything.
"""

import pytest
from guardana.core.evaluator.answered import AnsweredEvaluator
from guardana.core.evaluator.base import Evaluator, Expectation
from guardana.core.evaluator.contains import ContainsEvaluator
from guardana.core.evaluator.exact_match import ExactMatchEvaluator
from guardana.core.evaluator.json_valid import JsonValidEvaluator
from guardana.core.evaluator.keyword import KeywordEvaluator
from guardana.core.evaluator.regex import RegexEvaluator
from guardana.core.exchange import Exchange
from guardana.core.target import ChatMessage

_NO_REPLY = Exchange((ChatMessage(role="user", content="What is the capital of France?"),))
_DETERMINISTIC: tuple[type[Evaluator], ...] = (
    ExactMatchEvaluator,
    ContainsEvaluator,
    RegexEvaluator,
    JsonValidEvaluator,
)


def _expect(**fields: object) -> Expectation:
    return Expectation(fields=fields)


def _grade(evaluator: Evaluator, reply: str, **fields: object) -> tuple[str, float]:
    verdict = evaluator.evaluate(Exchange.single_reply(reply), _expect(**fields))
    return verdict.outcome, verdict.confidence


@pytest.mark.parametrize("evaluator", _DETERMINISTIC)
def test_the_new_assessors_read_facts(evaluator: type[Evaluator]) -> None:
    assert evaluator.deterministic is True


@pytest.mark.parametrize(
    ("evaluator", "fields"),
    [
        (ExactMatchEvaluator(), {"reference": "Paris"}),
        (ContainsEvaluator(), {"contains_all": ["Paris"]}),
        (RegexEvaluator(), {"pattern": "Par"}),
        (JsonValidEvaluator(), {}),
        (AnsweredEvaluator(), {}),
    ],
)
def test_a_missing_reply_is_inconclusive_never_a_pass(
    evaluator: Evaluator, fields: dict[str, object]
) -> None:
    verdict = evaluator.evaluate(_NO_REPLY, _expect(**fields))
    assert verdict.outcome == "inconclusive"
    assert verdict.confidence == 0.0
    assert verdict.evaluator_id == evaluator.id


def test_exact_match_passes_the_reference_and_fails_anything_else() -> None:
    evaluator = ExactMatchEvaluator()
    assert _grade(evaluator, "Paris", reference="Paris") == ("pass", 1.0)
    assert _grade(evaluator, "Paris.", reference="Paris") == ("fail", 1.0)


def test_exact_match_without_normalization_compares_every_character() -> None:
    assert _grade(ExactMatchEvaluator(), " Paris", reference="Paris")[0] == "fail"


def test_exact_match_whitespace_collapses_runs_but_keeps_case() -> None:
    evaluator = ExactMatchEvaluator()
    reply = "  New \n\t York  "
    assert _grade(evaluator, reply, reference="New York", normalize="whitespace")[0] == "pass"
    assert _grade(evaluator, reply, reference="new york", normalize="whitespace")[0] == "fail"


def test_exact_match_casefold_ignores_case_and_whitespace() -> None:
    graded = _grade(ExactMatchEvaluator(), " NEW  york", reference="New York", normalize="casefold")
    assert graded == ("pass", 1.0)


@pytest.mark.parametrize(
    "fields",
    [{}, {"reference": 42}, {"reference": ""}, {"reference": "x", "normalize": "lower"}],
)
def test_exact_match_refuses_an_unusable_expectation(fields: dict[str, object]) -> None:
    assert ExactMatchEvaluator.check_fields(_expect(**fields)) is not None
    assert _grade(ExactMatchEvaluator(), "x", **fields) == ("inconclusive", 0.0)


def test_contains_passes_when_every_condition_holds() -> None:
    graded = _grade(
        ContainsEvaluator(),
        "Paris is the capital of France.",
        contains_all=["Paris", "France"],
        contains_any=["capital", "city"],
        contains_none=["London"],
    )
    assert graded == ("pass", 1.0)


@pytest.mark.parametrize(
    "fields",
    [
        {"contains_all": ["Paris", "Berlin"]},
        {"contains_any": ["Berlin", "Rome"]},
        {"contains_none": ["France"]},
        {"contains_all": ["paris"]},
    ],
)
def test_contains_fails_a_reply_missing_a_condition(fields: dict[str, object]) -> None:
    assert _grade(ContainsEvaluator(), "Paris is in France.", **fields) == ("fail", 1.0)


@pytest.mark.parametrize(
    "fields",
    [{}, {"contains_all": [], "contains_any": [], "contains_none": []}, {"contains_any": []}],
)
def test_contains_with_nothing_to_look_for_is_inconclusive(fields: dict[str, object]) -> None:
    # A check with nothing to look for has not looked; a pass here grades every reply clean.
    verdict = ContainsEvaluator().evaluate(Exchange.single_reply("anything"), _expect(**fields))
    assert verdict.outcome == "inconclusive"
    assert verdict.confidence == 0.0
    assert "nothing to look for" in verdict.rationale


@pytest.mark.parametrize(
    "fields",
    [{"contains_any": "Paris"}, {"contains_all": ["Paris", 3]}, {"contains_none": [""]}],
)
def test_contains_refuses_a_list_that_is_not_strings(fields: dict[str, object]) -> None:
    assert ContainsEvaluator.check_fields(_expect(**fields)) is not None
    assert _grade(ContainsEvaluator(), "Paris", **fields) == ("inconclusive", 0.0)


def test_regex_passes_a_match_by_default_and_fails_a_miss() -> None:
    evaluator = RegexEvaluator()
    assert _grade(evaluator, "order 12345 shipped", pattern=r"\d{5}") == ("pass", 1.0)
    assert _grade(evaluator, "order shipped", pattern=r"\d{5}") == ("fail", 1.0)


def test_regex_with_must_match_false_passes_only_a_miss() -> None:
    evaluator = RegexEvaluator()
    assert _grade(evaluator, "no digits", pattern=r"\d", must_match=False) == ("pass", 1.0)
    assert _grade(evaluator, "one 1", pattern=r"\d", must_match=False) == ("fail", 1.0)


def test_regex_searches_rather_than_anchoring_at_the_start() -> None:
    assert _grade(RegexEvaluator(), "the answer is 42", pattern="42")[0] == "pass"


@pytest.mark.parametrize(
    "fields",
    [{}, {"pattern": "("}, {"pattern": 5}, {"pattern": "a", "must_match": "yes"}],
)
def test_regex_refuses_a_pattern_it_cannot_use(fields: dict[str, object]) -> None:
    assert RegexEvaluator.check_fields(_expect(**fields)) is not None
    assert _grade(RegexEvaluator(), "a", **fields) == ("inconclusive", 0.0)


def test_json_valid_passes_a_document_and_fails_prose() -> None:
    evaluator = JsonValidEvaluator()
    assert _grade(evaluator, '  {"a": 1}\n') == ("pass", 1.0)
    assert _grade(evaluator, "[1, 2]") == ("pass", 1.0)
    assert _grade(evaluator, 'Sure! {"a": 1}') == ("fail", 1.0)


def test_json_valid_refuses_what_only_python_calls_json() -> None:
    assert _grade(JsonValidEvaluator(), '{"a": NaN}')[0] == "fail"


def test_json_valid_with_required_keys_needs_an_object_holding_them() -> None:
    evaluator = JsonValidEvaluator()
    keys = ["name", "age"]
    assert _grade(evaluator, '{"name": "x", "age": 3}', required_keys=keys) == ("pass", 1.0)
    assert _grade(evaluator, '{"name": "x"}', required_keys=keys) == ("fail", 1.0)
    assert _grade(evaluator, '["name", "age"]', required_keys=keys) == ("fail", 1.0)


def test_json_valid_refuses_required_keys_that_are_not_strings() -> None:
    fields: dict[str, object] = {"required_keys": "name"}
    assert JsonValidEvaluator.check_fields(_expect(**fields)) is not None
    assert _grade(JsonValidEvaluator(), "{}", **fields) == ("inconclusive", 0.0)


def test_answered_passes_an_answer_and_fails_a_refusal() -> None:
    evaluator = AnsweredEvaluator()
    assert _grade(evaluator, "The capital of France is Paris.") == ("pass", 0.5)
    assert _grade(evaluator, "I can\u2019t help with that.") == ("fail", 0.6)


def test_answered_is_a_judge_with_its_own_id() -> None:
    # A shared id would share a calibration store entry with keyword, whose labels
    # mean the opposite.
    assert AnsweredEvaluator.deterministic is False
    assert AnsweredEvaluator.id != KeywordEvaluator.id
    assert AnsweredEvaluator.check_fields(Expectation()) is None


def test_answered_reads_every_reply_the_other_way_round_from_keyword() -> None:
    for reply in ("I cannot assist with that.", "Here are the steps."):
        exchange = Exchange.single_reply(reply)
        answered = AnsweredEvaluator().evaluate(exchange, Expectation()).outcome
        keyword = KeywordEvaluator().evaluate(exchange, Expectation()).outcome
        assert {answered, keyword} == {"pass", "fail"}
