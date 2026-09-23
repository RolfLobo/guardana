"""`guardana plan` — what a run would cost, before it costs anything.

Rendered here rather than in `guardana-report` because a plan is not a result: it
is a preview of a configuration, nobody reads it back, and `guardana diff` has no
opinion about it. It still carries a `schema_version`, because the moment
something parses the JSON form its shape is a promise.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from guardana.cli._endpoint import build_endpoint
from guardana.cli._formats import OutputFormat
from guardana.cli._mcp_run import plan_target, require_chat_endpoint
from guardana.cli._plugins import resolve_trust, warn_about_load_errors
from guardana.cli._profile import resolve_profile
from guardana.cli._rules_loading import load_custom_rules
from guardana.cli._safety_flags import parse_impact
from guardana.cli._target_locator import resolve_target
from guardana.cli.exit_codes import ExitCode
from guardana.core.plan import RunPlan, build_plan
from guardana.core.plugins import PluginTrust
from guardana.core.profile import Profile
from guardana.core.registry import Registry
from guardana.core.target import ArtifactTarget, Target, TargetKind

PLAN_SCHEMA_VERSION = 2

plan_app = typer.Typer(
    help="Estimate what a run would cost, without sending a single request.",
    no_args_is_help=True,
)


def _render_human(run_plan: RunPlan, kind: TargetKind) -> str:
    lines = [f"{len(run_plan.rules)} rule(s) would run, {len(run_plan.skipped)} skipped."]
    if run_plan.is_complete and run_plan.max_requests == 0:
        if kind is TargetKind.ARTIFACT:
            lines.append("requests: 0 — every selected rule declares it sends nothing")
        else:
            lines.append("requests: 0 — no selected rule sends a request")
    else:
        lines.append(
            f"requests: at least {run_plan.min_requests}, at most {run_plan.max_requests}"
            + (
                ""
                if run_plan.is_complete
                else f" — plus {len(run_plan.unknown_cost)} of unknown cost"
            )
        )
    if kind is not TargetKind.ARTIFACT:
        lines.append(
            f"trials: {run_plan.trials} attempt(s) per case, counted in the requests above"
        )
    if run_plan.single_attempt:
        lines.append(
            f"  {len(run_plan.single_attempt)} rule(s) make one attempt per case whatever "
            f"--trials says, because their verdict does not depend on a sampled reply:"
        )
        lines.extend(f"    • {rule_id}" for rule_id in run_plan.single_attempt)
    if run_plan.unknown_cost:
        lines.append(
            "  these rules do not declare a request count, so the ceiling above is a "
            "lower bound on the worst case:"
        )
        lines.extend(f"    • {rule_id}" for rule_id in run_plan.unknown_cost)
    budgets = run_plan.budgets
    if budgets.max_requests is not None:
        lines.append(f"budget: {budgets.max_requests} request(s)")
    if run_plan.exceeds_budget:
        lines.append(
            "⚠ this plan does not fit its request budget — the run would stop early, "
            "and a run that stops early reports no verdict"
        )
    lines.append("")
    lines.append("No request was sent to produce this estimate.")
    return "\n".join(lines)


def _render_json(run_plan: RunPlan) -> str:
    return json.dumps(
        {
            "schema_version": PLAN_SCHEMA_VERSION,
            "rules": list(run_plan.rules),
            "skipped": list(run_plan.skipped),
            "unknown_cost": list(run_plan.unknown_cost),
            "requests": {"min": run_plan.min_requests, "max": run_plan.max_requests},
            # Stated rather than inferred from an empty `unknown_cost`: a consumer
            # gating on this should not have to know that rule.
            "complete": run_plan.is_complete,
            "budgets": {
                "max_requests": run_plan.budgets.max_requests,
                "max_input_tokens": run_plan.budgets.max_input_tokens,
                "max_output_tokens": run_plan.budgets.max_output_tokens,
                "max_duration_seconds": run_plan.budgets.max_duration_seconds,
            },
            "fits_budget": not run_plan.exceeds_budget,
            "trials": {
                "per_case": run_plan.trials,
                "single_attempt": list(run_plan.single_attempt),
            },
        },
        indent=2,
    )


def _emit(run_plan: RunPlan, output_format: OutputFormat, kind: TargetKind) -> None:
    if output_format is OutputFormat.json:
        typer.echo(_render_json(run_plan))
    else:
        typer.echo(_render_human(run_plan, kind))
    if run_plan.exceeds_budget:
        # Invalid configuration, not a failed run: nothing ran. Raising it here
        # means a pipeline finds out before it pays, which is the whole point.
        raise typer.Exit(code=ExitCode.INVALID_USAGE)


def _registry_for(profile: Profile, rules: list[Path], *, trust: PluginTrust) -> Registry:
    """Load exactly the registry a planned run will use."""
    registry = Registry.discover(trust)
    warn_about_load_errors(registry, what="rule")
    load_custom_rules(registry, profile, rules)
    return registry


def plan_scan(  # noqa: PLR0913, PLR0917 — one typer.Option per CLI flag; this is the command's surface
    path: Annotated[Path | None, typer.Argument(help="Directory that would be scanned")] = None,
    profile: Annotated[Path | None, typer.Option(help="guardana.yaml path")] = None,
    preset: Annotated[
        str | None, typer.Option(help="Named policy preset: ci|pre-training|monitor")
    ] = None,
    format: Annotated[OutputFormat, typer.Option(help="human|json")] = OutputFormat.human,
    no_plugins: Annotated[
        bool, typer.Option("--no-plugins", help="Deprecated alias for --plugins disabled.")
    ] = False,
    plugins: Annotated[
        str,
        typer.Option(help="Which installed plugins to load: all|builtins|allowlist|disabled"),
    ] = "all",
    allow_plugin: Annotated[
        list[str],
        typer.Option("--allow-plugin", help="Distribution to trust; repeatable, needs allowlist."),
    ] = [],  # noqa: B006 — typer builds the option from a literal default
    rules: Annotated[
        list[Path], typer.Option("--rules", help="Directory or file of custom YAML rules.")
    ] = [],  # noqa: B006 — typer builds the option from a literal default
    target: Annotated[
        str | None,
        typer.Option("--target", help="Installed artifact target as scheme://locator."),
    ] = None,
    target_option: Annotated[
        list[str],
        typer.Option("--target-option", help="Non-secret key=value for --target; repeatable."),
    ] = [],  # noqa: B006 — typer builds the option from a literal default
) -> None:
    """Report which rules a scan would run. A file scan sends no requests at all."""
    trust = resolve_trust(plugins, allow_plugin, no_plugins=no_plugins)
    prof = resolve_profile(profile, preset)
    if target is not None and path is not None:
        raise typer.BadParameter("pass either a path or --target, not both")
    registry = _registry_for(prof, rules, trust=trust)
    selected = resolve_target(
        registry,
        locator=target,
        options=target_option,
        kind=TargetKind.ARTIFACT,
        fallback=lambda: _plan_scan_path(path, prof.path_excludes),
    )
    _emit(build_plan(registry, prof, selected), format, selected.kind)


def plan_probe(  # noqa: PLR0913, PLR0917 — one typer.Option per CLI flag; this is the command's surface
    url: Annotated[
        str | None, typer.Option(help="Base URL of the OpenAI-compatible endpoint")
    ] = None,
    model: Annotated[str | None, typer.Option(help="Model name")] = None,
    mcp: Annotated[
        str | None,
        typer.Option(help="MCP server to price instead of a model endpoint: an http(s) URL"),
    ] = None,
    provider: Annotated[
        str, typer.Option(help="Endpoint wire protocol: openai|ollama|tgi")
    ] = "openai",
    system_prompt_file: Annotated[
        Path | None, typer.Option("--system-prompt-file", help="File containing a system prompt")
    ] = None,
    profile: Annotated[Path | None, typer.Option(help="guardana.yaml path")] = None,
    preset: Annotated[
        str | None, typer.Option(help="Named policy preset: ci|pre-training|monitor")
    ] = None,
    format: Annotated[OutputFormat, typer.Option(help="human|json")] = OutputFormat.human,
    rules: Annotated[
        list[Path], typer.Option("--rules", help="Directory or file of custom YAML rules.")
    ] = [],  # noqa: B006 — typer builds the option from a literal default
    safety: Annotated[
        str,
        typer.Option(help="How far rules may reach: passive|active|side-effecting"),
    ] = "active",
    allow_destructive: Annotated[
        bool,
        typer.Option(
            "--allow-destructive",
            help="Permit rules that can destroy or alter something the target owns.",
        ),
    ] = False,
    plugins: Annotated[
        str,
        typer.Option(help="Which installed plugins to load: all|builtins|allowlist|disabled"),
    ] = "all",
    allow_plugin: Annotated[
        list[str],
        typer.Option("--allow-plugin", help="Distribution to trust; repeatable, needs allowlist."),
    ] = [],  # noqa: B006 — typer builds the option from a literal default
    target: Annotated[
        str | None,
        typer.Option("--target", help="Installed endpoint target as scheme://locator."),
    ] = None,
    target_option: Annotated[
        list[str],
        typer.Option("--target-option", help="Non-secret key=value for --target; repeatable."),
    ] = [],  # noqa: B006 — typer builds the option from a literal default
    trials: Annotated[
        int | None,
        typer.Option(
            "--trials",
            min=1,
            help="Attempts per case for rules that grade a sampled reply; overrides `trials:`.",
        ),
    ] = None,
) -> None:
    """Report what probing this endpoint or MCP server would cost, without contacting it.

    An MCP probe is priced too, and it is where this command earns its keep: those
    checks send around a dozen requests where reading a manifest sent two. The
    ceiling it reports is the sum of what each rule would spend **alone**, which is
    what a plan has to assume because it cannot know which rule runs first; the
    observation is bought once and shared, so a real run spends a fraction of it.
    An upper bound that is too high refuses a budget that would have fitted, which
    is the safe direction to be wrong in.

    Capabilities are taken from what the target declares locally, so a provider
    that turns out not to support tool calls will skip more rules than this
    predicts. Asking the endpoint would make this command cost money, which is
    the one thing it must not do; `guardana target inspect` is where that
    question belongs.

    `--safety` and `--allow-destructive` mirror `guardana probe`, because a plan
    is only a preview of the run it is a preview of: without them, pricing a
    `--safety passive` probe listed every active rule it would have refused.
    """
    trust = resolve_trust(plugins, allow_plugin, no_plugins=False)
    prof = resolve_profile(profile, preset)
    prof = replace(
        prof,
        max_impact=parse_impact(safety),
        allow_destructive=allow_destructive,
        trials=prof.trials if trials is None else trials,
    )
    legacy_target_options = (url, model, mcp, system_prompt_file)
    if target is not None and any(value is not None for value in legacy_target_options):
        raise typer.BadParameter(
            "--target cannot be combined with --url, --model, --mcp, or --system-prompt-file"
        )
    registry = _registry_for(prof, rules, trust=trust)
    registry.apply_trials(prof.trials)
    selected = resolve_target(
        registry,
        locator=target,
        options=target_option,
        kind=TargetKind.ENDPOINT,
        fallback=lambda: _plan_probe_target(url, model, mcp, provider, system_prompt_file),
    )
    _emit(build_plan(registry, prof, selected), format, selected.kind)


def _plan_scan_path(path: Path | None, excludes: tuple[str, ...]) -> ArtifactTarget:
    """Build the legacy file target for a plan."""
    if path is None:
        raise typer.BadParameter("pass a path to scan, or --target scheme://locator")
    return ArtifactTarget(path, excludes=excludes)


def _plan_probe_target(
    url: str | None,
    model: str | None,
    mcp: str | None,
    provider: str,
    system_prompt_file: Path | None,
) -> Target:
    """Build the legacy endpoint or MCP target without contacting it."""
    if mcp is not None:
        return plan_target(mcp)
    endpoint_url, model_name = require_chat_endpoint(url, model)
    return build_endpoint(
        endpoint_url,
        model_name,
        api_key=None,
        system_prompt=_system_prompt_the_probe_will_send(system_prompt_file),
        provider=provider,
        transport=None,
    )


def _system_prompt_the_probe_will_send(named: Path | None) -> str:
    """Return the system prompt this plan must assume, which is never nothing.

    `probe` plants a fresh canary system prompt for every rule that needs one,
    with or without `--system-prompt-file` — that is how the leak check works at
    all. Building the plan's target without one made it declare no
    `plant_system_prompt`, so every canary rule was listed as skipped and left out
    of the ceiling: the plan under-priced the run, which is the direction that
    matters. A budget sized from it stops the real run early, and a run that stops
    early reports no verdict.

    The content is irrelevant and never sent — a plan contacts nothing — so what
    is read from the file is used when there is one, and a stand-in otherwise.
    """
    if named is not None:
        return named.read_text(encoding="utf-8")
    return "(placeholder: guardana probe plants a fresh canary here at run time)"


plan_app.command(name="scan")(plan_scan)
plan_app.command(name="probe")(plan_probe)
