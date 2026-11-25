"""One protocol, several runtimes, and honest capability detection.

Each adapter drives one CLI. They share :class:`phos.forge.protocol.AgentResult`, so a caller does
not care which one ran, and the result records which one did.

**Three states, not two.** ``absent`` means no binary on ``PATH``. ``installed`` means the binary is
there and a turn has not succeeded, which on this machine covers both "not logged in" and "OAuth
expired". ``ready`` means a probe turn actually worked. The distinction is not pedantry: a
two-state check reported both broken runtimes as available during this session's recon, and the
first real operation would have failed at the first turn with a message nobody could act on.

**No model is chosen.** No adapter passes a model flag, and no module in this package names a model.
Each role runs on whatever the runtime's default is, and ``AgentResult.model`` records what the
runtime reported, so a difference between two results can be traced after the fact. The reason is
in the task: pinning a model would make a comparison between arms a comparison of models.

**Degradation is explicit.** A role whose runtime is not ``ready`` is refused before the operation
starts, with the reason naming what is missing. There is no silent fallback, because a result whose
runtime is unknown cannot be compared with a recorded one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from phos.forge.protocol import AgentResult, Capability, RoleRequest, Runtime, RuntimeState

#: How long a probe turn may take. Long enough for a real round trip, short enough that a hung CLI
#: does not hold an operation.
PROBE_TIMEOUT_S: Final = 120

#: How long a role turn may take. Generous, because the alternative is killing work that was about
#: to finish; an operation that needs longer should say so rather than be silently truncated.
TURN_TIMEOUT_S: Final = 3600


class RuntimeUnavailableError(RuntimeError):
    """A runtime was asked to run when it was not ready."""


@dataclass(frozen=True)
class Probe:
    """What one probe turn found.

    Attributes:
        ok: Whether the turn succeeded.
        detail: Why it did or did not, in a sentence a human can act on.
        model: What the runtime reported, when it said anything.
    """

    ok: bool
    detail: str
    model: str = "unknown"


class RuntimeAdapter:
    """Base class for one runtime's adapter.

    A subclass supplies the binary name, the argv for a turn and the way to read the runtime's own
    output. Everything that has to behave the same way across runtimes, which is the checking and
    the recording, stays here.
    """

    #: The runtime this adapter drives. Set by each subclass.
    runtime: Runtime = "unknown"

    #: The command to look for on ``PATH``.
    binary: str = ""

    def locate(self) -> Path | None:
        """Return the binary's path, or None when it is not installed.

        Returns:
            The path, or None.
        """
        found = shutil.which(self.binary) if self.binary else None
        return Path(found) if found else None

    def capability(self) -> Capability:
        """Return how available this runtime is, by running a real probe turn.

        The probe is a small turn with a fixed expected answer. It costs a little and it is the only
        way to tell ``installed`` from ``ready``: a binary that starts and then fails to
        authenticate is installed, not ready.

        Returns:
            The capability, with a detail a human can act on.
        """
        binary = self.locate()
        if binary is None:
            return Capability(
                runtime=self.runtime,
                state="absent",
                detail=f"{self.binary} is not on PATH",
                binary=None,
            )
        probe = self.probe()
        state: RuntimeState = "ready" if probe.ok else "installed"
        return Capability(runtime=self.runtime, state=state, detail=probe.detail, binary=binary)

    def probe(self) -> Probe:
        """Run a probe turn. Subclasses implement this.

        Returns:
            What the probe found.

        Raises:
            NotImplementedError: Always, in the base class.
        """
        raise NotImplementedError

    def run(self, request: RoleRequest, *, allow_unready: bool = False) -> AgentResult:
        """Run one role turn.

        Args:
            request: What the role is asked to do.
            allow_unready: Run even when the capability probe fails. The result then records
                ``unavailable`` rather than being reported as a working turn.

        Returns:
            The result, always with the runtime that actually ran and the state it was in.

        Raises:
            RuntimeUnavailableError: If the runtime is not ``ready`` and ``allow_unready`` is False.
        """
        capability = self.capability()
        if capability.state != "ready" and not allow_unready:
            raise RuntimeUnavailableError(
                f"{self.runtime} is {capability.state}: {capability.detail}. A role is refused "
                "rather than run on a runtime that cannot answer, because a result whose runtime "
                "is unknown cannot be compared with one whose runtime is recorded."
            )
        if capability.state != "ready":
            return AgentResult(
                runtime=self.runtime,
                runtime_state=capability.state,
                status="unavailable",
                stderr=capability.detail,
            )
        return self.invoke(request)

    def invoke(self, request: RoleRequest) -> AgentResult:
        """Run the turn against the CLI. Subclasses implement this.

        Args:
            request: What the role is asked to do.

        Returns:
            The result.

        Raises:
            NotImplementedError: Always, in the base class.
        """
        raise NotImplementedError

    def _run_process(self, argv: list[str], cwd: Path) -> tuple[int, str, str, float]:
        """Run one CLI invocation and time it.

        Args:
            argv: The command.
            cwd: The working directory, which is the role's worktree.

        Returns:
            ``(returncode, stdout, stderr, duration_s)``. A timeout returns 124, which is the code
            ``timeout(1)`` uses, so a truncated turn is distinguishable from a refusal.
        """
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=TURN_TIMEOUT_S,
            )
            elapsed = time.monotonic() - started
            return completed.returncode, completed.stdout, completed.stderr, elapsed
        except subprocess.TimeoutExpired as expired:
            elapsed = time.monotonic() - started
            out = expired.stdout if isinstance(expired.stdout, str) else ""
            err = expired.stderr if isinstance(expired.stderr, str) else ""
            return 124, out, f"{err}\nFORGE: the turn exceeded {TURN_TIMEOUT_S}s", elapsed
        except OSError as error:
            elapsed = time.monotonic() - started
            return 127, "", f"FORGE: could not start {argv[0]}: {error}", elapsed


def _prompt(request: RoleRequest) -> str:
    """Return the prompt one role is given.

    The instruction is the role's own skill text, verbatim, so a role behaves the same way under
    FORGE as it does when a human starts it. FORGE does not rewrite a role's mandate: that would be
    a second copy of a rule, and the rule files win over any summary of them.

    Args:
        request: What the role is asked to do.

    Returns:
        The prompt.
    """
    sections: list[str] = [
        f"You are the {request.role.replace('_', ' ')} for one FORGE operation."
    ]
    if request.instruction.strip():
        sections.append(request.instruction.strip())

    operation_lines = [f"Operation: {request.operation}"]
    if request.idea:
        operation_lines.append(f"Idea: {request.idea}")
    if request.declaration:
        operation_lines.append(f"Declaration: {request.declaration}")
    operation_lines += [
        f"Worktree: {request.worktree}",
        f"Base commit: {request.base_commit}",
    ]
    sections.append("## The operation\n\n" + "\n".join(operation_lines))
    sections.append(f"## The task\n\n{request.task}")

    boundaries = ["Work only inside the worktree above. Do not open any path outside it."]
    if request.may_write:
        boundaries += ["", "You may write these paths:", *[f"- {p}" for p in request.may_write]]
    if request.may_not_read:
        boundaries += [
            "",
            "You must not open these paths:",
            *[f"- {p}" for p in request.may_not_read],
        ]
    sections.append("## Boundaries\n\n" + "\n".join(boundaries))

    return "\n\n".join(sections)


class CodexAdapter(RuntimeAdapter):
    """The Codex CLI, driven with ``codex exec``.

    This is the one runtime that answered a probe on this machine, so it is the one the baseline
    harness can use today. ``--skip-git-repo-check`` is not passed: a role always runs in a
    worktree, which is a git repository, and a turn that somehow was not would be worth failing.
    """

    runtime: Runtime = "codex"
    binary: str = "codex"

    def probe(self) -> Probe:
        """Ask the runtime for a fixed answer.

        Returns:
            Whether it gave one.
        """
        binary = self.locate()
        if binary is None:
            return Probe(False, "codex is not on PATH")
        try:
            done = subprocess.run(
                [str(binary), "exec", "Reply with exactly: PROBE_OK"],
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                check=False,
                timeout=PROBE_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return Probe(False, f"codex probe failed to run: {error}")
        if done.returncode == 0 and "PROBE_OK" in done.stdout:
            return Probe(True, "codex answered a probe turn", "unknown")
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        return Probe(False, f"codex did not answer a probe turn: {tail[0][:200]}")

    def invoke(self, request: RoleRequest) -> AgentResult:
        """Run the turn through ``codex exec``.

        Args:
            request: What the role is asked to do.

        Returns:
            The result.
        """
        binary = self.locate()
        if binary is None:
            return AgentResult(runtime=self.runtime, runtime_state="absent", status="unavailable")
        code, out, err, elapsed = self._run_process(
            [str(binary), "exec", _prompt(request)], request.worktree
        )
        return AgentResult(
            runtime=self.runtime,
            runtime_state="ready",
            status="ok" if code == 0 else "failed",
            exit_status=code,
            stdout=out,
            stderr=err,
            duration_s=round(elapsed, 2),
            tokens=_tokens_from_codex(out),
        )


def _tokens_from_codex(output: str) -> int | None:
    """Return the token count Codex prints, or None when it printed none.

    Args:
        output: The command's standard output.

    Returns:
        The count, or None. None means "not reported" and is never zero.
    """
    for line in reversed(output.splitlines()):
        stripped = line.strip().lower()
        if stripped.startswith("tokens used"):
            continue
        if stripped.replace(",", "").isdigit():
            return int(stripped.replace(",", ""))
    return None


class ClaudeAdapter(RuntimeAdapter):
    """The Claude Code CLI, driven with ``claude -p``.

    Installed on this machine and not usable: the OAuth session is expired. That is why
    :meth:`capability` probes rather than trusting the binary's existence.
    """

    runtime: Runtime = "claude"
    binary: str = "claude"

    def probe(self) -> Probe:
        """Ask the runtime for a fixed answer.

        Returns:
            Whether it gave one. An authentication failure is reported by name, because "expired
            OAuth" and "not installed" need different fixes.
        """
        binary = self.locate()
        if binary is None:
            return Probe(False, "claude is not on PATH")
        try:
            done = subprocess.run(
                [str(binary), "-p", "Reply with exactly: PROBE_OK", "--output-format", "json"],
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                check=False,
                timeout=PROBE_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return Probe(False, f"claude probe failed to run: {error}")
        parsed = _json_or_none(done.stdout)
        if isinstance(parsed, dict) and parsed.get("is_error"):
            message = str(parsed.get("result", "no reason given"))
            return Probe(False, f"claude failed a probe turn: {message[:200]}")
        if done.returncode == 0 and "PROBE_OK" in done.stdout:
            return Probe(True, "claude answered a probe turn")
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        return Probe(False, f"claude did not answer a probe turn: {tail[0][:200]}")

    def invoke(self, request: RoleRequest) -> AgentResult:
        """Run the turn through ``claude -p`` with JSON output.

        Args:
            request: What the role is asked to do.

        Returns:
            The result.
        """
        binary = self.locate()
        if binary is None:
            return AgentResult(runtime=self.runtime, runtime_state="absent", status="unavailable")
        code, out, err, elapsed = self._run_process(
            [
                str(binary),
                "-p",
                _prompt(request),
                "--output-format",
                "json",
                "--permission-mode",
                "acceptEdits",
            ],
            request.worktree,
        )
        parsed = _json_or_none(out)
        model = "unknown"
        tokens: int | None = None
        text = out
        if isinstance(parsed, dict):
            text = str(parsed.get("result", out))
            usage = parsed.get("usage")
            if isinstance(usage, dict):
                combined = sum(
                    int(usage.get(key, 0))
                    for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens")
                    if isinstance(usage.get(key, 0), int)
                )
                tokens = combined or None
            reported = parsed.get("modelUsage")
            if isinstance(reported, dict) and reported:
                model = str(next(iter(reported)))
        return AgentResult(
            runtime=self.runtime,
            runtime_state="ready",
            status="ok" if code == 0 else "failed",
            exit_status=code,
            stdout=text,
            stderr=err,
            duration_s=round(elapsed, 2),
            model=model,
            tokens=tokens,
        )


class CursorAdapter(RuntimeAdapter):
    """The Cursor agent CLI, driven with ``cursor-agent --print --trust``.

    ``--worktree`` is deliberately not passed: FORGE creates the worktree itself, in
    :mod:`phos.forge.worktree`, so that the location, the base commit and the branch-name check are
    the same for every runtime.

    ``--trust`` is passed and is not a convenience. Without it the CLI stops to ask whether the
    directory is trusted, and in ``--print`` there is nobody to answer, so the turn fails with a
    message about the prompt rather than about the work. That is a false negative in a capability
    check: the runtime is authenticated and able, and reports itself unusable. The trust is scoped
    to the worktree FORGE made for this one role, which is a directory created minutes earlier from
    a known commit.
    """

    runtime: Runtime = "cursor"
    binary: str = "cursor-agent"

    def probe(self) -> Probe:
        """Ask the runtime for a fixed answer.

        Returns:
            Whether it gave one.
        """
        binary = self.locate()
        if binary is None:
            return Probe(False, "cursor-agent is not on PATH")
        try:
            done = subprocess.run(
                [str(binary), "--print", "--trust", "Reply with exactly: PROBE_OK"],
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                check=False,
                timeout=PROBE_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return Probe(False, f"cursor-agent probe failed to run: {error}")
        if done.returncode == 0 and "PROBE_OK" in done.stdout:
            return Probe(True, "cursor-agent answered a probe turn")
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        return Probe(False, f"cursor-agent did not answer a probe turn: {tail[0][:200]}")

    def invoke(self, request: RoleRequest) -> AgentResult:
        """Run the turn through ``cursor-agent --print``.

        Args:
            request: What the role is asked to do.

        Returns:
            The result.
        """
        binary = self.locate()
        if binary is None:
            return AgentResult(runtime=self.runtime, runtime_state="absent", status="unavailable")
        code, out, err, elapsed = self._run_process(
            [str(binary), "--print", "--trust", "--output-format", "text", _prompt(request)],
            request.worktree,
        )
        return AgentResult(
            runtime=self.runtime,
            runtime_state="ready",
            status="ok" if code == 0 else "failed",
            exit_status=code,
            stdout=out,
            stderr=err,
            duration_s=round(elapsed, 2),
        )


def _json_or_none(text: str) -> dict[str, object] | None:
    """Return ``text`` parsed as a JSON object, or None.

    Args:
        text: The candidate text.

    Returns:
        The object, or None when the text is not a JSON object.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


#: Every adapter, by runtime name.
ADAPTERS: Final[dict[str, type[RuntimeAdapter]]] = {
    "claude": ClaudeAdapter,
    "cursor": CursorAdapter,
    "codex": CodexAdapter,
}


def adapter_for(runtime: str) -> RuntimeAdapter:
    """Return the adapter for one runtime name.

    Args:
        runtime: ``claude``, ``cursor`` or ``codex``.

    Returns:
        The adapter.

    Raises:
        KeyError: If there is no such runtime.
    """
    return ADAPTERS[runtime]()


def detect(runtime: str) -> Capability:
    """Return how available one runtime is.

    Args:
        runtime: The runtime name.

    Returns:
        The capability.

    Raises:
        KeyError: If there is no such runtime.
    """
    return adapter_for(runtime).capability()


def detect_all() -> tuple[Capability, ...]:
    """Return how available every runtime is, in a fixed order.

    Returns:
        One capability per runtime, ordered ``claude``, ``cursor``, ``codex`` so a report reads the
        same way twice.
    """
    return tuple(adapter_for(name).capability() for name in ("claude", "cursor", "codex"))
