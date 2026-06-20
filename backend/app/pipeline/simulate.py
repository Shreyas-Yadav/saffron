"""Simulation: run a module + testbench through Icarus Verilog and turn the VCD
into a WaveDrom timing diagram.

Two single-responsibility pieces:
  - `Simulator`: compile + run -> raw VCD text
  - `vcd_to_wavedrom`: VCD text + signal order -> WaveDrom JSON
The pipeline (simulation.py) supplies the signal order from the netlist ports.
"""
from __future__ import annotations

import io
from abc import ABC, abstractmethod

from vcd.reader import TokenKind, tokenize

from .sandbox import Sandbox, SandboxError


class Simulator(ABC):
    @abstractmethod
    def run(self, verilog: str, testbench: str, top: str) -> str:
        """Compile + simulate; return raw VCD text (raises SandboxError on failure)."""


class IcarusSimulator(Simulator):
    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    def run(self, verilog: str, testbench: str, top: str) -> str:
        with self._sandbox.workspace() as ws:
            ws.write("design.v", verilog)
            ws.write("tb.v", testbench)
            comp = ws.run(["iverilog", "-o", "sim", "design.v", "tb.v"])
            if not comp.ok:
                raise SandboxError(comp.stderr.strip() or "iverilog compile failed")
            run = ws.run(["vvp", "sim"])
            if not run.ok:
                raise SandboxError(run.stderr.strip() or "vvp simulation failed")
            return ws.read("dut.vcd")


def vcd_to_wavedrom(vcd_text: str, names: list[str]) -> dict:
    """Convert VCD to WaveDrom showing only `names`, in that order.

    Every signal renders as a 0/1 square wave (textbook style): multi-bit buses are
    expanded into one binary signal per bit, MSB first, labelled `name[i]`. `.` holds
    the previous value; `x` marks undefined.
    """
    id_of: dict[str, str] = {}  # signal name -> vcd id (first occurrence wins)
    width_of: dict[str, int] = {}
    changes: dict[str, list[tuple[int, object]]] = {}
    now = 0

    for tok in tokenize(io.BytesIO(vcd_text.encode())):
        if tok.kind is TokenKind.VAR:
            id_of.setdefault(tok.var.reference, tok.var.id_code)
            width_of.setdefault(tok.var.id_code, tok.var.size)
            changes.setdefault(tok.var.id_code, [])
        elif tok.kind is TokenKind.CHANGE_TIME:
            now = tok.time_change
        elif tok.kind is TokenKind.CHANGE_SCALAR:
            changes.setdefault(tok.scalar_change.id_code, []).append(
                (now, str(tok.scalar_change.value))
            )
        elif tok.kind is TokenKind.CHANGE_VECTOR:
            changes.setdefault(tok.vector_change.id_code, []).append(
                (now, tok.vector_change.value)
            )

    ids = [id_of[n] for n in names if n in id_of]
    times = sorted({t for i in ids for t, _ in changes.get(i, [])})

    signals = []
    for name in names:
        ident = id_of.get(name)
        if ident is None:
            continue
        evs = sorted(changes.get(ident, []), key=lambda e: e[0])
        width = width_of.get(ident, 1)
        if width <= 1:
            signals.append(_binary_signal(name, evs, times, bit=None))
        else:
            for bit in range(width - 1, -1, -1):  # MSB first
                signals.append(
                    _binary_signal(f"{name}[{bit}]", evs, times, bit=bit)
                )

    return {"signal": signals}


def _binary_signal(
    label: str, evs: list[tuple[int, object]], times: list[int], bit: int | None
) -> dict:
    wave, prev = "", None
    for t in times:
        raw: object = None
        for et, ev in evs:
            if et <= t:
                raw = ev
            else:
                break
        v = _bit_value(raw, bit)
        wave += "." if v == prev else v
        prev = v
    return {"name": label, "wave": wave}


def _bit_value(raw: object, bit: int | None) -> str:
    """One character ('0'/'1'/'x') for a scalar value, or for bit `bit` of a bus."""
    if raw is None:
        return "x"
    if bit is None:
        return raw if raw in ("0", "1") else "x"
    try:
        return "1" if (int(raw) >> bit) & 1 else "0"
    except (TypeError, ValueError):
        return "x"
