import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Self

import pytest
import typer
from guardana.cli._target_locator import resolve_target, target_options
from guardana.cli.main import app
from guardana.core.registry import Registry
from guardana.core.report import CheckError
from guardana.core.target import Capability, ChatMessage, LocatorError, Target, TargetKind
from typer.testing import CliRunner

runner = CliRunner()


class _Located(Target):
    kind = TargetKind.ARTIFACT
    scheme = "acme-files"

    def __init__(self, ref: str) -> None:
        self._ref = ref

    @classmethod
    def from_locator(cls, locator: str, *, options: Mapping[str, str]) -> Self:
        if "unknown" in options:
            raise LocatorError("unknown option")
        return cls(f"acme-files://{locator}:{options.get('mode', 'default')}")

    def capabilities(self) -> set[Capability]:
        return set()

    @property
    def ref(self) -> str:
        return self._ref


class _Endpoint(Target):
    kind = TargetKind.ENDPOINT
    scheme = "acme-endpoint"

    def __init__(self, ref: str) -> None:
        self._ref = ref

    @classmethod
    def from_locator(cls, locator: str, *, options: Mapping[str, str]) -> Self:
        if options:
            raise LocatorError("this test target accepts no options")
        return cls(f"acme-endpoint://{locator}")

    def capabilities(self) -> set[Capability]:
        return {Capability.CHAT}

    @property
    def ref(self) -> str:
        return self._ref

    @property
    def model(self) -> str:
        return "scripted"

    def chat(self, messages: Sequence[ChatMessage]) -> str:
        return "I cannot help with that request."


class _Unavailable(_Located):
    scheme = "unavailable"

    @classmethod
    def from_locator(cls, locator: str, *, options: Mapping[str, str]) -> Self:
        raise OSError("connection refused")


def _fallback() -> Target:
    return _Located("fallback")


def test_resolve_target_passes_the_unparsed_locator_and_named_options() -> None:
    registry = Registry()
    registry.register_target(_Located)

    target = resolve_target(
        registry,
        locator="acme-files://bucket/key?part=1",
        options=["mode=strict"],
        kind=TargetKind.ARTIFACT,
        fallback=_fallback,
    )

    assert target.ref == "acme-files://bucket/key?part=1:strict"


@pytest.mark.parametrize("value", ["missing-equals", "=empty-key"])
def test_target_options_refuse_malformed_pairs(value: str) -> None:
    with pytest.raises(typer.BadParameter, match="key=value"):
        target_options([value])


def test_target_options_refuse_duplicate_keys() -> None:
    with pytest.raises(typer.BadParameter, match="more than once"):
        target_options(["mode=one", "mode=two"])


@pytest.mark.parametrize("locator", ["missing-separator", "://empty", "acme-files://"])
def test_target_locator_refuses_malformed_values(locator: str) -> None:
    with pytest.raises(typer.BadParameter, match="scheme://value"):
        resolve_target(
            Registry(),
            locator=locator,
            options=[],
            kind=TargetKind.ARTIFACT,
            fallback=_fallback,
        )


def test_unknown_or_wrong_kind_targets_are_usage_errors() -> None:
    registry = Registry()
    registry.register_target(_Located)

    with pytest.raises(typer.BadParameter, match="unknown target scheme"):
        resolve_target(
            registry,
            locator="missing://x",
            options=[],
            kind=TargetKind.ARTIFACT,
            fallback=_fallback,
        )
    with pytest.raises(typer.BadParameter, match="accepts only endpoint targets"):
        resolve_target(
            registry,
            locator="acme-files://x",
            options=[],
            kind=TargetKind.ENDPOINT,
            fallback=_fallback,
        )


def test_options_without_a_locator_are_refused() -> None:
    with pytest.raises(typer.BadParameter, match="needs --target"):
        resolve_target(
            Registry(),
            locator=None,
            options=["mode=strict"],
            kind=TargetKind.ARTIFACT,
            fallback=_fallback,
        )


def test_no_locator_uses_the_legacy_fallback() -> None:
    target = resolve_target(
        Registry(),
        locator=None,
        options=[],
        kind=TargetKind.ARTIFACT,
        fallback=_fallback,
    )

    assert target.ref == "fallback"


