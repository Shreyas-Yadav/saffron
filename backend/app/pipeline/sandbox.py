"""Process sandboxing: the single place that touches the filesystem and runs
external EDA tools. Every pipeline unit depends on the `Sandbox` abstraction
(not `subprocess`), so tools are mockable in tests and the security guard lives
in one spot.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class SandboxError(RuntimeError):
    """A command failed, timed out, or the binary was missing."""


class UnsafeVerilogError(ValueError):
    """Verilog contained a system task that can execute code / touch the host."""


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Workspace:
    """A scratch directory in which to write source files and run tools.

    Several tools share one workspace (e.g. yosys writes JSON, netlistsvg reads
    it), so the workspace — not a single command — is the unit of work.
    """

    def __init__(self, path: Path):
        self.path = path

    def write(self, name: str, content: str) -> Path:
        p = self.path / name
        p.write_text(content)
        return p

    def read(self, name: str) -> str:
        return (self.path / name).read_text()

    def run(self, argv: list[str], timeout: float = 20.0) -> CommandResult:
        if shutil.which(argv[0]) is None:
            raise SandboxError(f"required tool not found on PATH: {argv[0]}")
        try:
            proc = subprocess.run(
                argv,
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(f"{argv[0]} timed out after {timeout}s") from exc
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)


class Sandbox(ABC):
    """Provides isolated workspaces for running external tools."""

    @abstractmethod
    def workspace(self) -> "Iterator[Workspace]":  # contextmanager
        ...


class LocalSandbox(Sandbox):
    """Runs tools in a temp directory on the local machine with timeouts."""

    @contextmanager
    def workspace(self) -> Iterator[Workspace]:
        with tempfile.TemporaryDirectory(prefix="saffron-") as d:
            yield Workspace(Path(d))


# System tasks that let Verilog shell out, read/write host files, or run
# arbitrary code through Icarus' vvp. Reject before anything reaches a tool.
_FORBIDDEN = re.compile(r"\$(system|fopen|fwrite|fread|readmem[bh]|fscanf|fdisplay)\b")


class VerilogGuard:
    """Single-responsibility safety check on untrusted Verilog."""

    def check(self, verilog: str) -> None:
        m = _FORBIDDEN.search(verilog)
        if m:
            raise UnsafeVerilogError(
                f"disallowed system task `{m.group(0)}` in Verilog"
            )
