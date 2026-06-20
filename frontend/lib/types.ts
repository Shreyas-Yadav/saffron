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

export interface SchematicResult {
  svg: string | null;
  renderer: string | null;
  netlist_json: string | null;
  error: string | null;
  logs: string;
  wavedrom: WaveDrom | null;
  sim_error: string | null;
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
}
