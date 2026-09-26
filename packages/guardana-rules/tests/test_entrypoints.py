from guardana.core.registry import Registry
from guardana.rules import provide_evaluators


def test_discover_loads_rules_entrypoint_without_error() -> None:
    # guardana-rules registers a `guardana.rules` entry point; discovery must succeed
    reg = Registry.discover()
    assert isinstance(reg.rules(), tuple)


def test_the_suite_assessors_ship_with_the_built_in_evaluators() -> None:
    ids = {evaluator.id for evaluator in provide_evaluators()}
    assert {"exact_match", "contains", "regex", "json_valid", "answered"} <= ids


def test_the_judges_that_need_a_model_are_not_provided_bare() -> None:
    ids = {evaluator.id for evaluator in provide_evaluators()}
    assert not ids & {"llm_judge", "reference_judge", "guard"}
