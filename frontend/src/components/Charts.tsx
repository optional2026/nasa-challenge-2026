// Dependency-free SVG charts (Recharts could not be installed in the build
// environment; see docs/DECISIONS.md D-004). Interactive: hover tooltips and
// click-to-inspect on every observation point.
import { useEffect, useMemo, useRef, useState } from "react";

export interface Pt { t: string; v: number | null; id?: string; quality?: string; label?: string }
export interface Series { name: string; points: Pt[]; color?: string; dashed?: boolean; step?: boolean; axis?: "left" | "right" }
export interface Band { from: number; to: number; label: string; tone?: string }
export interface RefLine { value: number; label: string; tone?: string }
export interface Marker { t: string; end?: string | null; label: string; tone?: string }

function useWidth(): [any, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((entries) => setW(Math.max(260, Math.floor(entries[0].contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function niceTicks(min: number, max: number, n = 5): number[] {
  if (!isFinite(min) || !isFinite(max)) return [];
  if (min === max) { min -= 1; max += 1; }
  const step0 = (max - min) / n;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

function timeTicks(t0: number, t1: number, width: number): { t: number; label: string }[] {
  const span = t1 - t0;
  const target = Math.max(2, Math.floor(width / 110));
  const hour = 3600e3;
  const steps = [hour, 3 * hour, 6 * hour, 12 * hour, 24 * hour, 48 * hour, 7 * 24 * hour, 14 * 24 * hour, 30 * 24 * hour];
  const step = steps.find((s) => span / s <= target) || steps[steps.length - 1];
  const out: { t: number; label: string }[] = [];
  for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
    const d = new Date(t);
    const label = step >= 24 * hour ? d.toISOString().slice(5, 10) : d.toISOString().slice(5, 10) + " " + d.toISOString().slice(11, 16);
    out.push({ t, label: step >= 24 * hour ? label : label.slice(6) === "00:00" ? d.toISOString().slice(5, 10) : d.toISOString().slice(11, 16) });
  }
  return out;
}

// Theme-aware series colours (CSS variables defined per light/dark theme in styles.css). Applied via `style`,
// because SVG presentation attributes do not resolve var().
const PALETTE = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)"];

export function TimeSeriesChart({ series, bands = [], refLines = [], markers = [], unit = "", height = 240, onPointClick,
  domain, xDomain, emptyText = "No measurements in this period", rightUnit }: {
  series: Series[]; bands?: Band[]; refLines?: RefLine[]; markers?: Marker[]; unit?: string; height?: number;
  onPointClick?: (p: Pt, s: Series) => void; domain?: [number, number]; xDomain?: [number, number]; emptyText?: string; rightUnit?: string;
}) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<{ x: number; y: number; p: Pt; s: Series } | null>(null);
  const m = { l: 48, r: rightUnit ? 48 : 14, t: 12, b: 26 };
  const W = width, H = height;
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const all = series.flatMap((s) => s.points.filter((p) => p.v !== null && p.v !== undefined));
  const left = series.filter((s) => s.axis !== "right").flatMap((s) => s.points.filter((p) => p.v !== null));
  const right = series.filter((s) => s.axis === "right").flatMap((s) => s.points.filter((p) => p.v !== null));

  const calc = useMemo(() => {
    if (!all.length) return null;
    const ts = all.map((p) => new Date(p.t).getTime());
    let t0 = xDomain ? xDomain[0] : Math.min(...ts), t1 = xDomain ? xDomain[1] : Math.max(...ts);
    if (t0 === t1) { t0 -= 3600e3; t1 += 3600e3; }
    const vals = left.map((p) => p.v as number).concat(bands.flatMap((b) => [b.from, b.to])).concat(refLines.map((r) => r.value));
    let lo = domain ? domain[0] : Math.min(...vals), hi = domain ? domain[1] : Math.max(...vals);
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
    if (!domain) { lo -= pad; hi += pad; }
    const rv = right.map((p) => p.v as number);
    let rlo = Math.min(...rv), rhi = Math.max(...rv);
    if (rv.length) { const rp = (rhi - rlo) * 0.08 || 1; rlo -= rp; rhi += rp; }
    return { t0, t1, lo, hi, rlo, rhi };
  }, [JSON.stringify(series.map((s) => [s.name, s.points.length, s.points[0]?.t, s.points[s.points.length - 1]?.t, s.points[s.points.length - 1]?.v])),
      JSON.stringify(bands), JSON.stringify(refLines), JSON.stringify(domain), JSON.stringify(xDomain)]);

  if (!calc) return <div ref={ref} className="chart-empty" style={{ height }}>{emptyText}</div>;
  const { t0, t1, lo, hi, rlo, rhi } = calc;
  const x = (t: string | number) => m.l + ((typeof t === "number" ? t : new Date(t).getTime()) - t0) / (t1 - t0) * iw;
  const y = (v: number) => m.t + (1 - (v - lo) / (hi - lo)) * ih;
  const yr = (v: number) => m.t + (1 - (v - rlo) / (rhi - rlo)) * ih;
  const yTicks = niceTicks(lo, hi, Math.max(3, Math.floor(ih / 45)));
  const xTicks = timeTicks(t0, t1, iw);

  const path = (s: Series) => {
    const yy = s.axis === "right" ? yr : y;
    let d = "";
    let prev: Pt | null = null;
    for (const p of s.points) {
      if (p.v === null || p.v === undefined) { prev = null; continue; }
      const gap = prev && (new Date(p.t).getTime() - new Date(prev.t).getTime()) > 36 * 3600e3;
      if (!prev || gap) d += `M${x(p.t).toFixed(1)},${yy(p.v).toFixed(1)}`;
      else if (s.step) d += `H${x(p.t).toFixed(1)}V${yy(p.v).toFixed(1)}`;
      else d += `L${x(p.t).toFixed(1)},${yy(p.v).toFixed(1)}`;
      prev = p;
    }
    return d;
  };

  return (
    <div ref={ref} className="chart" style={{ minHeight: height }}>
      <svg width={W} height={H} role="img" aria-label={`Chart of ${series.map((s) => s.name).join(", ")}`}>
        {bands.map((b, i) => (
          <g key={i}>
            <rect x={m.l} width={iw} y={y(Math.min(Math.max(b.to, lo), hi))} height={Math.max(0, y(Math.max(Math.min(b.from, hi), lo)) - y(Math.min(Math.max(b.to, lo), hi)))}
              className={`band band-${b.tone || "baseline"}`} />
            <text x={m.l + 6} y={y(Math.min(b.to, hi)) + 12} className="band-label">{b.label}</text>
          </g>
        ))}
        {markers.map((mk, i) => {
          const xs = x(Math.max(t0, new Date(mk.t).getTime()));
          const xe = mk.end ? x(Math.min(t1, new Date(mk.end).getTime())) : xs;
          return (
            <g key={i} className={`marker marker-${mk.tone || "info"}`}>
              {xe - xs > 2 ? <rect x={xs} width={xe - xs} y={m.t} height={ih} /> : <line x1={xs} x2={xs} y1={m.t} y2={m.t + ih} />}
              <title>{mk.label}</title>
            </g>
          );
        })}
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={m.l} x2={m.l + iw} y1={y(v)} y2={y(v)} className="grid" />
            <text x={m.l - 8} y={y(v) + 4} textAnchor="end" className="tick">{v}</text>
          </g>
        ))}
        {rightUnit && niceTicks(rlo, rhi, 4).map((v) => (
          <text key={"r" + v} x={m.l + iw + 8} y={yr(v) + 4} className="tick">{v}</text>
        ))}
        {xTicks.map((tk) => (
          <text key={tk.t} x={x(tk.t)} y={H - 8} textAnchor="middle" className="tick">{tk.label}</text>
        ))}
        <text x={8} y={m.t + 4} className="tick unit-label" transform={`rotate(-90 8 ${m.t + 4})`} textAnchor="end">{unit}</text>
        {refLines.map((r, i) => (
          <g key={i} className={`ref ref-${r.tone || "info"}`}>
            <line x1={m.l} x2={m.l + iw} y1={y(r.value)} y2={y(r.value)} />
            <text x={m.l + iw - 4} y={y(r.value) - 5} textAnchor="end">{r.label}</text>
          </g>
        ))}
        {series.map((s, si) => (
          <g key={s.name}>
            <path d={path(s)} fill="none" style={{ stroke: s.color || PALETTE[si % PALETTE.length] }} strokeWidth={1.8}
              strokeDasharray={s.dashed ? "5 4" : undefined} />
            {s.points.length <= 400 && s.points.map((p, i) => p.v === null || p.v === undefined ? null : (
              <circle key={p.id || i} cx={x(p.t)} cy={(s.axis === "right" ? yr : y)(p.v)} r={p.quality && p.quality !== "valid" ? 4 : 2.6}
                className={`pt ${p.quality && p.quality !== "valid" ? "pt-q" : ""}`} style={{ fill: s.color || PALETTE[si % PALETTE.length] }}
                onMouseEnter={() => setHover({ x: x(p.t), y: (s.axis === "right" ? yr : y)(p.v as number), p, s })}
                onMouseLeave={() => setHover(null)}
                onClick={() => onPointClick && onPointClick(p, s)}
                tabIndex={onPointClick ? 0 : -1}
                onKeyDown={(e: any) => { if (e.key === "Enter" && onPointClick) onPointClick(p, s); }}
                aria-label={`${s.name} ${p.v} at ${p.t}`} />
            ))}
          </g>
        ))}
      </svg>
      {hover && (
        <div className="tooltip" style={{ left: Math.min(hover.x + 10, W - 190), top: Math.max(0, hover.y - 54) }}>
          <strong>{hover.s.name}: {hover.p.label ?? hover.p.v} {hover.s.axis === "right" ? rightUnit : unit}</strong>
          <span>{new Date(hover.p.t).toISOString().slice(0, 16).replace("T", " ")} UTC</span>
          {hover.p.quality && hover.p.quality !== "valid" && <span className="warn">Quality: {hover.p.quality}</span>}
          {onPointClick && <span className="hint">Click to inspect</span>}
        </div>
      )}
      {series.length > 1 && (
        <div className="legend">{series.map((s, i) => <span key={s.name}><i style={{ background: s.color || PALETTE[i % PALETTE.length] }} />{s.name}</span>)}</div>
      )}
    </div>
  );
}

