// Pure presentational static-timing report. Headline is max clock frequency for a
// clocked design (or propagation delay for combinational), plus the critical-path
// cell chain and area. Falls back to an area-only readout when OpenSTA is offline.
import type { TimingResult } from "@/lib/types";

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
    <div className="h-full w-full overflow-auto bg-ink p-5">
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

      {/* Critical path */}
      {timing.critical_path_cells.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-medium text-bone">
            Critical path ({timing.critical_path_cells.length} cells)
          </h3>
          <div className="flex flex-wrap items-center gap-1.5">
            {timing.critical_path_cells.map((c, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-bone-faint">→</span>}
                <span className="rounded bg-ink-2 px-2 py-0.5 font-mono text-xs text-ember">
                  {c}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      <p className="mt-6 text-xs text-bone-faint">
        {estimate
          ? `Area estimate from yosys (Nangate45). ${
              timing.error ? `OpenSTA not run: ${timing.error}` : ""
            }`
          : "Mapped to the Nangate45 standard-cell library and timed with OpenSTA."}
      </p>
    </div>
  );
}

function formatFreq(mhz: number): string {
  return mhz >= 1000 ? `${(mhz / 1000).toFixed(2)} GHz` : `${mhz.toFixed(0)} MHz`;
}

function Headline({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-ink-2 px-5 py-4">
      <div className="font-display text-4xl font-semibold tracking-tight text-saffron">
        {value}
      </div>
      <div className="mt-1 text-xs uppercase tracking-wide text-bone-faint">
        {label}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-hairline bg-ink-2 px-3 py-2">
      <div className="font-mono text-lg text-bone">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-bone-faint">
        {label}
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-ink p-6 text-center text-sm text-bone-dim">
      {children}
    </div>
  );
}
