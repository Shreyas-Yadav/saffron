"""Agentic generation: Claude drives the pipeline via tool use.

Contrast with `GenerateOrchestrator`, where Python hard-codes the
generate->synthesize->repair->simulate->formal->timing sequence and the LLM only
emits text. Here Claude is given the pipeline as *tools* and decides what to do next:
it writes Verilog in its own turn, calls `synthesize` to validate it, reads the tool
error, decides whether to fix or move on to `simulate`/`formal`/`timing`, and signals
completion by calling the terminal `submit_final` tool.

This module is intentionally the one place allowed to couple to the Anthropic tool-use
API surface (`messages.create(tools=...)` + a `stop_reason == "tool_use"` loop), the
same way `_ClaudeProvider` isolates the structured-output surface. It reuses the exact
same pipeline objects the non-agentic path uses, so the hardware tooling is unchanged.

The loop's tool calls are the agent's scratchpad. The returned `GenerateOutcome` is
NOT trusted from loop bookkeeping: `submit_final` re-runs the real pipeline on the
submitted Verilog, so the schematic/waveform/verdict you return always correspond to
the code the agent actually submitted.
"""
from __future__ import annotations

import json

from ..models import (
    ChatMessage,
    FormalResult,
    GenerateOutcome,
    SimResult,
    TimingResult,
)
from .sanitize import sanitize_verilog_with_report
from .schematic import SchematicPipeline
from .simulation import SimulationPipeline
from .steps import (
    formal_step,
    generation_step,
    sanitize_step,
    schematic_step,
    simulation_step,
    timing_step,
)
from .timing_pipeline import TimingPipeline
from .verification import FormalPipeline


class AgenticError(RuntimeError):
    """The agent loop could not produce a result (model error or no submission)."""


_SYSTEM = """You are an expert Verilog designer working as an autonomous agent. The \
user describes a circuit; you produce ONE synthesizable Verilog module and validate it \
with the hardware tools available to you, then submit it.

Workflow:
- Write the module, then call `synthesize` to compile it with the real toolchain.
- If `synthesize` returns an error, read it and call `synthesize` again with a fix.
  Don't reintroduce earlier mistakes; address the exact cause.
- Once it synthesizes, you MAY call `simulate`, `formal`, and `timing` to sanity-check
  behavior, but none is required to finish.
- When you are confident in the module, call `submit_final` with the final source. This
  ends your turn — do not keep working after submitting.

Rules:
- Synthesizable RTL only. No testbenches, no `$display`/`$system`/`$fopen`/`$readmem`.
- The synthesizable SystemVerilog subset is allowed (yosys `read_verilog -sv`,
  iverilog `-g2012`): `logic`, `always_comb`/`always_ff`, `for (int i = ...)` loops.
  Avoid non-synthesizable constructs (delays, `initial`, dynamic arrays).
- `top_module` MUST exactly match the module name you declare.
- For COMBINATIONAL modules, supply `properties`: a short list of formal assertions,
  each a SINGLE boolean Verilog expression over the module's OWN ports only (no
  `assert`, no `;`), true for every input — e.g. for an adder `"{cout, sum} == a + b + cin"`.
  For clocked modules, use an empty list.
"""


def _verilog_param(desc: str) -> dict:
    return {"type": "string", "description": desc}


# JSON-schema tool definitions. The pipeline backends need a netlist from a prior
# synthesis; the orchestrator caches it per run, so the agent's tools take only
# `verilog`/`top` and never pass netlist JSON around.
TOOLS = [
    {
        "name": "synthesize",
        "description": (
            "Compile a Verilog module to a gate-level netlist with yosys and render a "
            "schematic. Returns an error string if synthesis fails. Call this first and "
            "after every fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verilog": _verilog_param("Complete module source."),
                "top": {"type": "string", "description": "Top module name."},
            },
            "required": ["verilog", "top"],
        },
    },
    {
        "name": "simulate",
        "description": (
            "Run an auto-generated testbench with Icarus Verilog and return a waveform "
            "(or why it could not). Requires a module that already synthesizes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verilog": _verilog_param("Complete module source."),
                "top": {"type": "string", "description": "Top module name."},
            },
            "required": ["verilog", "top"],
        },
    },
    {
        "name": "formal",
        "description": (
            "Prove formal properties about the module with a SAT solver (and built-in "
            "well-formedness checks). Requires a module that already synthesizes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verilog": _verilog_param("Complete module source."),
                "top": {"type": "string", "description": "Top module name."},
                "properties": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Boolean Verilog expressions over the module's ports.",
                },
            },
            "required": ["verilog", "top"],
        },
    },
    {
        "name": "timing",
        "description": (
            "Map the module to a standard-cell library and estimate speed and area. "
            "Requires a module that already synthesizes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verilog": _verilog_param("Complete module source."),
                "top": {"type": "string", "description": "Top module name."},
            },
            "required": ["verilog", "top"],
        },
    },
    {
        "name": "submit_final",
        "description": (
            "Submit the finished module. This ends your turn. Provide the complete "
            "final source, the top module name, a one-sentence explanation for a human, "
            "and formal properties (empty list for clocked designs)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top_module": {"type": "string"},
                "verilog": _verilog_param("Complete final module source."),
                "explanation": {"type": "string"},
                "properties": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["top_module", "verilog", "explanation"],
        },
    },
]


