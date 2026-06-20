"""Golden test: the real toolchain turns the full-adder fixture into a gate SVG.

Uses the Step-0 fixture and the actual yosys/netlistsvg binaries (no LLM), so it
validates the whole synthesis pipeline deterministically.
"""
from pathlib import Path

import pytest

from app.api.deps import get_schematic_pipeline
from app.pipeline.sandbox import UnsafeVerilogError, VerilogGuard

FIXTURE = Path(__file__).parent.parent / "fixtures" / "full_adder.v"


def test_full_adder_synthesizes_to_gate_svg():
    verilog = FIXTURE.read_text()
    result = get_schematic_pipeline().build(verilog, top="full_adder")

    assert result.error is None, result.error
    assert result.svg and result.svg.lstrip().startswith("<svg")
    assert result.renderer == "netlistsvg"
    # netlistsvg emits a <g> per cell; a full adder has xor/and/or gates.
    assert "cell_$xor" in result.svg or "$xor" in result.svg


def test_guard_rejects_system_task():
    with pytest.raises(UnsafeVerilogError):
        VerilogGuard().check('module m; initial $system("rm -rf /"); endmodule')
