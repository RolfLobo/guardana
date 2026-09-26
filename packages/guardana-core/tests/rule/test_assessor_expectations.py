"""A built-in assessor's `expect:` fields are checked for type at load, not at grading.

A wrong type would otherwise load, run, and grade every case `inconclusive` — a
rule that looks configured and measures nothing.
"""

from pathlib import Path

import pytest
from guardana.core.rule.errors import RuleLoadError
from guardana.core.rule.yaml_rule import load_yaml_rules


def _rule(tmp_path: Path, evaluator: str, expect: str) -> Path:
    path = tmp_path / "r.yaml"
    path.write_text(
        "id: guardana.prompt.quality.demo\n"
        "title: demo quality check\n"
        "severity: low\n"
        "target_kind: endpoint\n"
        "taxonomy: [LLM09:2025]\n"
        f"evaluator: {evaluator}\n"
        "requires: [chat]\n"
        "prompts: ['What is the capital of France?']\n"
        f"expect: {expect}\n"
    )
    return path


@pytest.mark.parametrize(
    ("evaluator", "expect", "problem"),
    [
        ("contains", '{contains_any: "Paris"}', "contains_any"),
        ("contains", "{contains_all: [Paris, 3]}", "contains_all"),
        ("regex", "{pattern: '('}", "does not compile"),
        ("regex", "{pattern: a, must_match: 'yes'}", "must_match"),
        ("exact_match", "{reference: Paris, normalize: lower}", "normalize"),
        ("exact_match", "{reference: 42}", "reference"),
        ("json_valid", "{required_keys: name}", "required_keys"),
        ("length", "{max_chars: 0}", "max_chars"),
        ("reference_judge", "{reference: [Paris]}", "reference"),
    ],
)
def test_a_field_of_the_wrong_type_fails_at_load(
    tmp_path: Path, evaluator: str, expect: str, problem: str
) -> None:
    with pytest.raises(RuleLoadError, match=problem):
        load_yaml_rules(_rule(tmp_path, evaluator, expect))


@pytest.mark.parametrize(
    ("evaluator", "expect"),
    [
        ("exact_match", "{normalize: casefold}"),
        ("regex", "{must_match: false}"),
        ("reference_judge", "{goal: 'answer'}"),
    ],
)
def test_a_missing_required_field_fails_at_load(
    tmp_path: Path, evaluator: str, expect: str
) -> None:
    with pytest.raises(RuleLoadError, match="requires"):
        load_yaml_rules(_rule(tmp_path, evaluator, expect))


def test_a_field_an_assessor_does_not_read_fails_at_load(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="does not use"):
        load_yaml_rules(_rule(tmp_path, "contains", "{contain_all: [Paris]}"))


@pytest.mark.parametrize(
    ("evaluator", "expect"),
    [
        ("contains", "{contains_all: [Paris], contains_none: [London]}"),
        ("regex", "{pattern: 'Par(is)?', must_match: true}"),
        ("exact_match", "{reference: Paris, normalize: whitespace}"),
        ("json_valid", "{required_keys: [capital]}"),
        ("length", "{max_chars: 200}"),
        ("answered", "{}"),
        ("reference_judge", "{reference: Paris, goal: 'name the capital'}"),
    ],
)
def test_a_well_typed_expectation_loads(tmp_path: Path, evaluator: str, expect: str) -> None:
    rules = load_yaml_rules(_rule(tmp_path, evaluator, expect))
    assert len(rules) == 1
