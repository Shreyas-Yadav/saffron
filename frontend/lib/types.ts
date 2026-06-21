// Mirrors the backend Pydantic contracts (app/models.py). Single source of the
// shapes that cross the network boundary.

// A WaveDrom timing diagram: one entry per signal.
export interface WaveDromSignal {
  name: string;
  wave: string;
  data?: string[];
}
export interface WaveDrom {
  signal: WaveDromSignal[];
}

// One rule the formal checker tried to prove (intent = from the LLM; invariant =
// well-formedness, true of any sane circuit).
export interface FormalCheck {
  name: string;
  kind: "intent" | "invariant";
  status: "passed" | "failed" | "skipped" | "error";
  detail: string;
}
export interface FormalResult {
  status: "proven" | "refuted" | "skipped" | "error";
  bounded: boolean;
  cycles: number | null;
  checks: FormalCheck[];
  counterexample: WaveDrom | null;
  logs: string;
}

// One gate on the critical path: cell type, incremental delay, cumulative time (ns).
export interface PathStage {
  cell: string;
  delay_ns: number;
  time_ns: number;
}

// Static timing: how fast the mapped circuit can run. `source` is "opensta" for a
// real STA run, or "yosys-estimate" (area/cells only, no frequency) as a fallback.
export interface TimingResult {
  clocked: boolean;
  max_frequency_mhz: number | null;
  critical_path_ns: number | null;
  start_point: string | null;
  end_point: string | null;
  critical_path: PathStage[];
  area_um2: number | null;
  cell_count: number | null;
  source: "opensta" | "yosys-estimate";
  error: string | null;
  logs: string;
}

export interface SchematicResult {
  svg: string | null;
  renderer: string | null;
  netlist_json: string | null;
  error: string | null;
  logs: string;
  wavedrom: WaveDrom | null;
  sim_error: string | null;
  formal: FormalResult | null;
  timing: TimingResult | null;
}

export interface SynthesizeRequest {
  verilog: string;
  top?: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// Result of generate→synthesize→repair: code AND schematic in one response.
export interface GenerateOutcome {
  top_module: string;
  verilog: string;
  explanation: string;
  svg: string | null;
  renderer: string | null;
  attempts: number;
  error: string | null;
  wavedrom: WaveDrom | null;
  sim_error: string | null;
  formal: FormalResult | null;
  timing: TimingResult | null;
}