class AgenticOrchestrator:
    def __init__(
        self,
        client,
        model: str,
        schematic: SchematicPipeline,
        simulation: SimulationPipeline,
        formal: FormalPipeline,
        timing: TimingPipeline,
        max_turns: int = 12,
        max_tokens: int = 16000,
        label: str = "Claude",
    ):
        # `client` is an Anthropic-compatible client exposing `messages.create(...)`
        # (first-party Anthropic or Vertex); injected by deps.py.
        self._client = client
        self._model = model
        self._schematic = schematic
        self._simulation = simulation
        self._formal = formal
        self._timing = timing
        self._max_turns = max_turns  # hard cost guard — the analog of max_attempts
        self._max_tokens = max_tokens
        self._label = label

    def generate(self, messages: list[ChatMessage]) -> GenerateOutcome:
        convo = [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages
        ]
        # Per-run cache so sim/formal/timing tools can reuse the last good netlist
        # without the agent ever handling JSON blobs.
        netlist: dict[str, str] = {}

        for _ in range(self._max_turns):
            try:
                resp = self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=_SYSTEM,
                    tools=TOOLS,
                    messages=convo,
                )
            except Exception as exc:  # SDK raises a variety of error types
                raise AgenticError(f"{self._label} request failed: {exc}") from exc

            if resp.stop_reason == "end_turn":
                # Agent stopped talking without submitting — nothing to return.
                break

            convo.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                if block.name == "submit_final":
                    return self._finalize(block.input)
                payload, is_error = self._run_tool(block.name, block.input, netlist)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(payload),
                        "is_error": is_error,
                    }
                )

            if not tool_results:
                # No actionable tool calls and not end_turn — avoid a wasted round.
                break
            convo.append({"role": "user", "content": tool_results})

        raise AgenticError(
            "The agent did not submit a module within the turn limit. Try rephrasing "
            "the request or raising max_turns."
        )

    # -- tools ---------------------------------------------------------------

    def _run_tool(self, name: str, args: dict, netlist: dict) -> tuple[dict, bool]:
        """Execute one pipeline tool. Returns (json-able payload, is_error).

        The payload is the agent's feedback, not the user-facing result; the final
        outcome is rebuilt authoritatively in `_finalize`.
        """
        verilog, _ = sanitize_verilog_with_report(args.get("verilog", ""))
        top = args.get("top")

        if name == "synthesize":
            schem = self._schematic.build(verilog, top)
            if schem.error is None and schem.netlist_json:
                netlist["json"] = schem.netlist_json  # cache for downstream tools
                return {"ok": True, "message": "Synthesized successfully."}, False
            netlist.pop("json", None)
            return {"ok": False, "error": schem.error or "no netlist produced"}, True

        if "json" not in netlist:
            return {
                "ok": False,
                "error": f"Call synthesize successfully before {name}.",
            }, True

        if name == "simulate":
            sim = self._simulation.run(verilog, netlist["json"], top)
            return {"ok": sim.error is None, "error": sim.error,
                    "has_waveform": sim.wavedrom is not None}, sim.error is not None

        if name == "formal":
            result = self._formal.run(
                verilog, netlist["json"], top, args.get("properties", [])
            )
            return {"ok": result.status in ("proven", "skipped"),
                    "status": result.status,
                    "checks": [
                        {"name": c.name, "kind": c.kind, "status": c.status}
                        for c in result.checks
                    ]}, result.status in ("refuted", "error")

        if name == "timing":
            result = self._timing.run(verilog, netlist["json"], top)
            return {"ok": result.error is None, "error": result.error,
                    "max_frequency_mhz": result.max_frequency_mhz,
                    "critical_path_ns": result.critical_path_ns}, result.error is not None

        return {"ok": False, "error": f"Unknown tool {name!r}."}, True

    # -- final build ---------------------------------------------------------

    def _finalize(self, submission: dict) -> GenerateOutcome:
        """Re-run the real pipeline on the submitted module so the returned schematic,
        waveform, and verdict faithfully correspond to the submitted code (rather than
        to whatever the agent last poked at during the loop)."""
        top = submission.get("top_module")
        explanation = submission.get("explanation", "")
        properties = submission.get("properties", [])
        verilog, report = sanitize_verilog_with_report(submission.get("verilog", ""))

        steps = [generation_step(explanation), sanitize_step(report)]
        schem = self._schematic.build(verilog, top)

        sim = SimResult()
        formal: FormalResult | None = None
        timing: TimingResult | None = None
        if schem.error is None and schem.netlist_json:
            sim = self._simulation.run(verilog, schem.netlist_json, top)
            formal = self._formal.run(verilog, schem.netlist_json, top, properties)
            timing = self._timing.run(verilog, schem.netlist_json, top)

        steps.append(schematic_step(schem.error))
        steps.extend([simulation_step(sim), formal_step(formal), timing_step(timing)])

        return GenerateOutcome(
            top_module=top,
            verilog=verilog,
            explanation=explanation,
            svg=schem.svg,
            renderer=schem.renderer,
            attempts=1,
            error=schem.error,
            wavedrom=sim.wavedrom,
            sim_error=sim.error,
            testbench=sim.testbench,
            formal=formal,
            timing=timing,
            steps=steps,
        )
