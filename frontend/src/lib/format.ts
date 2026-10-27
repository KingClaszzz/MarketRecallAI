export const pct = (p: number, digits = 0) => `${(p * 100).toFixed(digits)}%`;

export const shortAddress = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`;

export const shortBlob = (b: string) => `${b.slice(0, 6)}…${b.slice(-4)}`;

export function price(x: number) {
  if (x >= 100) return x.toFixed(2);
  if (x >= 1) return x.toFixed(4);
  return x.toFixed(5);
}

/** Backend datetimes are UTC without an offset (SQLite drops it). */
export function utcMs(iso: string) {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z").getTime();
}

export function hourLabel(ms: number) {
  return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function dateTime(ms: number) {
  return new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function countdown(toMs: number, now = Date.now()) {
  const s = Math.max(0, Math.floor((toMs - now) / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function regimeSentence(r: { vol: string; trend: string; chain: string }) {
  const vol = { low: "calm", normal: "steady", high: "volatile" }[r.vol] ?? r.vol;
  const trend = { up: "rising", down: "falling", sideways: "sideways" }[r.trend] ?? r.trend;
  const chain = { quiet: "a quiet", normal: "a normal", busy: "a busy", unknown: "an unmeasured" }[r.chain] ?? r.chain;
  return `${vol}, ${trend} market on ${chain} Sui network`;
}

export const ACTION_LABEL: Record<string, string> = {
  BASELINE: "Unchanged by memory",
  ADJUSTED: "Adjusted by memory",
  NO_CALL: "No call",
};
