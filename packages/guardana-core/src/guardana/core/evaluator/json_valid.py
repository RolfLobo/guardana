import json
from collections.abc import Mapping
from typing import ClassVar

from guardana.core.evaluator.base import Evaluator, Expectation, Verdict
from guardana.core.exchange import Exchange


def _refuse_constant(name: str) -> object:
    # Python's decoder accepts NaN and Infinity, which JSON does not.
    raise ValueError(f"{name} is not JSON")


class JsonValidEvaluator(Evaluator):
    """Passes a reply that is one JSON document, optionally an object with given keys.

    The reply is stripped of surrounding whitespace and parsed strictly (`NaN` and
    `Infinity` are refused). With `required_keys`, the document must be an object
    holding every one of them. A document too deeply nested for the parser to
    read is `inconclusive`: that limit is the parser's, not JSON's. Confidence 1.0.
    """

    id = "json_valid"
    deterministic: ClassVar[bool] = True
    expects: ClassVar[Mapping[str, bool]] = {"required_keys": False}

    @classmethod
    def check_fields(cls, expectation: Expectation) -> str | None:
        """Return why `required_keys` is not a list of strings, or None."""
        raw = expectation.get("required_keys")
        if raw is not None and (
            not isinstance(raw, list) or not all(isinstance(k, str) for k in raw)
        ):
            return f"evaluator {cls.id!r}: 'expect.required_keys' must be a list of strings"
        return None

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        """Pass when the reply parses, and holds every required key when some are named."""
        problem = self.check_fields(expectation)
        if problem is not None:
            return Verdict("inconclusive", 0.0, problem, self.id)
        reply = exchange.reply_text
        if reply is None:
            return Verdict("inconclusive", 0.0, "No model reply to parse.", self.id)
        try:
            document = json.loads(reply.strip(), parse_constant=_refuse_constant)
        except RecursionError:
            return Verdict("inconclusive", 0.0, "reply is nested too deeply to parse.", self.id)
        except ValueError as exc:
            return Verdict("fail", 1.0, f"reply is not valid JSON: {exc}", self.id)
        raw = expectation.get("required_keys")
        required = [k for k in raw if isinstance(k, str)] if isinstance(raw, list) else []
        why = _why_not(document, required)
        if why is not None:
            return Verdict("fail", 1.0, why, self.id)
        return Verdict("pass", 1.0, "reply is valid JSON holding every required key.", self.id)


def _why_not(document: object, required: list[str]) -> str | None:
    if not required:
        return None
    if not isinstance(document, dict):
        return "reply is valid JSON but not an object."
    missing = [k for k in required if k not in document]
    return f"reply lacks required key(s): {', '.join(missing)}" if missing else None
