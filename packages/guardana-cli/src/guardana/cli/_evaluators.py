"""Build config-driven evaluators (the LLM judges and the guard) and register them.

The judge's differentiating value is that it grades "did the attack succeed" — but
it needs a model to ask, and nothing built one from config until here. Both the
judge and the optional guard model are ordinary endpoints, so they can point at a
local OpenAI-compatible server for fully offline grading. Absent config leaves an
evaluator unregistered, and a rule that names it is then skipped visibly by the
runner — never a silent pass.
"""

import os
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

from guardana.cli._endpoint import build_endpoint
from guardana.core.budget import Budgets
from guardana.core.evaluator.guard import GuardEvaluator
from guardana.core.evaluator.llm_judge import JudgeCalibration, LlmJudgeEvaluator
from guardana.core.evaluator.reference_judge import ReferenceJudgeEvaluator
from guardana.core.fingerprint import digest_of
from guardana.core.profile import Profile
from guardana.core.profile.errors import ProfileError
from guardana.core.registry import Registry
from guardana.core.target import ChatMessage

_DEFAULT_PROMPT_VERSION = "2025.1"
_DEFAULT_PORTS = {"https": 443, "http": 80}


def wire_config_evaluators(
    registry: Registry, profile: Profile, budgets: Budgets | None = None
) -> None:
    """Register every evaluator that must be built from `guardana.yaml` config.

    `llm_judge` and `reference_judge` share one judge model, built from
    `evaluators.llm_judge`; `guard` is an optional safety classifier. Call after
    discovery so they join the evaluator set the runner resolves every rule against.

    `budgets` bounds every judge and guard call on a meter of the model's own, so a
    judge-graded run stops at the ceiling like its target instead of spending past it.
    `None` leaves them unbounded. A token ceiling the judge's transport cannot enforce
    raises `BudgetExhausted` here, before anything is sent.
    """
    judge_cfg = profile.evaluator_config.get("llm_judge")
    if judge_cfg is not None:
        for evaluator in _build_judges(judge_cfg, budgets):
            registry.register_evaluator(evaluator)
    guard_cfg = profile.evaluator_config.get("guard")
    if guard_cfg is not None:
        registry.register_evaluator(
            GuardEvaluator(
                _endpoint_call(guard_cfg, "guard", budgets),
                judge_identity=_identity(guard_cfg, "guard"),
            )
        )


def _build_judges(
    cfg: Mapping[str, object], budgets: Budgets | None
) -> tuple[LlmJudgeEvaluator, ReferenceJudgeEvaluator]:
    """Build the security judge and the reference judge on one judge model and one meter."""
    judge = _endpoint_call(cfg, "llm_judge", budgets)
    version = cfg.get("prompt_version", _DEFAULT_PROMPT_VERSION)
    if not isinstance(version, str):
        raise ProfileError("evaluators.llm_judge.prompt_version must be a string")
    min_agreement = cfg.get("min_agreement", 1)
    # `bool` is an `int` subclass, so `min_agreement: true` would slip through — reject it.
    if not isinstance(min_agreement, int) or isinstance(min_agreement, bool):
        raise ProfileError("evaluators.llm_judge.min_agreement must be an integer")
    identity = f"{_identity(cfg, 'llm_judge')}; samples={min_agreement}"
    try:
        # `prompt_version` names the security judge's rubric; the reference judge keeps
        # its own, so neither can inherit a calibration measured for the other.
        return (
            LlmJudgeEvaluator(
                judge, version, min_agreement, _calibration(cfg), judge_identity=identity
            ),
            ReferenceJudgeEvaluator(judge, min_agreement=min_agreement, judge_identity=identity),
        )
    except ValueError as exc:  # unknown prompt_version or min_agreement < 1 — config typos
        raise ProfileError(f"evaluators.llm_judge: {exc}") from exc


def _calibration(cfg: Mapping[str, object]) -> JudgeCalibration | None:
    """Read a measured accuracy from config, if the operator recorded one.

    Deliberately numbers rather than a corpus path: measuring costs one judge call
    per sample, and a scan is the wrong moment to spend that. Run
    `guardana calibrate`, then record what it measured — an explicit, auditable
    act rather than something that quietly happens on every run.
    """
    raw = cfg.get("calibration")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ProfileError("evaluators.llm_judge.calibration must be a mapping")
    accuracy = raw.get("accuracy")
    samples = raw.get("samples")
    evaluator_id = raw.get("evaluator_id")
    if not isinstance(accuracy, int | float) or isinstance(accuracy, bool):
        raise ProfileError("evaluators.llm_judge.calibration.accuracy must be a number")
    if not isinstance(samples, int) or isinstance(samples, bool):
        raise ProfileError("evaluators.llm_judge.calibration.samples must be an integer")
    if not isinstance(evaluator_id, str) or not evaluator_id:
        raise ProfileError(
            "evaluators.llm_judge.calibration.evaluator_id must name the judge that was "
            "measured, e.g. llm_judge@2025.1 — a changed rubric must not inherit an "
            "older measurement"
        )
    try:
        return JudgeCalibration(
            evaluator_id=evaluator_id, accuracy=float(accuracy), samples=samples
        )
    except ValueError as exc:
        raise ProfileError(f"evaluators.llm_judge.calibration: {exc}") from exc


def _endpoint_call(
    cfg: Mapping[str, object], what: str, budgets: Budgets | None
) -> Callable[[str], str]:
    """Build a `prompt -> reply` callable from an endpoint config block, bounded when asked."""
    target = build_endpoint(
        _require_str(cfg, "endpoint", what),
        _require_str(cfg, "model", what),
        api_key=_api_key(cfg, what),
    )
    if budgets is not None:
        target.apply_budgets(budgets)

    def call(prompt: str) -> str:
        return target.chat([ChatMessage(role="user", content=prompt)])

    return call


def _identity(cfg: Mapping[str, object], what: str) -> str:
    """State which model at which endpoint grades, so a calibration can be matched to it.

    The endpoint is digested after canonicalisation, never written out: a URL can carry
    credentials in its userinfo or query, and two spellings of one server must not read
    as two judges.
    """
    model = _require_str(cfg, "model", what)
    parts = urlsplit(_require_str(cfg, "endpoint", what))
    try:
        port = parts.port
    except ValueError as exc:
        raise ProfileError(f"evaluators.{what}.endpoint has an unreadable port: {exc}") from exc
    scheme = parts.scheme.lower()
    if port is None:
        port = _DEFAULT_PORTS.get(scheme)
    if port is None:
        raise ProfileError(f"evaluators.{what}.endpoint must state a port, or use http or https")
    host = (parts.hostname or "").lower()
    canonical = f"{scheme}://{host}:{port}{parts.path.rstrip('/')}"
    endpoint = digest_of(canonical).split(":", 1)[-1][:12]
    return f"model={model}; endpoint={endpoint}"


def _require_str(cfg: Mapping[str, object], key: str, what: str) -> str:
    value = cfg.get(key)
    if not isinstance(value, str) or not value:
        raise ProfileError(f"evaluators.{what}.{key} must be a non-empty string")
    return value


def _api_key(cfg: Mapping[str, object], what: str) -> str | None:
    env = cfg.get("api_key_env")
    if env is None:
        return None
    if not isinstance(env, str):
        raise ProfileError(f"evaluators.{what}.api_key_env must be a string")
    return os.environ.get(env)
