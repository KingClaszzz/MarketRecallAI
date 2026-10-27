/** Gauge from 0% (DOWN) to 100% (UP), with Amnesiac (grey) and Recall (blue) needles. */
type Props = { amnesiac: number; recall: number; noCall?: boolean; size?: number };

const START = -180; // degrees
const polar = (cx: number, cy: number, r: number, deg: number) => {
  const rad = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
};

export function ProbabilityDial({ amnesiac, recall, noCall = false, size = 360 }: Props) {
  const w = size;
  const top = 26;
  const r = w / 2 - 24;
  const cx = w / 2;
  const cy = top + r + 6;
  const h = cy + 30;
  const angle = (p: number) => START + p * 180;

  const ticks = Array.from({ length: 21 }, (_, i) => i / 20);
  const [ax, ay] = polar(cx, cy, r, START);
  const [bx, by] = polar(cx, cy, r, 0);
  const [rx0, ry0] = polar(cx, cy, r, angle(Math.min(amnesiac, recall)));
  const [rx1, ry1] = polar(cx, cy, r, angle(Math.max(amnesiac, recall)));
  const gapLarge = Math.abs(recall - amnesiac) > 0.5 ? 1 : 0;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img"
      aria-label={`Amnesiac ${Math.round(amnesiac * 100)}% up, Recall ${noCall ? "no call" : `${Math.round(recall * 100)}% up`}`}>
      <path d={`M ${ax} ${ay} A ${r} ${r} 0 0 1 ${bx} ${by}`} fill="none" stroke="var(--color-hair)" strokeWidth={10} strokeLinecap="round" />
      {/* the shift memory applied */}
      <path d={`M ${rx0} ${ry0} A ${r} ${r} 0 ${gapLarge} 1 ${rx1} ${ry1}`} fill="none"
        stroke="var(--color-recall)" strokeOpacity={0.22} strokeWidth={10} strokeLinecap="round" />
      {ticks.map((p) => {
        const major = p === 0 || p === 0.5 || p === 1;
        const [x0, y0] = polar(cx, cy, r - 16, angle(p));
        const [x1, y1] = polar(cx, cy, r - (major ? 30 : 22), angle(p));
        return <line key={p} x1={x0} y1={y0} x2={x1} y2={y1} stroke={major ? "var(--color-ink-2)" : "var(--color-faint)"} strokeWidth={major ? 1.5 : 1} />;
      })}
      <text x={cx - r} y={cy + 26} fontSize={12} fill="var(--color-muted)" textAnchor="middle">Down</text>
      <text x={cx + r} y={cy + 26} fontSize={12} fill="var(--color-muted)" textAnchor="middle">Up</text>
      <text x={cx} y={top - 8} fontSize={11} fill="var(--color-faint)" textAnchor="middle">50%</text>

      <Needle cx={cx} cy={cy} length={r - 34} deg={angle(amnesiac)} color="var(--color-amnesiac)" width={2} />
      {!noCall && <Needle cx={cx} cy={cy} length={r - 6} deg={angle(recall)} color="var(--color-recall)" width={4} />}
      <circle cx={cx} cy={cy} r={9} fill="var(--color-ink)" />
      <circle cx={cx} cy={cy} r={3.5} fill="#fff" />
    </svg>
  );
}

function Needle({ cx, cy, length, deg, color, width }: { cx: number; cy: number; length: number; deg: number; color: string; width: number }) {
  return (
    <g style={{ transform: `rotate(${deg}deg)`, transformOrigin: `${cx}px ${cy}px`, transition: "transform 1.1s var(--ease-out-soft)" }}>
      <line x1={cx} y1={cy} x2={cx + length} y2={cy} stroke={color} strokeWidth={width} strokeLinecap="round" />
    </g>
  );
}
