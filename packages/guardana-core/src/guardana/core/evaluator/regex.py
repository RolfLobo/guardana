import re
from collections.abc import Mapping
from typing import ClassVar

from guardana.core.evaluator.base import Evaluator, Expectation, Outcome, Verdict
from guardana.core.exchange import Exchange


class RegexEvaluator(Evaluator):
    """Grades a reply by whether `pattern` occurs anywhere in it (`re.search`).

    `must_match` (default true) passes a reply the pattern is found in; false
    passes a reply it is not found in. The pattern must compile, which is checked
    before any reply is read. Confidence 1.0: a match is a fact.
    """

    id = "regex"
    deterministic: ClassVar[bool] = True
    expects: ClassVar[Mapping[str, bool]] = {"pattern": True, "must_match": False}

    @classmethod
    def check_fields(cls, expectation: Expectation) -> str | None:
        """Return why `pattern` or `must_match` is unusable, or None."""
        pattern = expectation.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return f"evaluator {cls.id!r}: 'expect.pattern' must be a non-empty string"
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"evaluator {cls.id!r}: 'expect.pattern' does not compile: {exc}"
        if not isinstance(expectation.get("must_match", True), bool):
            return f"evaluator {cls.id!r}: 'expect.must_match' must be true or false"
        return None

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        """Pass when finding the pattern is what `must_match` asked for."""
        problem = self.check_fields(expectation)
        if problem is not None:
            return Verdict("inconclusive", 0.0, problem, self.id)
        reply = exchange.reply_text
        if reply is None:
            return Verdict("inconclusive", 0.0, "No model reply to search.", self.id)
        must_match = expectation.get("must_match", True) is True
        found = re.search(str(expectation.get("pattern")), reply) is not None
        said = "found" if found else "not found"
        outcome: Outcome = "pass" if found == must_match else "fail"
        return Verdict(
            outcome, 1.0, f"pattern {said} in the reply (must_match={must_match}).", self.id
        )
