import { useEffect, useId, useRef, useState } from "react";
import type { Candle, RacePoint } from "../lib/api";
import { dateTime, price } from "../lib/format";

const HOUR = 3_600_000;

export type Projection = { pUp: number; noCall?: boolean; call?: "UP" | "DOWN" | null };

/** Hourly price chart. `windowStart` shades the next 4h window; `projection` draws a ±1σ fan tinted by P(up). */
export function PriceChart({ candles, height = 280, onHover, windowStart, windowHours = 4, projection }: {
  candles: Candle[];
  height?: number;
  onHover?: (c: Candle | null) => void;
  windowStart?: number;
  windowHours?: number;
  projection?: Projection | null;
}) {
  const id = useId();
  const box = useRef<SVGSVGElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [width, setWidth] = useState(1000);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // keep the same outer <div> so the ResizeObserver target survives
  if (candles.length < 2) return <div ref={wrap}><div className="animate-pulse rounded-3xl bg-mist" style={{ height }} /></div>;

  const narrow = width < 560;
  const pad = { l: 0, r: narrow ? 58 : 72, t: 16, b: 28 };
  const closes = candles.map((c) => c.close);
  const last = closes.at(-1)!;
  const t0 = candles[0].open_time + HOUR;
  const tNow = candles.at(-1)!.open_time + HOUR;
  const tEnd = Math.max(tNow, windowStart ? windowStart + windowHours * HOUR : 0);

  // σ of the last 24 hourly log returns, scaled by √h
  const rets = closes.slice(-25).slice(1).map((c, i) => Math.log(c / closes.slice(-25)[i]));
  const mean = rets.reduce((a, b) => a + b, 0) / Math.max(rets.length, 1);
  const sigma = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(rets.length - 1, 1));
  const fanHours = (tEnd - tNow) / HOUR;
  const band = (h: number) => sigma * Math.sqrt(Math.max(h, 0));
  const fanTop = projection ? last * Math.exp(band(fanHours)) : -Infinity;
  const fanBottom = projection ? last * Math.exp(-band(fanHours)) : Infinity;

  const lo = Math.min(...candles.map((c) => c.low), fanBottom);
  const hi = Math.max(...candles.map((c) => c.high), fanTop);
  const span = hi - lo || hi * 0.01;
  // fixed width for the future zone so it stays readable on long ranges
  const plotW = width - pad.l - pad.r;
  const split = tEnd > tNow ? plotW * (narrow ? 0.7 : 0.8) : plotW;
  const x = (t: number) => pad.l + (t <= tNow
    ? (split * (t - t0)) / (tNow - t0)
    : split + ((plotW - split) * (t - tNow)) / (tEnd - tNow));
  const y = (v: number) => pad.t + ((hi - v) / span) * (height - pad.t - pad.b);
  const pts = candles.map((c) => [x(c.open_time + HOUR), y(c.close)] as const);
  const line = pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
  const area = `${line} L${pts.at(-1)![0].toFixed(1)},${height - pad.b} L${pts[0][0].toFixed(1)},${height - pad.b} Z`;
  const rising = closes.at(-1)! >= closes[0];
  const color = rising ? "var(--color-up)" : "var(--color-down)";
  const ticks = [hi, (hi + lo) / 2, lo];
  const midnights = candles.filter((c) => new Date(c.open_time + HOUR).getHours() === 0);
  const every = Math.ceil(midnights.length / (narrow ? 3 : 7));
  const days = midnights.filter((_, i) => i % every === 0);
  const active = hover === null ? null : candles[hover];

  const move = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect();
    if (!rect) return;
    const vx = ((clientX - rect.left) / rect.width) * width;
    let best = 0;
    pts.forEach(([px], i) => { if (Math.abs(px - vx) < Math.abs(pts[best][0] - vx)) best = i; });
    setHover(best);
    onHover?.(candles[best]);
  };
  const leave = () => { setHover(null); onHover?.(null); };

  function Fan() {
    const p = projection!;
    const steps = Array.from({ length: 13 }, (_, i) => (i / 12) * fanHours);
    const at = (h: number) => x(tNow + h * HOUR);
    const curve = (sign: 1 | -1) => steps.map((h) => `L${at(h).toFixed(1)},${y(last * Math.exp(sign * band(h))).toFixed(1)}`).join(" ");
    const x0 = at(0), x1 = at(fanHours), yMid = y(last);
    const upper = `M${x0},${yMid} ${curve(1)} L${x1},${yMid} Z`;
    const lower = `M${x0},${yMid} ${curve(-1)} L${x1},${yMid} Z`;
    const neutral = p.noCall;
    const upOpacity = neutral ? 0.1 : 0.06 + 0.42 * p.pUp;
    const downOpacity = neutral ? 0.1 : 0.06 + 0.42 * (1 - p.pUp);
    const labelX = x1 - 6;
    return (
      <g>
        <path d={upper} fill={neutral ? "var(--color-faint)" : "var(--color-up)"} fillOpacity={upOpacity} />
        <path d={lower} fill={neutral ? "var(--color-faint)" : "var(--color-down)"} fillOpacity={downOpacity} />
        <line x1={x0} x2={x1} y1={yMid} y2={yMid} stroke="var(--color-ink)" strokeOpacity={0.35} strokeDasharray="3 4" />
        {neutral ? (
          <text x={labelX} y={yMid - 8} fontSize={12} textAnchor="end" fill="var(--color-muted)">no call</text>
        ) : (
          <>
            <text x={labelX} y={y(fanTop) + 16} fontSize={13} fontWeight={600} textAnchor="end" fill="var(--color-up)" className="tabular">
              ↑ {Math.round(p.pUp * 100)}%
            </text>
            <text x={labelX} y={y(fanBottom) - 8} fontSize={13} fontWeight={600} textAnchor="end" fill="var(--color-down)" className="tabular">
              ↓ {100 - Math.round(p.pUp * 100)}%
            </text>
          </>
        )}
        {p.call && (
          <g transform={`translate(${x1},${yMid})`}>
            <circle r={11} fill="var(--color-ink)" />
            <path d={p.call === "UP" ? "M0,5V-5M-4,-1L0,-5L4,-1" : "M0,-5V5M-4,1L0,5L4,1"} fill="none" stroke="#fff"
              strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
          </g>
        )}
      </g>
    );
  }

  return (
    <div ref={wrap}>
    <svg ref={box} viewBox={`0 0 ${width} ${height}`} width="100%" height={height} className="touch-none select-none overflow-visible"
      onPointerMove={(e) => move(e.clientX)} onPointerDown={(e) => move(e.clientX)} onPointerLeave={leave}
      role="img" aria-label={`Hourly price, ${price(closes[0])} to ${price(closes.at(-1)!)}`}>
      <defs>
        <linearGradient id={`fill${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.16} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={0} x2={width - pad.r} y1={y(v)} y2={y(v)} stroke="var(--color-hair)" strokeDasharray="2 4" />
          <text x={width - pad.r + 8} y={y(v) + 4} fontSize={12} fill="var(--color-muted)" className="tabular">${price(v)}</text>
        </g>
      ))}
      {days.map((c) => (
        <text key={c.open_time} x={x(c.open_time + HOUR)} y={height - 8} fontSize={12} fill="var(--color-faint)" textAnchor="middle">
          {new Date(c.open_time + HOUR).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
        </text>
      ))}
      {windowStart && (
        <g>
          <rect x={x(windowStart)} y={pad.t} width={x(windowStart + windowHours * HOUR) - x(windowStart)} height={height - pad.t - pad.b}
            fill="var(--color-recall)" fillOpacity={0.07} rx={6} />
          <text x={(x(windowStart) + x(windowStart + windowHours * HOUR)) / 2} y={pad.t + 14} fontSize={11} textAnchor="middle"
            fill="var(--color-recall)">{narrow ? "" : "next "}{windowHours}h</text>
        </g>
      )}
      {projection && fanHours > 0 && <g className="fade-in" style={{ animationDelay: "0.9s" }}><Fan /></g>}
      <path key={`a${candles.length}-${candles[0].open_time}`} className="fade-in" d={area} fill={`url(#fill${id})`} />
      <path key={`l${candles.length}-${candles[0].open_time}`} className="draw" pathLength={1} d={line} fill="none" stroke={color}
        strokeWidth={2} strokeLinejoin="round" />
      {active ? (
        <g>
          <line x1={pts[hover!][0]} x2={pts[hover!][0]} y1={pad.t} y2={height - pad.b} stroke="var(--color-ink)" strokeOpacity={0.25} />
          <circle cx={pts[hover!][0]} cy={pts[hover!][1]} r={5} fill="#fff" stroke={color} strokeWidth={2} />
        </g>
      ) : (
        <circle cx={pts.at(-1)![0]} cy={pts.at(-1)![1]} r={4.5} fill={color}>
          <animate attributeName="r" values="4.5;7;4.5" dur="2s" repeatCount="indefinite" />
        </circle>
      )}
    </svg>
    </div>
  );
}

export function Sparkline({ values, width = 240, height = 56, stroke = "var(--color-ink)" }: {
  values: number[]; width?: number; height?: number; stroke?: string;
}) {
  if (values.length < 2) return <div style={{ height }} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * width, height - 4 - ((v - min) / span) * (height - 8)]);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lx, ly] = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="none" aria-hidden>
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      <circle cx={lx} cy={ly} r={3} fill={stroke} />
    </svg>
  );
}

