// Pure presentational: render a netlistsvg schematic with fit-to-view, scroll/pinch
// zoom, and drag-to-pan, so large circuits (a full ALU) are viewable whole or in
// detail. No fetch logic or app state — fed entirely by props.
"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { SchematicResult } from "@/lib/types";

interface Props {
  result: SchematicResult | null;
  loading: boolean;
}

interface View {
  scale: number;
  x: number;
  y: number;
}

const MIN = 0.05;
const MAX = 12;

// Critical-path endpoints (e.g. "op[2]") map to a schematic port label by their base
// name ("op"). Netlist-internal names (registers like "_103_") aren't drawn, so skip.
function portBase(point: string | null | undefined): string | null {
  if (!point || point.startsWith("_")) return null;
  return point.replace(/\[.*$/, "");
}

export function SchematicPanel({ result, loading }: Props) {
  if (loading) return <Centered>Synthesizing circuit…</Centered>;
  if (!result) return <Centered>Schematic will appear here.</Centered>;
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

  const t = result.timing;
  const startBase = portBase(t?.start_point);
  const endBase = portBase(t?.end_point);
  const highlights = [...new Set([startBase, endBase].filter(Boolean) as string[])];
  const caption =
    highlights.length && t?.start_point && t?.end_point
      ? `${t.start_point} → ${t.end_point}`
      : null;

  return <ZoomableSvg svg={result.svg ?? ""} highlights={highlights} caption={caption} />;
}

const HILITE = "#ea580c"; // orange-600 — the "hot" critical path

// A pan/zoom/fit viewer for an SVG string. Reused by the Timing tab for the
// critical-path schematic. `highlights`/`caption` are optional emphasis.
export function ZoomableSvg({
  svg,
  highlights = [],
  caption = null,
}: {
  svg: string;
  highlights?: string[];
  caption?: string | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>({ scale: 1, x: 0, y: 0 });
  const drag = useRef<{ px: number; py: number; x: number; y: number } | null>(null);

  // Scale the whole circuit to fit the panel (with a small margin) and center it.
  const fit = useCallback(() => {
    const c = container.current;
    const el = content.current?.querySelector("svg");
    if (!c || !el) return;
    const w = el.viewBox?.baseVal?.width || el.width?.baseVal?.value || el.clientWidth;
    const h = el.viewBox?.baseVal?.height || el.height?.baseVal?.value || el.clientHeight;
    if (!w || !h) return;
    const scale = Math.min(c.clientWidth / w, c.clientHeight / h) * 0.92;
    setView({
      scale,
      x: (c.clientWidth - w * scale) / 2,
      y: (c.clientHeight - h * scale) / 2,
    });
  }, []);

  // Highlight the critical-path endpoint labels by baking a CSS rule INTO the SVG
  // string before injection. netlistsvg tags each port label `<text>` with a
  // `cell_<portname>` class, so recoloring is just a stylesheet rule. Doing it in
  // the markup (not by mutating the DOM afterward) means React owns the result and
  // can't reconcile the marks away.
  const hkey = highlights.join("|");
  const markedSvg = useMemo(() => injectHighlight(svg, hkey), [svg, hkey]);

  // Fit on new schematic / resize, on the next frame (after layout).
  useLayoutEffect(() => {
    const r = requestAnimationFrame(fit);
    return () => cancelAnimationFrame(r);
  }, [markedSvg, fit]);
  useEffect(() => {
    const ro = new ResizeObserver(fit);
    if (container.current) ro.observe(container.current);
    return () => ro.disconnect();
  }, [fit]);

  const zoomAround = useCallback((factor: number, cx: number, cy: number) => {
    setView((v) => {
      const scale = clamp(v.scale * factor, MIN, MAX);
      const k = scale / v.scale;
      return { scale, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k };
    });
  }, []);

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const r = container.current!.getBoundingClientRect();
    zoomAround(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX - r.left, e.clientY - r.top);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture(e.pointerId);
    drag.current = { px: e.clientX, py: e.clientY, x: view.x, y: view.y };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    setView((v) => ({
      ...v,
      x: drag.current!.x + (e.clientX - drag.current!.px),
      y: drag.current!.y + (e.clientY - drag.current!.py),
    }));
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  const button = (cx = 0, cy = 0) => {
    const c = container.current;
    return { cx: cx || (c ? c.clientWidth / 2 : 0), cy: cy || (c ? c.clientHeight / 2 : 0) };
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-white">
      {caption && (
        <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-md bg-white/90 px-2.5 py-1 text-xs text-neutral-700 shadow ring-1 ring-neutral-200">
          <span style={{ color: HILITE }}>●</span> Critical path:{" "}
          <span className="font-mono font-medium">{caption}</span>
        </div>
      )}
      <div
        ref={container}
        className="h-full w-full cursor-grab touch-none active:cursor-grabbing"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        <div
          ref={content}
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
            transformOrigin: "0 0",
            width: "max-content",
          }}
          dangerouslySetInnerHTML={{ __html: markedSvg }}
        />
      </div>

      {/* zoom controls */}
      <div className="absolute bottom-3 right-3 flex flex-col overflow-hidden rounded-md border border-neutral-300 bg-white text-neutral-700 shadow">
        <Ctrl onClick={() => { const b = button(); zoomAround(1.25, b.cx, b.cy); }} label="+" />
        <Ctrl onClick={() => { const b = button(); zoomAround(1 / 1.25, b.cx, b.cy); }} label="−" />
        <Ctrl onClick={fit} label="Fit" small />
      </div>
    </div>
  );
}

function Ctrl({
  onClick,
  label,
  small,
}: {
  onClick: () => void;
  label: string;
  small?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`border-b border-neutral-200 px-3 py-1.5 last:border-b-0 hover:bg-neutral-100 ${
        small ? "text-xs" : "text-base leading-none"
      }`}
    >
      {label}
    </button>
  );
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

// Bake a highlight rule into the SVG markup. netlistsvg gives each port label a
// `cell_<portname>` class, so recoloring the endpoints is one injected <style> rule
// (inserted just after the opening <svg> tag). `!important` beats netlistsvg's own
// `text { fill:#000 }`.
function injectHighlight(svg: string, hkey: string): string {
  const names = hkey ? hkey.split("|") : [];
  if (!names.length) return svg;
  const selector = names.map((n) => `.cell_${n.replace(/[^\w-]/g, "")}`).join(",");
  const style = `<style>${selector}{fill:${HILITE}!important;font-weight:bold;}</style>`;
  return svg.replace(/(<svg\b[^>]*>)/, `$1${style}`);
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-white p-6 text-center text-sm text-neutral-500">
      {children}
    </div>
  );
}