def test_a_target_rejected_option_is_a_usage_error() -> None:
    registry = Registry()
    registry.register_target(_Located)

    with pytest.raises(typer.BadParameter, match="unknown option"):
        resolve_target(
            registry,
            locator="acme-files://x",
            options=["unknown=yes"],
            kind=TargetKind.ARTIFACT,
            fallback=_fallback,
        )


def test_an_unreachable_target_has_its_own_exit_code() -> None:
    registry = Registry()
    registry.register_target(_Unavailable)

    with pytest.raises(typer.Exit) as stopped:
        resolve_target(
            registry,
            locator="unavailable://x",
            options=[],
            kind=TargetKind.ARTIFACT,
            fallback=_fallback,
        )

    assert stopped.value.exit_code == 4


def test_an_unknown_scheme_mentions_when_plugin_trust_refused_providers() -> None:
    registry = Registry()
    registry.record_load_error(
        CheckError("acme", "discovery", "entry point refused: plugin trust is allowlist")
    )

    with pytest.raises(typer.BadParameter, match="plugin trust is allowlist"):
        resolve_target(
            registry,
            locator="acme-files://x",
            options=[],
            kind=TargetKind.ARTIFACT,
            fallback=_fallback,
        )


def test_scan_keeps_a_plugin_owned_locator_ref_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = Registry.discover()
    registry.register_target(_Located)
    monkeypatch.setattr(
        Registry,
        "discover",
        classmethod(lambda cls, trust=True: registry),
    )
    output = tmp_path / "run.json"
    locator = f"acme-files://{tmp_path}"

    result = runner.invoke(
        app,
        ["scan", "--target", locator, "--format", "json", "--output", str(output)],
    )

    assert result.exit_code in (0, 2), result.output
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["run"]["target"]["ref"] == f"{locator}:default"


def _install_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = Registry.discover()
    registry.register_target(_Endpoint)
    monkeypatch.setattr(
        Registry,
        "discover",
        classmethod(lambda cls, trust=True: registry),
    )


def test_probe_runs_an_installed_endpoint_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_endpoint(monkeypatch)
    output = tmp_path / "probe.json"

    result = runner.invoke(
        app,
        [
            "probe",
            "--target",
            "acme-endpoint://deployment/support",
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code in (0, 1, 2), result.output
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["run"]["target"]["ref"] == "acme-endpoint://deployment/support"
    canary = next(
        skipped
        for skipped in document["run"]["result_summary"]["rules_skipped"]
        if skipped["rule_id"] == "guardana.prompt.system_prompt_leak.canary"
    )
    assert canary["missing"] == ["plant_system_prompt"]


def test_monitor_rebuilds_an_installed_target_for_its_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_endpoint(monkeypatch)

    result = runner.invoke(
        app,
        [
            "monitor",
            "--target",
            "acme-endpoint://deployment/support",
            "--max-cycles",
            "1",
            "--interval",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output


def test_plan_and_inspection_accept_the_same_installed_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_endpoint(monkeypatch)

    planned = runner.invoke(
        app, ["plan", "probe", "--target", "acme-endpoint://deployment/support"]
    )
    inspected = runner.invoke(
        app,
        [
            "target",
            "inspect",
            "--target",
            "acme-endpoint://deployment/support",
            "--format",
            "json",
        ],
    )

    assert planned.exit_code == 0, planned.output
    assert "No request was sent" in planned.output
    assert inspected.exit_code == 0, inspected.output
    assert json.loads(inspected.output)["target"]["ref"] == ("acme-endpoint://deployment/support")


@pytest.mark.parametrize(
    "command",
    [
        ["probe", "--url", "http://legacy", "--model", "m"],
        ["monitor", "--url", "http://legacy", "--model", "m"],
        ["target", "inspect", "--url", "http://legacy", "--model", "m"],
    ],
)
def test_an_endpoint_locator_refuses_legacy_connection_flags(
    command: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_endpoint(monkeypatch)

    result = runner.invoke(
        app,
        [*command, "--target", "acme-endpoint://deployment/support"],
    )

    assert result.exit_code == 3, result.output
    assert "--target cannot be combined" in result.output
