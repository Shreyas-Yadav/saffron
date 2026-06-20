// Pure presentational: given a schematic result + loading flag, render it. No fetch
// logic, no app state — fully decoupled and trivially reusable.
import type { SchematicResult } from "@/lib/types";

interface Props {
  result: SchematicResult | null;
  loading: boolean;
}

export function SchematicPanel({ result, loading }: Props) {
  if (loading) {
    return <Centered>Synthesizing circuit…</Centered>;
  }
  if (!result) {
    return <Centered>Schematic will appear here.</Centered>;
  }
  if (result.error) {
    return (
      <Centered>
        <span className="text-red-400">Synthesis error:</span>
        <pre className="mt-2 max-w-full overflow-auto text-xs text-red-300">
          {result.error}
        </pre>
      </Centered>
    );
  }
  return (
    <div className="flex h-full w-full items-center justify-center overflow-auto bg-white p-4">
      {/* netlistsvg returns a trusted, self-generated SVG */}
      <div
        className="[&_svg]:h-auto [&_svg]:max-w-full"
        dangerouslySetInnerHTML={{ __html: result.svg ?? "" }}
      />
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
