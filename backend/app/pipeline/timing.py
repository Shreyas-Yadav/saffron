"""Static timing analysis: how fast can the circuit actually run?

The schematic's `prep` netlist is *untimed* generic logic, so timing needs its own
flow: map the design onto a real standard-cell library (Nangate45) with yosys, then
ask OpenSTA for the critical path. Two engines behind one `TimingAnalyzer` interface:

  - `OpenStaTimingAnalyzer` — yosys maps to cells (and reports area), then OpenSTA
    (run in a Docker container) times the register-to-register / input-to-output
    path. Max frequency = 1 / (clock_period - worst_slack).
  - If Docker/OpenSTA is unavailable it degrades gracefully to the yosys area+cell
    estimate alone (`source="yosys-estimate"`, no max frequency) rather than failing.
"""
from __future__ import annotations

import gzip
import re
from abc import ABC, abstractmethod
from pathlib import Path

from ..models import PathStage, TimingResult
from .sandbox import Sandbox, SandboxError
from .testbench import Port, find_clock

# Map to real cells AND report area in one yosys run (area is always available, even
# when OpenSTA isn't). NOT the schematic's `prep` flow — that leaves untimed logic.
_MAP_SCRIPT = (
    "read_verilog design.v; synth -top {top} -flatten; "
    "dfflibmap -liberty nangate.lib; abc -liberty nangate.lib; opt; clean; "
    "tee -o stat.txt stat -liberty nangate.lib; "
    "write_verilog -noattr mapped.v"
)


class TimingAnalyzer(ABC):
    @abstractmethod
    def analyze(self, verilog: str, top: str, clock: Port | None) -> TimingResult:
        """Map + time `top`; never raises (returns TimingResult(error=...))."""


class OpenStaTimingAnalyzer(TimingAnalyzer):
    def __init__(
        self,
        sandbox: Sandbox,
        liberty_gz: str | Path,
        docker_image: str = "openroad/opensta",
        platform: str = "linux/amd64",
        period_ns: float = 10.0,
    ):
        self._sandbox = sandbox
        self._liberty_gz = Path(liberty_gz)
        self._image = docker_image
        self._platform = platform
        self._period = period_ns

    def analyze(self, verilog: str, top: str, clock: Port | None) -> TimingResult:
        liberty = gzip.decompress(self._liberty_gz.read_bytes()).decode()
        with self._sandbox.workspace() as ws:
            ws.write("design.v", verilog)
            ws.write("nangate.lib", liberty)

            # 1. Map to real cells + area (host yosys). Area is reported even if STA
            #    later fails, so a missing Docker still yields a useful readout.
            mapped = ws.run(
                ["yosys", "-q", "-p", _MAP_SCRIPT.format(top=top)], timeout=60
            )
            if not mapped.ok:
                return TimingResult(
                    source="yosys-estimate",
                    error=(mapped.stderr.strip() or "yosys mapping failed")[:300],
                )
            area, cells = _parse_stat(ws.read("stat.txt"))
            clocked = clock is not None

            # 2. Time the mapped netlist with OpenSTA (Docker). Best-effort: on any
            #    failure, keep the area/cell estimate and explain why.
            ws.write("run.tcl", _run_tcl(top, clock, self._period))
            try:
                sta = ws.run(
                    [
                        "docker", "run", "--rm", "--platform", self._platform,
                        "-v", f"{ws.path}:/work", self._image,
                        "-no_init", "-exit", "/work/run.tcl",
                    ],
                    timeout=240,
                )
            except SandboxError as exc:
                return TimingResult(
                    clocked=clocked, area_um2=area, cell_count=cells,
                    source="yosys-estimate", error=str(exc),
                )
            if not sta.ok:
                return TimingResult(
                    clocked=clocked, area_um2=area, cell_count=cells,
                    source="yosys-estimate",
                    error=(sta.stderr.strip() or "OpenSTA failed")[:300],
                )

            result = _parse_sta(
                sta.stdout, period=self._period, clocked=clocked,
                area=area, cells=cells,
            )
            # Render a schematic of just the critical path (its gates + wiring) from
            # the mapped netlist. Best-effort: a render failure leaves the rest intact.
            instances = [s.instance for s in result.critical_path if s.instance]
            if instances:
                result.critical_path_svg = self._render_path(ws, top, instances)
            return result

    def _render_path(self, ws, top: str, instances: list[str]) -> str | None:
        """`yosys show` of only the path cells -> an SVG where every gate and wire
        shown belongs to the critical path. Needs graphviz `dot` (which yosys execs)."""
        selection = " ".join(f"c:{i}" for i in instances)
        script = (
            f"read_verilog mapped.v; "
            f"show -format svg -prefix cp -notitle {selection}"
        )
        try:
            res = ws.run(["yosys", "-p", script], timeout=60)
            if not res.ok:
                return None
            return ws.read("cp.svg")
        except (SandboxError, FileNotFoundError, OSError):
            return None


