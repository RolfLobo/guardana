from collections.abc import Callable, Sequence
from urllib.error import URLError

import typer
from guardana.cli.exit_codes import ExitCode
from guardana.core.registry import Registry
from guardana.core.target import EndpointError, LocatorError, Target, TargetKind


def target_options(values: Sequence[str]) -> dict[str, str]:
    """Parse repeatable ``key=value`` target options, refusing ambiguity."""
    parsed: dict[str, str] = {}
    for value in values:
        key, separator, option = value.partition("=")
        key = key.strip()
        if not separator or not key:
            raise typer.BadParameter(
                f"invalid --target-option {value!r}: use a non-empty key=value pair"
            )
        if key in parsed:
            raise typer.BadParameter(
                f"--target-option {key!r} was passed more than once; one target "
                "configuration cannot contain two values for the same key"
            )
        parsed[key] = option
    return parsed


def resolve_target(
    registry: Registry,
    *,
    locator: str | None,
    options: Sequence[str],
    kind: TargetKind,
    fallback: Callable[[], Target],
) -> Target:
    """Build a selected plugin target, or the command's unchanged built-in target.

    The command chooses ``kind``. A locator can choose an implementation, never
    turn ``scan`` into a network probe or ``probe`` into a file reader.
    """
    if locator is None:
        if options:
            raise typer.BadParameter("--target-option needs --target scheme://locator")
        return fallback()

    scheme, separator, rest = locator.partition("://")
    if not separator or not scheme or not rest:
        raise typer.BadParameter(f"invalid target locator {locator!r}: use scheme://value")
    target_type = registry.target_for(scheme)
    if target_type is None:
        available = ", ".join(registry.schemes()) or "none"
        trust = _trust_note(registry)
        raise typer.BadParameter(
            f"unknown target scheme {scheme!r}; loaded schemes: {available}{trust}"
        )
    try:
        target = target_type.from_locator(rest, options=target_options(options))
    except LocatorError as exc:
        raise typer.BadParameter(f"invalid {scheme} target: {exc}") from exc
    except (URLError, OSError, EndpointError) as exc:
        typer.echo(f"error: could not reach target {locator}: {exc}", err=True)
        raise typer.Exit(code=ExitCode.TARGET_UNAVAILABLE) from exc
    if target.kind is not kind:
        raise typer.BadParameter(
            f"target {locator!r} built a {target.kind} target, but this command accepts "
            f"only {kind} targets"
        )
    return target


def _trust_note(registry: Registry) -> str:
    """Explain when a scheme may be absent because plugin trust refused its provider."""
    refused = [
        error.reason
        for error in registry.load_errors
        if error.stage == "discovery" and "plugin trust is" in error.reason
    ]
    if not refused:
        return ""
    policy = refused[0].rsplit("plugin trust is ", 1)[-1]
    return (
        f"; {len(refused)} plugin entry point(s) were not loaded because plugin trust is {policy}"
    )


__all__ = ["resolve_target", "target_options"]
