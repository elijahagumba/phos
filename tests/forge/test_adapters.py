"""Tests for the adapters: three-state detection, refusal, degradation and recording.

The real capability detection is exercised too, because the interesting fact about this machine is
which runtimes actually answer. Those tests read the machine and cannot fail for the right reason if
a runtime is later logged in, so they assert the shape rather than a fixed state.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from phos.forge import adapters
from phos.forge.adapters import (
    ADAPTERS,
    ClaudeAdapter,
    CodexAdapter,
    CursorAdapter,
    RuntimeAdapter,
    RuntimeUnavailableError,
    adapter_for,
    detect,
)
from phos.forge.protocol import AgentResult, Capability, RoleRequest

PACKAGE = Path(__file__).resolve().parents[2] / "src/phos/forge"


class _NeverReady(RuntimeAdapter):
    """An adapter whose binary is present and whose probe always fails."""

    runtime = "codex"
    binary = "python3"

    def probe(self) -> adapters.Probe:
        return adapters.Probe(False, "the probe was told to fail")

    def invoke(self, request: RoleRequest) -> AgentResult:  # pragma: no cover - refused first
        raise AssertionError("invoke must not be reached when the probe failed")


class _AlwaysReady(RuntimeAdapter):
    """An adapter that answers, so the success path is exercised without a network call."""

    runtime = "codex"
    binary = "python3"

    def probe(self) -> adapters.Probe:
        return adapters.Probe(True, "the probe was told to succeed")

    def invoke(self, request: RoleRequest) -> AgentResult:
        return AgentResult(
            runtime=self.runtime,
            runtime_state="ready",
            status="ok",
            exit_status=0,
            stdout="done",
            duration_s=0.1,
        )


def _request(tmp_path: Path) -> RoleRequest:
    return RoleRequest(
        operation="op-1",
        role="applied_scientist",
        task="write a harness",
        worktree=tmp_path,
        base_commit="0" * 40,
    )


def test_an_absent_binary_is_reported_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch the module this code actually reads, so the test does not depend on a re-export.
    monkeypatch.setattr("phos.forge.adapters.shutil.which", lambda _: None)
    capability = CodexAdapter().capability()
    assert capability.state == "absent"
    assert "not on PATH" in capability.detail


def test_an_installed_binary_whose_probe_fails_is_installed_not_ready() -> None:
    capability = _NeverReady().capability()
    assert capability.state == "installed"
    assert capability.detail == "the probe was told to fail"


def test_a_successful_probe_is_ready() -> None:
    capability = _AlwaysReady().capability()
    assert capability.state == "ready"


def test_an_unready_runtime_refuses_the_role() -> None:
    with pytest.raises(RuntimeUnavailableError, match="cannot be compared"):
        _NeverReady().run(_request(Path("/tmp")))


def test_an_unready_runtime_can_be_forced_and_reports_unavailable() -> None:
    result = _NeverReady().run(_request(Path("/tmp")), allow_unready=True)
    assert result.status == "unavailable"
    assert result.runtime_state == "installed"
    assert result.exit_status is None


def test_a_ready_runtime_runs(tmp_path: Path) -> None:
    result = _AlwaysReady().run(_request(tmp_path))
    assert result.status == "ok"
    assert result.runtime == "codex"
    assert result.runtime_state == "ready"


def test_the_recorded_runtime_is_the_one_that_ran(tmp_path: Path) -> None:
    result = _AlwaysReady().run(_request(tmp_path))
    assert result.runtime == _AlwaysReady.runtime


def test_no_module_in_the_package_names_a_model() -> None:
    """The task says do not pin or choose models. A model name in the code would be a pin."""
    suspicious = re.compile(
        r"\b(claude-(?:opus|sonnet|haiku)|gpt-\d|o[134]-|gemini-\d|grok-\d|composer-\d)", re.I
    )
    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not suspicious.search(text), f"{path.name} names a model"


def test_no_adapter_passes_a_model_flag() -> None:
    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert '"--model"' not in text, f"{path.name} passes --model"


def test_the_result_model_defaults_to_unknown_not_to_a_choice() -> None:
    assert AgentResult().model == "unknown"


def test_tokens_default_to_none_not_zero() -> None:
    """None is "not reported"; zero would be a claim that the turn was free."""
    assert AgentResult().tokens is None


def test_every_adapter_is_registered() -> None:
    assert set(ADAPTERS) == {"claude", "cursor", "codex"}


@pytest.mark.parametrize("name", ["claude", "cursor", "codex"])
def test_adapter_for_returns_the_right_class(name: str) -> None:
    expected = {"claude": ClaudeAdapter, "cursor": CursorAdapter, "codex": CodexAdapter}[name]
    assert isinstance(adapter_for(name), expected)


def test_an_unknown_runtime_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        adapter_for("gemini")


def test_the_binaries_are_the_ones_the_assessment_names() -> None:
    assert ClaudeAdapter.binary == "claude"
    assert CursorAdapter.binary == "cursor-agent"
    assert CodexAdapter.binary == "codex"


def test_capability_is_reported_for_this_machine() -> None:
    """A real probe, so the report says what is true here rather than what the code assumes."""
    for name in ("claude", "cursor", "codex"):
        capability = detect(name)
        assert capability.state in {"absent", "installed", "ready"}
        assert capability.detail, "a capability must say why it is in that state"
        if capability.state != "absent":
            assert capability.binary is not None


def test_a_capability_is_frozen() -> None:
    made = Capability(runtime="codex", state="ready", detail="fine")
    with pytest.raises(ValidationError):
        made.state = "absent"  # type: ignore[misc]


def test_the_prompt_carries_the_role_instruction_and_the_boundaries(tmp_path: Path) -> None:
    request = RoleRequest(
        operation="op-1",
        role="adversarial_researcher",
        task="attack the claimed win",
        idea="a sequential column",
        worktree=tmp_path,
        base_commit="0" * 40,
        instruction="You never open src/phos/atlas.",
        may_not_read=("src/phos/atlas/**",),
        may_write=("docs/method/**",),
    )
    prompt = adapters._prompt(request)
    assert "adversarial researcher" in prompt
    assert "You never open src/phos/atlas." in prompt
    assert "src/phos/atlas/**" in prompt
    assert "docs/method/**" in prompt
    assert "attack the claimed win" in prompt


def test_the_prompt_has_no_blank_run_where_an_optional_field_is_empty(tmp_path: Path) -> None:
    request = RoleRequest(
        operation="op-1",
        role="principal_architect",
        task="design",
        worktree=tmp_path,
        base_commit="0" * 40,
    )
    prompt = adapters._prompt(request)
    assert "\n\n\n" not in prompt


def test_codex_token_parsing_reads_the_reported_number() -> None:
    output = "some text\ntokens used\n19,040\n"
    assert adapters._tokens_from_codex(output) == 19040


def test_codex_token_parsing_returns_none_when_nothing_is_reported() -> None:
    assert adapters._tokens_from_codex("no numbers here") is None
