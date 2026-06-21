"""Agentic tool-use loop, tested with a fake Claude client against the REAL synthesis
pipeline (real yosys/netlistsvg). No Anthropic key required.

Mirrors test_orchestrator.py: the model is faked, the hardware tools are real.
"""
import json
from pathlib import Path

import pytest

from app.api.deps import (
    get_formal_pipeline,
    get_schematic_pipeline,
    get_simulation_pipeline,
)
from app.models import ChatMessage, TimingResult
from app.pipeline.agentic import AgenticError, AgenticOrchestrator

VALID = (Path(__file__).parent.parent / "fixtures" / "full_adder.v").read_text()
BROKEN = "module full_adder(input a, output y); assign y = ; endmodule"


class _StubTiming:
    """Timing runs OpenSTA in Docker (slow); the loop tests don't exercise it."""

    def run(self, verilog, netlist_json, top):
        return TimingResult(source="yosys-estimate")


class _ToolUse:
    type = "tool_use"

    def __init__(self, name, input, id="t1"):
        self.name = name
        self.input = input
        self.id = id


class _Resp:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    """Returns scripted responses and records the messages sent on each call."""

    def __init__(self, scripted):
        self._scripted = scripted
        self.calls = 0
        self.message_log: list[list] = []

    def create(self, **kw):
        self.message_log.append(list(kw["messages"]))  # snapshot
        out = self._scripted[min(self.calls, len(self._scripted) - 1)]
        self.calls += 1
        return out


class _FakeClient:
    def __init__(self, scripted):
        self.messages = _FakeMessages(scripted)


def _orchestrator(scripted, **kw):
    client = _FakeClient(scripted)
    orch = AgenticOrchestrator(
        client=client,
        model="fake",
        schematic=get_schematic_pipeline(),
        simulation=get_simulation_pipeline(),
        formal=get_formal_pipeline(),
        timing=_StubTiming(),
        **kw,
    )
    return orch, client


def _synth(verilog):
    return _Resp([_ToolUse("synthesize", {"verilog": verilog, "top": "full_adder"})])


def _submit(verilog=VALID):
    return _Resp(
        [
            _ToolUse(
                "submit_final",
                {
                    "top_module": "full_adder",
                    "verilog": verilog,
                    "explanation": "A full adder.",
                    "properties": [],
                },
            )
        ]
    )


def _tool_results(messages):
    """All tool_result blocks across a recorded messages snapshot."""
    blocks = []
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            blocks.extend(b for b in m["content"] if b.get("type") == "tool_result")
    return blocks


def test_synthesize_then_submit():
    orch, client = _orchestrator([_synth(VALID), _submit()])
    outcome = orch.generate([ChatMessage(role="user", content="full adder")])
    assert outcome.error is None
    assert outcome.svg and outcome.svg.lstrip().startswith("<svg")
    assert client.messages.calls == 2


def test_failed_synthesize_is_fed_back_as_error():
    orch, client = _orchestrator([_synth(BROKEN), _synth(VALID), _submit()])
    outcome = orch.generate([ChatMessage(role="user", content="full adder")])
    assert outcome.error is None  # final submitted module is valid
    # The broken synthesis must have been returned to the model with is_error=True.
    fed_back = [b for snap in client.messages.message_log for b in _tool_results(snap)]
    assert any(b["is_error"] for b in fed_back)


def test_downstream_tool_requires_synthesize_first():
    # simulate before any successful synthesize -> guarded error, no netlist used.
    sim_first = _Resp(
        [_ToolUse("simulate", {"verilog": VALID, "top": "full_adder"})]
    )
    orch, client = _orchestrator([sim_first, _submit()])
    orch.generate([ChatMessage(role="user", content="full adder")])
    fed_back = [b for snap in client.messages.message_log for b in _tool_results(snap)]
    guard = [b for b in fed_back if "synthesize" in b["content"]]
    assert guard and guard[0]["is_error"]
    assert not json.loads(guard[0]["content"])["ok"]


def test_gives_up_after_max_turns():
    # Never submits -> the turn cap stops a runaway loop.
    orch, _ = _orchestrator([_synth(VALID)], max_turns=2)
    with pytest.raises(AgenticError):
        orch.generate([ChatMessage(role="user", content="full adder")])
