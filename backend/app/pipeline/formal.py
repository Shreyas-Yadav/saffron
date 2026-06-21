"""Formal verification: prove things about a module with Yosys' SAT engine.

Two complementary rule sources (see `FormalResult`):
  - **intent** rules — boolean assertions from the LLM describing what the circuit
    should do (e.g. `{cout,sum} == a + b + cin`). We wrap the module in a harness
    carrying one `assert` and let `sat -prove-asserts` check it for *every* input.
    A refuted rule yields a concrete failing vector, dumped as a counterexample
    waveform (reusing `vcd_to_wavedrom`).
  - **invariant** rules — true of any well-formed circuit regardless of intent:
    no combinational loops / multiple drivers (`check`), and no *accidental* latch
    (`$dlatch`, i.e. an incompletely-assigned `always @*`).

Scope (v1): intent proofs run on **combinational** modules, where SAT proves the
property for all inputs and never gives a false counterexample. For **clocked**
modules, sound intent proofs need inductive invariants (temporal induction doesn't
converge on arbitrary LLM properties and BMC over `$past` gives false failures), so
intent rules are reported as *skipped* there — but the invariants still run on every
design, clocked or not.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ..models import FormalCheck, FormalResult
from .sandbox import Sandbox
from .simulate import vcd_to_wavedrom
from .testbench import Port, find_clock


class FormalVerifier(ABC):
    @abstractmethod
    def verify(
        self, verilog: str, properties: list[str], top: str, ports: list[Port]
    ) -> FormalResult:
        """Prove intent + invariant rules about `top`; never raises for a refuted
        rule (that's a result, not an error)."""


def _hrange(width: int) -> str:
    return "" if width <= 1 else f"[{width - 1}:0] "


def _build_harness(top: str, ports: list[Port]) -> str:
    """A wrapper exposing the DUT's own ports (so `sat -show-ports` dumps clean
    names) with a placeholder `{ASSERT}` line for one intent property."""
    decls = ", ".join(
        f"{'input' if p.direction == 'input' else 'output'} {_hrange(p.width)}{p.name}"
        for p in ports
        if p.direction in ("input", "output")
    )
    conns = ", ".join(f".{p.name}({p.name})" for p in ports)
    return (
        f"module formal_harness({decls});\n"
        f"    {top} dut ({conns});\n"
        f"    always @* assert ({{ASSERT}});\n"
        f"endmodule\n"
    )


def sanitize_sat_vcd(raw: str) -> str:
    """Make a Yosys SAT-model VCD parseable by pyvcd: drop its unterminated
    `$dumpvars` keyword and normalise the `#-1` pseudo-time to `#0`."""
    out: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if s == "$dumpvars":
            continue
        if re.fullmatch(r"#-\d+", s):
            out.append("#0")
            continue
        out.append(line)
    return "\n".join(out) + "\n"


class YosysFormalVerifier(FormalVerifier):
    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    def verify(
        self, verilog: str, properties: list[str], top: str, ports: list[Port]
    ) -> FormalResult:
        inputs = [p for p in ports if p.direction == "input"]
        clocked = find_clock(inputs) is not None

        checks: list[FormalCheck] = []
        counterexample: dict | None = None

        # Invariants run on every design (clocked or not).
        checks.extend(self._invariants(verilog, top))

        # Intent proofs: combinational only (see module docstring).
        for prop in properties:
            if clocked:
                checks.append(
                    FormalCheck(
                        name=prop,
                        kind="intent",
                        status="skipped",
                        detail="clocked module — bounded sequential proof not run in v1",
                    )
                )
                continue
            check, cex = self._prove_intent(verilog, top, ports, prop)
            checks.append(check)
            if cex and counterexample is None:
                counterexample = cex

        return FormalResult(
            status=_overall(checks),
            bounded=False,
            checks=checks,
            counterexample=counterexample,
        )

    # --- invariants -------------------------------------------------------------

    def _invariants(self, verilog: str, top: str) -> list[FormalCheck]:
        results: list[FormalCheck] = []
        # No combinational loops / multiple drivers.
        results.append(
            self._yosys_invariant(
                verilog,
                name="no combinational loops or multiple drivers",
                script=f"read_verilog -sv design.v; prep -top {top}; check -assert",
                fail_detail="combinational loop or multiply-driven net detected",
            )
        )
        # No accidental latch (incomplete `always @*`).
        results.append(
            self._yosys_invariant(
                verilog,
                name="no accidental latches",
                script=(
                    f"read_verilog -sv design.v; prep -top {top}; "
                    "proc; opt; select -assert-none t:$dlatch"
                ),
                fail_detail="inferred latch — an `always @*` block is missing an assignment",
            )
        )
        return results

    def _yosys_invariant(
        self, verilog: str, name: str, script: str, fail_detail: str
    ) -> FormalCheck:
        with self._sandbox.workspace() as ws:
            ws.write("design.v", verilog)
            result = ws.run(["yosys", "-q", "-p", script])
        if result.ok:
            return FormalCheck(name=name, kind="invariant", status="passed")
        return FormalCheck(
            name=name, kind="invariant", status="failed", detail=fail_detail
        )

    # --- intent (combinational SAT) ---------------------------------------------

    def _prove_intent(
        self, verilog: str, top: str, ports: list[Port], prop: str
    ) -> tuple[FormalCheck, dict | None]:
        harness = _build_harness(top, ports).replace("{ASSERT}", prop)
        script = (
            "read_verilog -sv design.v harness.v; "
            "prep -top formal_harness -flatten; chformal -lower; "
            "sat -prove-asserts -show-ports -dump_vcd cex.vcd"
        )
        with self._sandbox.workspace() as ws:
            ws.write("design.v", verilog)
            ws.write("harness.v", harness)
            # No `-q`: the SAT verdict ("...SUCCESS!" / "...FAIL!") prints at a log
            # level that `-q` suppresses, and we parse that line below.
            result = ws.run(["yosys", "-p", script])
            out = result.stdout + result.stderr
            if "SUCCESS!" in out:
                return (
                    FormalCheck(
                        name=prop,
                        kind="intent",
                        status="passed",
                        detail="proven for all inputs",
                    ),
                    None,
                )
            if "FAIL!" in out:
                cex = self._counterexample(ws, ports)
                return (
                    FormalCheck(
                        name=prop,
                        kind="intent",
                        status="failed",
                        detail="counterexample found — property does not hold",
                    ),
                    cex,
                )
        # Neither marker → the property couldn't be checked (e.g. bad expression).
        detail = (result.stderr.strip() or "could not evaluate property")[:300]
        return (
            FormalCheck(name=prop, kind="intent", status="error", detail=detail),
            None,
        )

    def _counterexample(self, ws, ports: list[Port]) -> dict | None:
        try:
            vcd = sanitize_sat_vcd(ws.read("cex.vcd"))
        except (FileNotFoundError, OSError):
            return None
        names = [p.name for p in ports if p.direction == "input"] + [
            p.name for p in ports if p.direction == "output"
        ]
        wd = vcd_to_wavedrom(vcd, names)
        return wd if wd.get("signal") else None


def _overall(checks: list[FormalCheck]) -> str:
    if any(c.status == "failed" for c in checks):
        return "refuted"
    ran = [c for c in checks if c.status in ("passed", "failed")]
    if not ran:
        return "skipped"
    return "proven"
