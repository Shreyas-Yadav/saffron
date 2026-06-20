// Pure presentational waveform renderer, textbook style: every signal is a binary
// 0/1 square wave (buses arrive pre-expanded into per-bit signals from the backend),
// with dashed vertical gridlines marking each time step.
import type { WaveDrom } from "@/lib/types";

interface Props {
  wavedrom: WaveDrom | null;
  simError: string | null;
  loading: boolean;
}

const U = 40; // px per time unit
const ROW = 40; // px per signal row
const LABEL = 88; // px reserved for signal names
const PAD = 18;
const HI = 8; // y offset of logic-high within a row
const LO = ROW - 12; // y offset of logic-low

export function WaveformPanel({ wavedrom, simError, loading }: Props) {
  if (loading) return <Centered>Simulating…</Centered>;
  if (simError)
    return (
      <Centered>
        <span className="text-neutral-300">No waveform</span>
        <p className="mt-1 max-w-md text-xs text-neutral-500">{simError}</p>
      </Centered>
    );
  if (!wavedrom || wavedrom.signal.length === 0)
    return <Centered>Waveform will appear here after generating.</Centered>;

  const steps = Math.max(...wavedrom.signal.map((s) => s.wave.length));
  const rowsH = wavedrom.signal.length * ROW;
  const width = LABEL + steps * U + PAD;
  const height = PAD * 2 + rowsH;

  return (
    <div className="h-full w-full overflow-auto bg-neutral-950 p-4">
      <svg width={width} height={height} className="font-mono">
        {/* dashed vertical gridlines at each time-step boundary */}
        {Array.from({ length: steps + 1 }, (_, k) => (
          <line
            key={k}
            x1={LABEL + k * U}
            x2={LABEL + k * U}
            y1={PAD}
            y2={PAD + rowsH}
            className="stroke-neutral-700"
            strokeWidth={1}
            strokeDasharray="3 4"
          />
        ))}
        {wavedrom.signal.map((sig, i) => (
          <SignalRow key={sig.name + i} sig={sig} y={PAD + i * ROW} steps={steps} />
        ))}
      </svg>
    </div>
  );
}

function SignalRow({
  sig,
  y,
  steps,
}: {
  sig: { name: string; wave: string };
  y: number;
  steps: number;
}) {
  // Resolve '.' (hold) into the token carried from the previous cell.
  const tokens: string[] = [];
  let prev = "0";
  for (let k = 0; k < steps; k++) {
    const c = sig.wave[k] ?? ".";
    tokens.push(c === "." ? prev : c);
    if (c !== ".") prev = c;
  }

  const yOf = (t: string) =>
    t === "1" ? y + HI : t === "0" ? y + LO : y + (HI + LO) / 2;
  let d = "";
  let prevY = yOf(tokens[0]);
  for (let k = 0; k < tokens.length; k++) {
    const x0 = LABEL + k * U;
    const x1 = x0 + U;
    const yk = yOf(tokens[k]);
    if (k === 0) d += `M ${x0} ${yk} `;
    else if (yk !== prevY) d += `V ${yk} `;
    d += `H ${x1} `;
    prevY = yk;
  }

  return (
    <g>
      <text
        x={0}
        y={y + (HI + LO) / 2 + 4}
        className="fill-neutral-300 text-[12px]"
      >
        {sig.name}
      </text>
      <path d={d} className="fill-none stroke-amber-400" strokeWidth={2} />
    </g>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center p-6 text-center text-sm text-neutral-400">
      {children}
    </div>
  );
}
