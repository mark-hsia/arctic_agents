"""Tool layer base classes.

All external bio tools (assemblers, binners, antiSMASH, ...) are surfaced
through this small interface so agents call ``registry.get(tool_id).run(...)``
without caring whether the implementation shells out, calls a hosted API, or
returns a replay artifact.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ToolUnavailable(RuntimeError):
    """Raised when a tool is requested but cannot run in the current environment."""


@dataclass
class ToolRunResult:
    tool_id: str
    output_paths: list[Path] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    duration_seconds: float = 0.0
    tool_version: str | None = None


class Tool(ABC):
    """Abstract base. Concrete tools implement :meth:`is_available` and
    :meth:`run`."""

    tool_id: str
    binary: str | None = None  # for shell-based tools

    def is_available(self) -> bool:
        if self.binary is None:
            return True
        return shutil.which(self.binary) is not None

    def version(self) -> str | None:  # pragma: no cover - per-tool override
        return None

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolRunResult:  # pragma: no cover
        ...


@dataclass
class ShellResult:
    return_code: int
    stdout: str
    stderr: str


def run_shell(
    cmd: str | list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
) -> ShellResult:
    """Thin wrapper over ``subprocess.run`` with friendly errors."""

    args = cmd if isinstance(cmd, list) else shlex.split(cmd)
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(args)}\n"
            f"stderr: {completed.stderr.strip()[:2000]}"
        )
    return ShellResult(
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
