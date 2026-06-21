"""Timing analysis tests. The report parsers run everywhere (pure functions); the
full OpenSTA path is skipped unless Docker + the openroad/opensta image are present,
so the suite stays green without Docker.
"""
import shutil
import subprocess

import pytest

from app.api.deps import get_schematic_pipeline, get_timing_pipeline
from app.pipeline.timing import _parse_sta, _parse_stat

# --- pure parser tests (no Docker) ------------------------------------------------

STAT = """
       55   90.972 cells
        8   36.176   DFF_X1
   Chip area for module '\\ctr': 90.972000
"""

STA_REPORT = """
Startpoint: _103_ (rising edge-triggered flip-flop clocked by clk)
Endpoint: _109_ (rising edge-triggered flip-flop clocked by clk)
   0.0000    0.0000 ^ _103_/CK (DFF_X1)
   0.0932    0.0932 ^ _103_/Q (DFF_X1)
   0.0460    0.1391 ^ _063_/ZN (XNOR2_X1)
             0.4668   data arrival time
             1.4940   slack (MET)
WORST_SLACK 1.494042265525609
"""


def test_parse_stat_extracts_area_and_cells():
    area, cells = _parse_stat(STAT)
    assert area == 90.972
    assert cells == 55


def test_parse_sta_computes_max_frequency_for_clocked():
    # period 2.0 ns, slack 1.494 -> min period 0.506 ns -> ~1976 MHz.
    res = _parse_sta(STA_REPORT, period=2.0, clocked=True, area=90.972, cells=55)
    assert res.source == "opensta"
    assert res.clocked is True
    assert res.max_frequency_mhz == pytest.approx(1976.3, abs=1.0)
    assert res.start_point == "_103_" and res.end_point == "_109_"
    # The launch flop's CK+Q lines merge into one DFF_X1 stage, then the XNOR2.
    cells = [s.cell for s in res.critical_path]
    assert cells == ["DFF_X1", "XNOR2_X1"]
    assert res.critical_path[0].delay_ns == pytest.approx(0.0932, abs=1e-3)
    # Instance names are captured (used to render the path schematic).
    assert [s.instance for s in res.critical_path] == ["_103_", "_063_"]


def test_parse_sta_combinational_has_no_frequency():
    res = _parse_sta(STA_REPORT, period=2.0, clocked=False, area=5.5, cells=5)
    assert res.max_frequency_mhz is None
    assert res.critical_path_ns == pytest.approx(0.4668, abs=1e-3)


def test_parse_sta_without_paths_degrades():
    res = _parse_sta("no timing here", period=2.0, clocked=True, area=None, cells=None)
    assert res.source == "yosys-estimate"
    assert res.error


# --- full OpenSTA path (Docker-gated) ---------------------------------------------


def _opensta_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", "openroad/opensta"],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


requires_opensta = pytest.mark.skipif(
    not _opensta_available(), reason="Docker + openroad/opensta image not available"
)

COUNTER = (
    "module ctr(input clk, input rst_n, input en, input [7:0] din,"
    " output reg [7:0] q);\n"
    "  always @(posedge clk) if(!rst_n) q<=0; else if(en) q<=q+din;\n"
    "endmodule"
)


@requires_opensta
def test_clocked_design_reports_real_frequency():
    net = get_schematic_pipeline().build(COUNTER, "ctr").netlist_json
    t = get_timing_pipeline().run(COUNTER, net, "ctr")
    assert t.source == "opensta", t.error
    assert t.clocked is True
    assert t.max_frequency_mhz and t.max_frequency_mhz > 0
    assert t.area_um2 and t.cell_count
    assert any("DFF" in s.cell for s in t.critical_path)
    assert t.start_point and t.end_point
    # The path schematic renders (needs graphviz `dot`, present with the toolchain).
    assert t.critical_path_svg and "<svg" in t.critical_path_svg
