from collections.abc import Callable, Mapping
from typing import ClassVar

from guardana.core.evaluator.base import Evaluator, Expectation, Verdict
from guardana.core.exchange import Exchange


def _whitespace(text: str) -> str:
    return " ".join(text.split())


def _casefold(text: str) -> str:
    return _whitespace(text).casefold()


_NORMALIZERS: dict[str, Callable[[str], str]] = {
    "none": lambda text: text,
    "whitespace": _whitespace,
    "casefold": _casefold,
}


class ExactMatchEvaluator(Evaluator):
    """Passes a reply equal to `reference`, after an optional normalization.

    `normalize` is `none` (byte-for-byte, the default), `whitespace` (strip and
    collapse every whitespace run to one space) or `casefold` (whitespace, then
    case-insensitive). Equality is a fact, not an opinion, so a verdict carries
    confidence 1.0.
    """

    id = "exact_match"
    deterministic: ClassVar[bool] = True
    expects: ClassVar[Mapping[str, bool]] = {"reference": True, "normalize": False}

    @classmethod
    def check_fields(cls, expectation: Expectation) -> str | None:
        """Return why `reference` or `normalize` is unusable, or None."""
        reference = expectation.get("reference")
        if not isinstance(reference, str) or not reference:
            return f"evaluator {cls.id!r}: 'expect.reference' must be a non-empty string"
        normalize = expectation.get("normalize", "none")
        if not isinstance(normalize, str) or normalize not in _NORMALIZERS:
            return (
                f"evaluator {cls.id!r}: 'expect.normalize' must be one of "
                f"{', '.join(_NORMALIZERS)}, got {normalize!r}"
            )
        return None

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        """Pass when the normalized reply equals the normalized reference."""
        problem = self.check_fields(expectation)
        if problem is not None:
            return Verdict("inconclusive", 0.0, problem, self.id)
        reply = exchange.reply_text
        if reply is None:
            return Verdict("inconclusive", 0.0, "No model reply to compare.", self.id)
        mode = str(expectation.get("normalize", "none"))
        normalize = _NORMALIZERS[mode]
        if normalize(reply) == normalize(str(expectation.get("reference"))):
            return Verdict("pass", 1.0, f"reply equals the reference (normalize={mode}).", self.id)
        return Verdict(
            "fail", 1.0, f"reply differs from the reference (normalize={mode}).", self.id
        )
