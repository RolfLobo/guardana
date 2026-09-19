"""`guardana rule test` — run a rule's own fixtures, including the one nobody writes.

The inner loop for somebody authoring a rule: edit it, run its samples, see whether
it still classifies them correctly. Sends nothing anywhere — every fixture is a
scripted double — so it is safe to run on every keystroke.

**An unsampled rule is never reported as passing.** A command whose whole purpose is
to disprove false greens cannot print "ok" over an empty set of cases in its own
output, so a rule with no fixtures, or with no `inconclusive` fixture, exits `2`.
"""

from collections.abc import Callable
from fnmatch import fnmatch
from pathlib import Path
from typing import Annotated

import typer
from guardana.cli._evaluators import wire_config_evaluators
from guardana.cli._plugins import resolve_trust, warn_about_load_errors
from guardana.cli._profile import resolve_profile
from guardana.cli._rules_loading import load_custom_rules
from guardana.cli.exit_codes import ExitCode
from guardana.core.calibration.corpus import dump_corpus
from guardana.core.calibration.sample import CalibrationSample
from guardana.core.exchange import Exchange
from guardana.core.registry import Registry
from guardana.core.report import CheckError
from guardana.core.rule import FixtureOutcome, Rule, RuleContext, RuleFixture
from guardana.core.rule.verify import FixtureVerdict, RuleVerification, verify_rule
from guardana.core.target import ChatMessage, EndpointTarget

rule_app = typer.Typer(help="Work on one rule: run its fixtures.")


@rule_app.command("test")
def run_fixtures(  # noqa: PLR0913, PLR0917 — one typer.Option per CLI flag; the command's surface
    selector: Annotated[
        str, typer.Argument(help="Rule id or glob, e.g. 'acme.*'. Defaults to every rule.")
    ] = "*",
    profile: Annotated[Path | None, typer.Option(help="guardana.yaml path")] = None,
    rules: Annotated[
        list[Path],
        typer.Option("--rules", help="Directory or file of custom YAML rules; repeatable."),
    ] = [],  # noqa: B006 — typer builds the option from a literal default
    plugins: Annotated[
        str,
        typer.Option(help="Which installed plugins to load: all|builtins|allowlist|disabled"),
    ] = "all",
    allow_plugin: Annotated[
        list[str],
        typer.Option("--allow-plugin", help="Distribution to trust; repeatable, needs allowlist."),
    ] = [],  # noqa: B006 — typer builds the option from a literal default
    write_corpus: Annotated[
        Path | None,
        typer.Option(
            "--write-corpus",
            help="Write the fixtures out as a labelled corpus for `guardana calibrate`.",
        ),
    ] = None,
    unsampled_ok: Annotated[
        bool,
        typer.Option(
            "--unsampled-ok",
            help="Do not go indeterminate over rules that declare no fixtures.",
        ),
    ] = False,
) -> None:
    """Run the fixtures a rule declares, and say what they did not establish.

    Exit `0` every fixture classified as declared · `1` one did not · `2` the rule
    was never sampled, a fixture could not run, or a rule could not be loaded ·
    `3` the selector matched nothing.
    """
    prof = resolve_profile(profile, None)
    registry = Registry.discover(resolve_trust(plugins, allow_plugin, no_plugins=False))
    load_custom_rules(registry, prof, rules)
    wire_config_evaluators(registry, prof)
    warn_about_load_errors(registry, what="rule")

    selected = [r for r in registry.rules() if fnmatch(r.meta.id, selector)]
    if not selected:
        typer.echo(
            f"error: no rule matches {selector!r} — nothing was verified, which is not "
            f"the same as nothing being wrong",
            err=True,
        )
        raise typer.Exit(code=ExitCode.INVALID_USAGE)

    def context(rule: Rule) -> RuleContext:
        # The same context the runner builds, per rule. Grading a fixture with
        # default settings while the run grades with the profile's would verify a
        # rule nobody executes — the check would be green about behaviour the
        # pipeline never sees.
        return RuleContext(
            config=dict(prof.rule_config.get(rule.meta.id, {})),
            evaluators=registry.evaluators(),
        )

    verifications = tuple(verify_rule(rule, context(rule)) for rule in selected)
    for line in _render(verifications, registry.load_errors, unsampled_ok=unsampled_ok):
        typer.echo(line)
    if write_corpus is not None:
        _write_corpus(selected, verifications, write_corpus, context)
    raise typer.Exit(
        code=_exit_code(verifications, registry.load_errors, unsampled_ok=unsampled_ok)
    )


def _exit_code(
    verifications: tuple[RuleVerification, ...],
    load_errors: tuple[CheckError, ...],
    *,
    unsampled_ok: bool,
) -> int:
    """Worst outcome wins, and a wrong answer outranks an unasked question.

    A rule that classified a sample wrongly is a defect somebody must fix; a rule
    nobody sampled is a question nobody put. Reporting the second over the first
    would bury the actionable half. A rule that never loaded was never verified,
    and whether the selector would have matched it cannot be known, so it holds
    the verdict at indeterminate whatever else passed.
    """
    if any(v.failed for v in verifications):
        return ExitCode.POLICY_FAILED
    if load_errors or any(v.errored for v in verifications):
        return ExitCode.INDETERMINATE
    if not unsampled_ok and any(v.gaps for v in verifications):
        return ExitCode.INDETERMINATE
    return ExitCode.OK