def _run_tcl(top: str, clock: Port | None, period: float) -> str:
    head = (
        "read_liberty /work/nangate.lib\n"
        "read_verilog /work/mapped.v\n"
        f"link_design {top}\n"
    )
    if clock is not None:
        clk = (
            f"create_clock -name {clock.name} -period {period} "
            f"[get_ports {clock.name}]\n"
        )
    else:
        # No clock: time input->output paths against a virtual clock.
        clk = (
            f"create_clock -name vclk -period {period}\n"
            "set_input_delay 0 -clock vclk [all_inputs]\n"
            "set_output_delay 0 -clock vclk [all_outputs]\n"
        )
    return head + clk + (
        "report_checks -path_delay max -digits 4\n"
        'puts "WORST_SLACK [worst_slack -max]"\n'
    )


def _parse_stat(text: str) -> tuple[float | None, int | None]:
    area_m = re.search(r"Chip area for module.*?:\s*([\d.]+)", text)
    cells_m = re.search(r"(\d+)\s+[\d.]+\s+cells", text)
    area = float(area_m.group(1)) if area_m else None
    cells = int(cells_m.group(1)) if cells_m else None
    return area, cells


# A path stage line: "<delay>  <time>  <edge> <inst>/<pin> (<CELLTYPE_X#>)".
_STAGE = re.compile(
    r"^\s*([\d.]+)\s+([\d.]+)\s+[v^]\s+(\S+)\s+\(([A-Za-z][\w]*_X\d+)\)\s*$",
    re.MULTILINE,
)


def _parse_path(text: str) -> list[PathStage]:
    """Gate-by-gate critical path with per-stage delays. A single cell can span two
    report lines (a flop's CK then Q); merge consecutive lines from the same
    instance so each gate appears once with its combined delay."""
    merged: list[list] = []  # [delay, time, inst, cell]
    for delay, time, instpin, cell in _STAGE.findall(text):
        inst = instpin.split("/")[0]
        d, t = float(delay), float(time)
        if merged and merged[-1][2] == inst:
            merged[-1][0] = round(merged[-1][0] + d, 4)
            merged[-1][1] = round(t, 4)
        else:
            merged.append([round(d, 4), round(t, 4), inst, cell])
    return [
        PathStage(cell=cell, delay_ns=d, time_ns=t, instance=inst)
        for d, t, inst, cell in merged
    ]


def _parse_sta(
    text: str, period: float, clocked: bool, area: float | None, cells: int | None
) -> TimingResult:
    slack_m = re.search(r"WORST_SLACK\s+(-?[\d.]+)", text)
    arrival_m = re.search(r"([\d.]+)\s+data arrival time", text)
    start_m = re.search(r"Startpoint:\s+(\S+)", text)
    end_m = re.search(r"Endpoint:\s+(\S+)", text)
    path = _parse_path(text)

    if slack_m is None:
        return TimingResult(
            clocked=clocked, area_um2=area, cell_count=cells,
            source="yosys-estimate", error="OpenSTA reported no timing paths",
        )
    slack = float(slack_m.group(1))
    min_period = period - slack  # fastest achievable period (ns)

    max_freq = None
    critical_ns = float(arrival_m.group(1)) if arrival_m else None
    if clocked and min_period > 0:
        max_freq = round(1000.0 / min_period, 1)
        critical_ns = round(min_period, 4)

    return TimingResult(
        clocked=clocked,
        max_frequency_mhz=max_freq,
        critical_path_ns=critical_ns,
        start_point=start_m.group(1) if start_m else None,
        end_point=end_m.group(1) if end_m else None,
        critical_path=path,
        area_um2=area,
        cell_count=cells,
        source="opensta",
    )