export function BarChart({ bars, unit = "", height = 160, refLine, onBarClick }: {
  bars: { label: string; value: number | null; tone?: string; title?: string }[]; unit?: string; height?: number;
  refLine?: RefLine; onBarClick?: (i: number) => void;
}) {
  const [ref, width] = useWidth();
  const m = { l: 40, r: 8, t: 10, b: 22 };
  const iw = width - m.l - m.r, ih = height - m.t - m.b;
  const vals = bars.map((b) => b.value ?? 0).concat(refLine ? [refLine.value] : []);
  const hi = Math.max(1, ...vals) * 1.1;
  const bw = iw / Math.max(1, bars.length);
  const y = (v: number) => m.t + ih - (v / hi) * ih;
  return (
    <div ref={ref} className="chart" style={{ minHeight: height }}>
      <svg width={width} height={height} role="img" aria-label="Bar chart">
        {niceTicks(0, hi, 3).map((v) => (
          <g key={v}><line x1={m.l} x2={m.l + iw} y1={y(v)} y2={y(v)} className="grid" />
            <text x={m.l - 6} y={y(v) + 4} textAnchor="end" className="tick">{v}</text></g>
        ))}
        {bars.map((b, i) => (
          <g key={i} onClick={() => onBarClick && onBarClick(i)} className={onBarClick ? "clickable" : ""}>
            {b.value === null
              ? <rect x={m.l + i * bw + bw * 0.18} width={bw * 0.64} y={m.t + ih - 6} height={6} className="bar bar-missing" />
              : <rect x={m.l + i * bw + bw * 0.18} width={bw * 0.64} y={y(b.value)} height={Math.max(1, m.t + ih - y(b.value))} className={`bar bar-${b.tone || "plain"}`} />}
            <title>{b.title || `${b.label}: ${b.value ?? "no data"} ${unit}`}</title>
            <text x={m.l + i * bw + bw / 2} y={height - 6} textAnchor="middle" className="tick">{b.label}</text>
          </g>
        ))}
        {refLine && (
          <g className={`ref ref-${refLine.tone || "info"}`}>
            <line x1={m.l} x2={m.l + iw} y1={y(refLine.value)} y2={y(refLine.value)} />
            <text x={m.l + iw - 4} y={y(refLine.value) - 4} textAnchor="end">{refLine.label}</text>
          </g>
        )}
      </svg>
    </div>
  );
}

export function Sparkline({ values, tone = "plain", width = 120, height = 30 }: { values: number[]; tone?: string; width?: number; height?: number }) {
  if (values.length < 2) return <svg width={width} height={height} />;
  const lo = Math.min(...values), hi = Math.max(...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * (width - 2) + 1},${height - 2 - ((v - lo) / (hi - lo || 1)) * (height - 4)}`);
  return <svg width={width} height={height} className={`spark spark-${tone}`} aria-hidden><polyline points={pts.join(" ")} fill="none" /></svg>;
}