def _render(
    verifications: tuple[RuleVerification, ...],
    load_errors: tuple[CheckError, ...],
    *,
    unsampled_ok: bool,
) -> list[str]:
    lines = [
        f"! could not load {error.source} ({error.stage}): {error.reason}" for error in load_errors
    ]
    passed = failed = errored = 0
    for verification in verifications:
        for result in verification.results:
            if result.verdict is FixtureVerdict.PASSED:
                passed += 1
                continue
            failed += result.verdict is FixtureVerdict.FAILED
            errored += result.verdict is FixtureVerdict.ERRORED
            mark = "✖" if result.verdict is FixtureVerdict.FAILED else "!"
            lines.append(f"{mark} {result.rule_id} — {result.fixture}")
            lines.append(f"    {result.detail}")
        lines.extend(f"? {gap}" for gap in verification.gaps)
    unsampled = sum(1 for v in verifications if v.gaps)
    lines.append("")
    lines.append(
        f"{len(verifications)} rule(s); {passed} fixture(s) passed, {failed} failed, "
        f"{errored} could not run. {unsampled} rule(s) not fully sampled."
        + (f" {len(load_errors)} rule source(s) could not be loaded." if load_errors else "")
    )
    if unsampled and unsampled_ok:
        lines.append(
            "note: --unsampled-ok is set, so the unsampled rules above did not take "
            "the verdict away. They are still unchecked."
        )
    return lines


_LEFT_OUT = (
    "inconclusive (no measurable label)",
    "from a rule that declares no expectation or more than one",
    "not a single scripted reply (a conversation or an agent run)",
    "not classified as declared",
    "no request reached the scripted model",
)
_INCONCLUSIVE, _NOT_ONE_EXPECTATION, _NOT_ONE_REPLY, _NOT_VERIFIED, _NOTHING_SENT = _LEFT_OUT


def _write_corpus(
    selected: list[Rule],
    verifications: tuple[RuleVerification, ...],
    destination: Path,
    context: Callable[[Rule], RuleContext],
) -> None:
    """Turn the fixtures into a labelled corpus `guardana calibrate` can measure against.

    A fixture becomes a row only when the row can be labelled truthfully: a known
    outcome, one expectation to grade it with, one scripted reply for that
    expectation to read, and a rule that classified it as its author declared.
    Everything else is **left out** and counted per reason rather than passed over;
    a guessed or disputed label would make the resulting Brier score a measurement
    of the guess.

    The row pairs the reply with the first prompt the rule really sent. The label is
    the fixture's outcome for the rule as a whole, which is exact for a rule that
    sends one prompt and for an evaluator that does not read the prompt.
    """
    samples: list[CalibrationSample] = []
    left_out = dict.fromkeys(_LEFT_OUT, 0)
    for rule, verification in zip(selected, verifications, strict=True):
        expectations = tuple(e for _id, e in rule.declared_expectations())
        for index, fixture in enumerate(rule.fixtures()):
            reply = _scripted_reply(fixture.target)
            if fixture.outcome is FixtureOutcome.INCONCLUSIVE:
                left_out[_INCONCLUSIVE] += 1
            elif len(expectations) != 1:
                left_out[_NOT_ONE_EXPECTATION] += 1
            elif reply is None:
                left_out[_NOT_ONE_REPLY] += 1
            elif not _classified_as_declared(verification, index, fixture):
                left_out[_NOT_VERIFIED] += 1
            elif (prompt := _first_request(rule, fixture, context(rule))) is None:
                left_out[_NOTHING_SENT] += 1
            else:
                samples.append(
                    CalibrationSample(
                        exchange=Exchange((*prompt, ChatMessage(role="assistant", content=reply))),
                        expectation=expectations[0],
                        attack_succeeded=fixture.outcome is FixtureOutcome.FINDING,
                    )
                )
    destination.write_text(dump_corpus(samples), encoding="utf-8")
    reasons = ", ".join(f"{count} {reason}" for reason, count in left_out.items() if count)
    typer.echo(
        f"wrote {len(samples)} labelled sample(s) to {destination}"
        + (f"; left out: {reasons}" if reasons else "")
    )


def _classified_as_declared(
    verification: RuleVerification, index: int, fixture: RuleFixture
) -> bool:
    """Whether the verdict at this fixture's position is a pass about this very fixture.

    `fixtures()` is called again to build the corpus, and a plugin whose samples are
    not stable across calls must not get a row labelled from another sample's verdict.
    """
    if index >= len(verification.results):
        return False
    result = verification.results[index]
    return (
        result.verdict is FixtureVerdict.PASSED
        and result.fixture == fixture.name
        and result.expected is fixture.outcome
    )


def _first_request(
    rule: Rule, fixture: RuleFixture, ctx: RuleContext
) -> tuple[ChatMessage, ...] | None:
    """Play the fixture once more and read back the first request the rule sent.

    A row has to carry the exchange the evaluator graded. A placeholder user turn
    labels a different one: an evaluator that reads the prompt, as `amplification`
    does, is measured on text the rule never sent, and a judge reads the fixture's
    name where the prompt should be.
    """
    try:
        list(rule.run(fixture.target, ctx))
    except Exception:  # classified as declared a moment ago; a replay that raises gets no row
        return None
    seen = getattr(getattr(fixture.target, "transport", None), "seen", None)
    if not isinstance(seen, list) or not seen:
        return None
    return tuple(seen[0])


def _scripted_reply(target: object) -> str | None:
    """Read back the one reply a fixture's scripted transport will answer, if that is all it is.

    A plugin fixture may drive an artifact or an MCP server, a scenario several
    turns and an agent run a tool loop; none of those is one exchange a judge can be
    measured on. Returning `None` is how they are left out rather than rendered as
    an empty conversation or as the first turn of a longer one.
    """
    if not isinstance(target, EndpointTarget):
        return None
    scripted = getattr(target.transport, "scripted", None)
    if isinstance(scripted, tuple) and len(scripted) == 1 and isinstance(scripted[0], str):
        return scripted[0]
    return None


__all__ = ["rule_app"]
