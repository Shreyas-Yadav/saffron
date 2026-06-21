"""Typed contracts shared between units. Pydantic models are the only data that
crosses unit boundaries, so each unit can be understood and tested in isolation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FormalCheck(BaseModel):
    """One rule the formal checker tried to prove about a design.

    `kind="intent"` rules come from the LLM (what the circuit should *do*);
    `kind="invariant"` rules are true of any well-formed circuit (no loops, no
    accidental latches) regardless of intent.
    """

    name: str
    kind: Literal["intent", "invariant"]
    status: Literal["passed", "failed", "skipped", "error"]
    detail: str = ""


class FormalResult(BaseModel):
    """Output of the formal-verification pipeline (Yosys SAT).

    `status` is the overall verdict; `checks` is the per-rule breakdown. When an
    intent rule is refuted, `counterexample` carries the failing input vector as a
    WaveDrom diagram (rendered with the same panel as the simulation waveform).
    """

    status: Literal["proven", "refuted", "skipped", "error"]
    bounded: bool = False  # True only for bounded (sequential) proofs
    cycles: int | None = None
    checks: list[FormalCheck] = Field(default_factory=list)
    counterexample: dict | None = None
    logs: str = ""


class TimingResult(BaseModel):
    """Output of static timing analysis: how fast the mapped circuit can run.

    The design is synthesized to a real standard-cell library (Nangate45) and timed.
    For a **clocked** design, `max_frequency_mhz` is the fastest the clock can run;
    for a **combinational** one it's null and `critical_path_ns` is the input→output
    propagation delay. `source` records whether OpenSTA produced the numbers or we
    fell back to a yosys-only area/cell estimate (no max frequency).
    """

    clocked: bool = False
    max_frequency_mhz: float | None = None
    critical_path_ns: float | None = None
    critical_path_cells: list[str] = Field(default_factory=list)
    area_um2: float | None = None
    cell_count: int | None = None
    source: Literal["opensta", "yosys-estimate"] = "opensta"
    error: str | None = None
    logs: str = ""


class SchematicResult(BaseModel):
    """Output of the synthesis + render pipeline."""

    svg: str | None = None
    renderer: str | None = None  # which SchematicRenderer produced the svg
    netlist_json: str | None = None  # yosys JSON (handy for debugging/waveform)
    error: str | None = None
    logs: str = ""
    # Best-effort simulation result attached by the /synthesize route.
    wavedrom: dict | None = None
    sim_error: str | None = None
    # Best-effort formal-verification result attached by the /synthesize route.
    formal: FormalResult | None = None
    # Best-effort static-timing result attached by the /synthesize route.
    timing: TimingResult | None = None


class SimResult(BaseModel):
    """Output of the simulation pipeline: a WaveDrom timing diagram (or why not)."""

    wavedrom: dict | None = None
    error: str | None = None
    logs: str = ""


class SynthesizeRequest(BaseModel):
    """Step 1 endpoint: synthesize a known Verilog string into a schematic."""

    verilog: str = Field(..., description="Synthesizable Verilog source")
    top: str | None = Field(None, description="Top module name; auto-detected if omitted")


class GenResult(BaseModel):
    """What an LLMProvider returns: a synthesizable module + metadata."""

    top_module: str
    verilog: str
    explanation: str
    # Intent assertions (boolean Verilog expressions over the module's ports) the
    # formal checker can prove. Optional — empty means "invariants only".
    properties: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    """Full conversation so far; the latest user turn drives generation.

    Sending history (not just the last turn) is what makes iteration work in Step 4
    — 'now make it 4-bit' refines the prior module.
    """

    messages: list[ChatMessage]


class GenerateOutcome(BaseModel):
    """Result of generate→synthesize→repair: code AND schematic in one shot.

    `attempts` is how many generations it took to compile (1 = first try). `error` is
    non-null only if it still failed after the last attempt.
    """

    top_module: str
    verilog: str
    explanation: str
    svg: str | None = None
    renderer: str | None = None
    attempts: int = 1
    error: str | None = None
    # Best-effort waveform (combinational modules); null if simulation was skipped
    # or failed. `sim_error` explains a failure without blocking the schematic.
    wavedrom: dict | None = None
    sim_error: str | None = None
    # Best-effort formal-verification result; null if it was skipped or errored.
    formal: FormalResult | None = None
    # Best-effort static-timing result; null if it was skipped or errored.
    timing: TimingResult | None = None
