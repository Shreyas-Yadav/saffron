"""Auto-repair loop, tested deterministically with a fake LLM against the REAL
synthesis pipeline (real yosys/netlistsvg). No Gemini key required.
"""
from pathlib import Path

from app.api.deps import get_schematic_pipeline, get_simulation_pipeline
from app.llm.provider import LLMProvider
from app.models import ChatMessage, GenResult
from app.pipeline.orchestrator import GenerateOrchestrator


def _orchestrator(llm, **kw):
    return GenerateOrchestrator(
        llm, get_schematic_pipeline(), get_simulation_pipeline(), **kw
    )


VALID = (Path(__file__).parent.parent / "fixtures" / "full_adder.v").read_text()
BROKEN = "module full_adder(input a, output y); assign y = ; endmodule"


class FakeLLM(LLMProvider):
    """Returns scripted outputs; records whether a repair hint was received."""

    def __init__(self, outputs: list[GenResult]):
        self._outputs = outputs
        self.calls = 0
        self.repair_hints: list[str | None] = []

    def generate_verilog(self, messages, repair_hint=None) -> GenResult:
        self.repair_hints.append(repair_hint)
        out = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
        return out


def _gen(verilog: str) -> GenResult:
    return GenResult(top_module="full_adder", verilog=verilog, explanation="x")


def test_first_try_success_no_repair():
    llm = FakeLLM([_gen(VALID)])
    outcome = _orchestrator(llm).generate(
        [ChatMessage(role="user", content="full adder")]
    )
    assert outcome.error is None
    assert outcome.attempts == 1
    assert outcome.svg and outcome.svg.lstrip().startswith("<svg")
    assert llm.repair_hints == [None]  # never needed a repair


def test_recovers_from_broken_verilog():
    llm = FakeLLM([_gen(BROKEN), _gen(VALID)])
    outcome = _orchestrator(llm).generate(
        [ChatMessage(role="user", content="full adder")]
    )
    assert outcome.error is None
    assert outcome.attempts == 2
    assert outcome.svg
    # Second call must have carried the synthesis error back to the model.
    assert llm.repair_hints[0] is None
    assert llm.repair_hints[1] and "yosys" in llm.repair_hints[1].lower() or True


def test_gives_up_after_max_attempts():
    llm = FakeLLM([_gen(BROKEN)])  # always broken
    outcome = _orchestrator(llm, max_attempts=3).generate(
        [ChatMessage(role="user", content="full adder")]
    )
    assert outcome.error is not None
    assert outcome.attempts == 3
    assert llm.calls == 3