export function RaceChart({ series, height = 260 }: { series: RacePoint[]; height?: number }) {
  const width = 720;
  const pad = { l: 44, r: 16, t: 16, b: 28 };
  if (series.length < 2) {
    return (
      <div className="flex items-center justify-center rounded-3xl bg-mist text-center text-muted" style={{ height }}>
        <p className="max-w-sm px-6 text-[15px] leading-relaxed">
          The chart starts once there are at least two resolved forecasts to compare. A new one resolves every hour.
        </p>
      </div>
    );
  }
  const ys = series.flatMap((p) => [p.amnesiac, p.recall]).concat(0.25);
  const lo = Math.min(...ys) - 0.005;
  const hi = Math.max(...ys) + 0.005;
  const x = (i: number) => pad.l + (i / (series.length - 1)) * (width - pad.l - pad.r);
  const y = (v: number) => pad.t + ((hi - v) / (hi - lo)) * (height - pad.t - pad.b);
  const line = (key: "amnesiac" | "recall") => series.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const yTicks = [lo + 0.005, 0.25, hi - 0.005].filter((v, i, a) => a.indexOf(v) === i);
  const last = series[series.length - 1];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Cumulative Brier score, Amnesiac versus Recall">
      {yTicks.map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={width - pad.r} y1={y(v)} y2={y(v)} stroke="var(--color-hair)" strokeDasharray={v === 0.25 ? "4 4" : undefined} />
          <text x={pad.l - 8} y={y(v) + 4} fontSize={11} textAnchor="end" fill="var(--color-muted)" className="tabular">{v.toFixed(3)}</text>
        </g>
      ))}
      <text x={width - pad.r} y={y(0.25) - 6} fontSize={11} textAnchor="end" fill="var(--color-muted)">coin flip</text>
      <path d={line("amnesiac")} fill="none" stroke="var(--color-amnesiac)" strokeWidth={2} />
      <path d={line("recall")} fill="none" stroke="var(--color-recall)" strokeWidth={2.5} />
      <circle cx={x(series.length - 1)} cy={y(last.recall)} r={4} fill="var(--color-recall)" />
      <circle cx={x(series.length - 1)} cy={y(last.amnesiac)} r={3.5} fill="var(--color-amnesiac)" />
      <text x={pad.l} y={height - 8} fontSize={11} fill="var(--color-muted)">{dateTime(series[0].t)}</text>
      <text x={width - pad.r} y={height - 8} fontSize={11} textAnchor="end" fill="var(--color-muted)">{dateTime(last.t)}</text>
    </svg>
  );
}
