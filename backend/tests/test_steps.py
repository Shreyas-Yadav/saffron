"""Student-facing process steps for /synthesize and the repair orchestrator."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import (
    get_formal_pipeline,
    get_llm_provider,
    get_schematic_pipeline,
    get_simulation_pipeline,
)
from app.main import app
from app.llm.provider import LLMError, LLMProvider
from app.models import ChatMessage, GenResult, ProcessStep, StepExplanation, TimingResult
from app.pipeline.orchestrator import GenerateOrchestrator


FIXTURES = Path(__file__).parent.parent / "fixtures"
FULL_ADDER = (FIXTURES / "full_adder.v").read_text()
NBSP = "\u00a0"


class _StubTiming:
    def run(self, verilog, netlist_json, top):
        return TimingResult(source="yosys-estimate", area_um2=1.0, cell_count=1)


class _FakeLLM(LLMProvider):
    def __init__(self, outputs: list[GenResult]):
        self._outputs = outputs
        self.calls = 0

    def generate_verilog(self, messages, repair_hint=None) -> GenResult:
        out = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
        return out

    def explain_step(self, verilog, top_module, step) -> StepExplanation:
        return StepExplanation(
            headline=f"Here's what '{step.title}' means for your circuit.",
            points=["A first teaching point.", "A second teaching point."],
        )


def _orchestrator(llm, **kw):
    return GenerateOrchestrator(
        llm,
        get_schematic_pipeline(),
        get_simulation_pipeline(),
        get_formal_pipeline(),
        _StubTiming(),
        **kw,
    )


def _gen(verilog: str) -> GenResult:
    return GenResult(top_module="full_adder", verilog=verilog, explanation="full adder")


def test_synthesize_returns_student_steps():
    res = TestClient(app).post(
        "/api/synthesize",
        json={"verilog": FULL_ADDER, "top": "full_adder"},
    )
    assert res.status_code == 200
    steps = res.json()["steps"]
    ids = [s["id"] for s in steps]
    assert ids == ["sanitize", "synthesize", "simulate", "formal", "timing"]
    assert steps[0]["summary"]
    assert steps[1]["status"] == "success"


def test_dirty_paste_reports_sanitize_cleanup():
    dirty = f"module m (input{NBSP}wire a, output y); assign y = a; endmodule"
    res = TestClient(app).post(
        "/api/synthesize",
        json={"verilog": dirty, "top": "m"},
    )
    assert res.status_code == 200
    clean_step = res.json()["steps"][0]
    assert clean_step["id"] == "sanitize"
    assert clean_step["status"] == "warning"
    assert "copy-paste" in clean_step["summary"]


def test_repair_attempt_is_visible_in_steps():
    broken = "module full_adder(input a, output y); assign y = ; endmodule"
    outcome = _orchestrator(_FakeLLM([_gen(broken), _gen(FULL_ADDER)])).generate(
        [ChatMessage(role="user", content="full adder")]
    )
    ids = [s.id for s in outcome.steps]
    assert "repair-1" in ids
    repair = next(s for s in outcome.steps if s.id == "repair-1")
    assert repair.status == "warning"
    assert repair.technical
    assert outcome.error is None


_SAMPLE_STEP = {
    "id": "simulate",
    "title": "Simulated example inputs",
    "status": "success",
    "summary": "Icarus ran a testbench and produced a waveform.",
    "details": [],
    "technical": None,
}


def test_explain_step_returns_plain_language():
    app.dependency_overrides[get_llm_provider] = lambda: _FakeLLM([_gen(FULL_ADDER)])
    try:
        res = TestClient(app).post(
            "/api/explain-step",
            json={"verilog": FULL_ADDER, "top_module": "full_adder", "step": _SAMPLE_STEP},
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)
    assert res.status_code == 200
    body = res.json()
    assert body["headline"]
    assert len(body["points"]) >= 1


def test_explain_step_surfaces_llm_error_as_502():
    class _BrokenLLM(_FakeLLM):
        def explain_step(self, verilog, top_module, step):
            raise LLMError("GEMINI_API_KEY is not set.")

    app.dependency_overrides[get_llm_provider] = lambda: _BrokenLLM([_gen(FULL_ADDER)])
    try:
        res = TestClient(app).post(
            "/api/explain-step",
            json={"verilog": FULL_ADDER, "step": _SAMPLE_STEP},
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)
    assert res.status_code == 502
