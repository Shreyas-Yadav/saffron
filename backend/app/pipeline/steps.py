"""Student-facing explanations for the circuit pipeline.

These are deterministic templates over known stage outcomes. Raw tool text stays as
optional evidence; the primary explanation is short, plain language for learners.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import FormalResult, ProcessStep, SimResult, TimingResult


@dataclass(frozen=True)
class SanitizeReport:
    changed: bool
    replacements: int
    removed: int


def sanitize_step(report: SanitizeReport) -> ProcessStep:
    if not report.changed:
        return ProcessStep(
            id="sanitize",
            title="Cleaned the Verilog text",
            status="success",
            summary="The source text was already clean enough for the Verilog tools.",
            details=[
                "Saffron checks for invisible copy-paste characters before running tools.",
                "No risky look-alike spaces, quotes, or dashes needed to be changed.",
            ],
        )
    total = report.replacements + report.removed
    return ProcessStep(
        id="sanitize",
        title="Cleaned the Verilog text",
        status="warning",
        summary="Saffron fixed hidden copy-paste characters before running the tools.",
        details=[
            "Some characters can look like normal spaces or quotes but confuse Verilog parsers.",
            f"{total} character{'s' if total != 1 else ''} were normalized or removed.",
            "The circuit logic was not changed; only text encoding artifacts were cleaned.",
        ],
    )


def generation_step(explanation: str) -> ProcessStep:
    return ProcessStep(
        id="generate",
        title="Generated Verilog",
        status="success",
        summary="The AI turned your request into one synthesizable Verilog module.",
        details=[
            explanation or "The module was generated from the conversation.",
            "The next step is to run real hardware tools on the code instead of trusting the AI blindly.",
        ],
    )


def repair_attempt_step(attempt: int, error: str) -> ProcessStep:
    return ProcessStep(
        id=f"repair-{attempt}",
        title=f"Repair attempt {attempt}",
        status="warning",
        summary="The first version did not pass synthesis, so Saffron asked the AI to fix it.",
        details=[
            "A hardware tool found a concrete problem in the generated Verilog.",
            "The tool error was sent back to the model as feedback for the next attempt.",
        ],
        technical=error,
    )


def schematic_step(error: str | None, attempts: int = 1) -> ProcessStep:
    if error:
        return ProcessStep(
            id="synthesize",
            title="Synthesized the circuit",
            status="error",
            summary=_friendly_error(error),
            details=[
                "Synthesis is the step where Verilog is converted into gates and wires.",
                "Because this step failed, the schematic and later analysis tabs cannot be trusted yet.",
            ],
            technical=error,
        )
    repaired = attempts > 1
    return ProcessStep(
        id="synthesize",
        title="Synthesized the circuit",
        status="success",
        summary="Yosys converted the Verilog into a gate-level netlist.",
        details=[
            "This proves the code is parseable and structurally synthesizable.",
            "netlistsvg then rendered that netlist as the schematic you see.",
            "The circuit compiled after auto-repair." if repaired else "The circuit compiled on the first attempt.",
        ],
    )


def simulation_step(sim: SimResult) -> ProcessStep:
    if sim.error:
        return ProcessStep(
            id="simulate",
            title="Simulated example inputs",
            status="warning",
            summary="Saffron could not produce a waveform for this design.",
            details=[
                "Simulation runs the circuit on example inputs over time.",
                "A missing waveform does not necessarily mean synthesis failed; it means this analysis could not run.",
            ],
            technical=sim.error,
        )
    if sim.wavedrom:
        return ProcessStep(
            id="simulate",
            title="Simulated example inputs",
            status="success",
            summary="Icarus Verilog ran an auto-generated testbench and produced a waveform.",
            details=[
                "For combinational circuits, Saffron tries several input combinations.",
                "For clocked circuits, it creates a clock and drives inputs for a few cycles.",
                "The Waveform tab shows the signal values from that run.",
            ],
        )
    return ProcessStep(
        id="simulate",
        title="Simulated example inputs",
        status="skipped",
        summary="No waveform was produced for this run.",
        details=["The schematic can still be inspected even when simulation is skipped."],
    )


def skipped_step(id: str, title: str, reason: str) -> ProcessStep:
    return ProcessStep(
        id=id,
        title=title,
        status="skipped",
        summary=f"This step was skipped because {reason}.",
        details=["Fix the earlier step first, then run the pipeline again."],
    )


def formal_step(formal: FormalResult | None) -> ProcessStep:
    if formal is None:
        return ProcessStep(
            id="formal",
            title="Checked formal rules",
            status="skipped",
            summary="Formal verification did not run for this result.",
        )
    if formal.status == "refuted":
        return ProcessStep(
            id="formal",
            title="Checked formal rules",
            status="error",
            summary="The solver found a case where one rule does not hold.",
            details=[
                "SAT checks look for a counterexample instead of trying examples one by one.",
                "When a counterexample exists, the Formal tab can show the failing input vector.",
            ],
            technical=formal.logs or _checks_text(formal),
        )
    if formal.status == "error":
        return ProcessStep(
            id="formal",
            title="Checked formal rules",
            status="warning",
            summary="Formal verification could not complete.",
            details=[
                "This does not block the schematic; it only means the extra proof step failed.",
            ],
            technical=formal.logs or _checks_text(formal),
        )
    if formal.status == "proven":
        has_intent = any(c.kind == "intent" and c.status == "passed" for c in formal.checks)
        return ProcessStep(
            id="formal",
            title="Checked formal rules",
            status="success",
            summary=(
                "The SAT checker proved the generated intent rule for all inputs."
                if has_intent
                else "The circuit passed built-in well-formedness checks."
            ),
            details=[
                "Built-in checks look for structural issues like loops or accidental latches.",
                "For combinational designs, intent rules can be proven for all possible inputs.",
            ],
            technical=_checks_text(formal),
        )
    return ProcessStep(
        id="formal",
        title="Checked formal rules",
        status="skipped",
        summary="No formal checks were applicable for this run.",
        technical=_checks_text(formal),
    )


def timing_step(timing: TimingResult | None) -> ProcessStep:
    if timing is None:
        return ProcessStep(
            id="timing",
            title="Estimated speed and area",
            status="skipped",
            summary="Timing analysis did not run for this result.",
        )
    if timing.error:
        return ProcessStep(
            id="timing",
            title="Estimated speed and area",
            status="warning",
            summary="Saffron could not run full OpenSTA timing, so it kept the available estimate.",
            details=[
                "Timing maps the circuit to a standard-cell library to estimate speed and area.",
                "If Docker/OpenSTA is unavailable, Saffron can still report yosys area and cell counts.",
            ],
            technical=timing.error,
        )
    metric = (
        f"maximum clock frequency is about {timing.max_frequency_mhz} MHz"
        if timing.clocked and timing.max_frequency_mhz is not None
        else f"slowest input-to-output delay is about {timing.critical_path_ns} ns"
        if timing.critical_path_ns is not None
        else "timing completed"
    )
    return ProcessStep(
        id="timing",
        title="Estimated speed and area",
        status="success",
        summary=f"OpenSTA timed the mapped circuit; {metric}.",
        details=[
            "This uses a real cell library, so it is closer to hardware than a plain schematic.",
            "The Timing tab shows the critical-path cell types and area numbers.",
        ],
    )


def _friendly_error(error: str) -> str:
    low = error.lower()
    if "syntax error" in low or "unexpected" in low:
        return "The synthesis tool could not parse the Verilog syntax."
    if "required tool not found" in low:
        return "A required hardware tool is missing from the local environment."
    if "timed out" in low:
        return "A hardware tool took too long and was stopped."
    if "disallowed system task" in low:
        return "The Verilog used a system task that Saffron blocks for safety."
    return "The synthesis tool reported an error while building the circuit."


def _checks_text(formal: FormalResult) -> str | None:
    if not formal.checks:
        return None
    lines = []
    for check in formal.checks:
        detail = f": {check.detail}" if check.detail else ""
        lines.append(f"{check.status.upper()} [{check.kind}] {check.name}{detail}")
    return "\n".join(lines)
