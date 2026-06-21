// Pure presentational static-timing report. Headline is max clock frequency for a
// clocked design (or propagation delay for combinational), plus the critical-path
// cell chain and area. Falls back to an area-only readout when OpenSTA is offline.
import { ZoomableSvg } from "@/components/SchematicPanel";
import type { PathStage, TimingResult } from "@/lib/types";

interface Props {
  timing: TimingResult | null;
  loading: boolean;
}

export function TimingPanel({ timing, loading }: Props) {
  if (loading) return <Centered>Analyzing timing…</Centered>;
  if (!timing)
    return <Centered>Timing will appear here after generating.</Centered>;

  const estimate = timing.source === "yosys-estimate";

  return (
    <div className="h-full w-full overflow-auto bg-neutral-950 p-5">
      {/* Headline metric */}
      {timing.clocked && timing.max_frequency_mhz != null ? (
        <Headline value={formatFreq(timing.max_frequency_mhz)} label="max clock frequency" />
      ) : timing.critical_path_ns != null ? (
        <Headline
          value={`${timing.critical_path_ns} ns`}
          label="combinational propagation delay"
        />
      ) : (
        <Headline value="—" label={estimate ? "timing unavailable" : "no timing paths"} />
      )}

      {/* Secondary metrics */}
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {timing.clocked && timing.critical_path_ns != null && (
          <Metric label="min clock period" value={`${timing.critical_path_ns} ns`} />
        )}
        {timing.area_um2 != null && (
          <Metric label="cell area" value={`${timing.area_um2.toFixed(1)} µm²`} />
        )}
        {timing.cell_count != null && (
          <Metric label="standard cells" value={`${timing.cell_count}`} />
        )}
      </div>

      {/* Critical path: gate-by-gate delay waterfall from start pin to end pin */}
      {timing.critical_path.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-1 text-sm font-medium text-neutral-200">
            Critical path ({timing.critical_path.length} gates)
          </h3>
          {timing.start_point && timing.end_point && (
            <p className="mb-3 font-mono text-xs text-neutral-400">
              <span className="text-amber-300">{timing.start_point}</span>
              <span className="text-neutral-600"> → … → </span>
              <span className="text-amber-300">{timing.end_point}</span>
              <span className="text-neutral-600"> (slowest path)</span>
            </p>
          )}
          <CriticalPath stages={timing.critical_path} />
        </div>
      )}

      {/* Faithful schematic of just the path: every gate AND wire shown is on the
          critical path (rendered from the timed netlist). */}
      {timing.critical_path_svg && (
        <div className="mt-6">
          <h3 className="mb-1 text-sm font-medium text-neutral-200">
            Critical path schematic
          </h3>
          <p className="mb-2 text-xs text-neutral-500">
            The mapped (timed) gates and wiring on the slowest path — drag to pan,
            scroll to zoom.
          </p>
          <div className="h-96 rounded-md border border-neutral-800 bg-white">
            <ZoomableSvg svg={timing.critical_path_svg} />
          </div>
        </div>
      )}

      <p className="mt-6 text-xs text-neutral-500">
        {estimate
          ? `Area estimate from yosys (Nangate45). ${
              timing.error ? `OpenSTA not run: ${timing.error}` : ""
            }`
          : "Mapped to the Nangate45 standard-cell library and timed with OpenSTA."}
      </p>
    </div>
  );
}

function CriticalPath({ stages }: { stages: PathStage[] }) {
  const maxDelay = Math.max(...stages.map((s) => s.delay_ns), 1e-9);
  return (
    <div className="flex flex-wrap items-stretch gap-1.5">
      {stages.map((s, i) => (
        <div key={i} className="flex items-stretch gap-1.5">
          {i > 0 && <div className="self-center text-neutral-600">→</div>}
          <div className="flex w-24 flex-col rounded-md border border-neutral-800 bg-neutral-900/60 p-2">
            <span className="truncate font-mono text-xs text-amber-200" title={s.cell}>
              {s.cell}
            </span>
            <span className="mt-0.5 font-mono text-[11px] text-neutral-400">
              +{s.delay_ns.toFixed(3)} ns
            </span>
            {/* delay bar — wider = slower gate, so the bottleneck stands out */}
            <div className="mt-1 h-1 rounded bg-neutral-800">
              <div
                className="h-1 rounded bg-amber-400"
                style={{ width: `${(s.delay_ns / maxDelay) * 100}%` }}
              />
            </div>
            <span className="mt-1 font-mono text-[10px] text-neutral-600">
              t={s.time_ns.toFixed(3)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function formatFreq(mhz: number): string {
  return mhz >= 1000 ? `${(mhz / 1000).toFixed(2)} GHz` : `${mhz.toFixed(0)} MHz`;
}

function Headline({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/50 px-5 py-4">
      <div className="font-mono text-3xl text-amber-300">{value}</div>
      <div className="mt-1 text-xs uppercase tracking-wide text-neutral-500">
        {label}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-neutral-900/60 px-3 py-2">
      <div className="font-mono text-lg text-neutral-100">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-neutral-500">
        {label}
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center p-6 text-center text-sm text-neutral-400">
      {children}
    </div>
  );
}
