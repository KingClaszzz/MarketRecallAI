import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { PriceChart, RaceChart, type Projection } from "../components/Charts";
import { Aurora, Button, Logo, Segmented } from "../components/Chrome";
import { ProbabilityDial } from "../components/ProbabilityDial";
import { SignInDialog } from "../components/SignInDialog";
import { Tour } from "../components/Tour";
import { TOUR_KEY, TOUR_STEPS } from "../lib/tour";
import {
  api, ApiError, ASSET_NAMES, ASSETS,
  type Asset, type Candle, type ChatMessage, type Direction, type Me, type Mode, type Pick, type PredictSession, type SessionView,
} from "../lib/api";
import { ACTION_LABEL, countdown, dateTime, hourLabel, pct, price, regimeSentence, shortAddress, shortBlob, utcMs } from "../lib/format";
import { useSession } from "../lib/session";
import { useFetch } from "../lib/useFetch";

const HOUR = 3_600_000;
const WINDOW_H = 4;

function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

const windowLabel = (t: number) => `${hourLabel(t)}–${hourLabel(t + WINDOW_H * HOUR)}`;
const isOpen = (s: PredictSession, now = Date.now()) => utcMs(s.expires_at) > now && s.messages_used < s.max_messages;
const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export default function Dashboard() {
  const { token, me, loading, signOut, refresh } = useSession();
  const [tourOpen, setTourOpen] = useState(false);
  useEffect(() => {
    if (!me) return;
    try {
      if (!localStorage.getItem(TOUR_KEY)) setTourOpen(true);
    } catch {
      /* storage unavailable */
    }
  }, [me]);
  const closeTour = (finished: boolean) => {
    setTourOpen(false);
    try {
      localStorage.setItem(TOUR_KEY, finished ? "done" : "skipped");
    } catch {
      /* ignore */
    }
  };
  const [asset, setAsset] = useState<Asset>("SUI");
  const [signIn, setSignIn] = useState(false);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [view, setView] = useState<SessionView | null>(null);
  const [reload, setReload] = useState(0);
  const list = useFetch(() => (token ? api.sessions(token) : Promise.resolve([])), [token, reload], 120_000).data ?? [];

  const chooseAsset = (a: Asset) => {
    setAsset(a);
    const latest = list.find((r) => r.session.asset === a && isOpen(r.session));
    setActiveId(latest?.session.id ?? null);
  };
  const firstLoad = useRef(true);
  useEffect(() => {
    if (!firstLoad.current || list.length === 0) return;
    firstLoad.current = false;
    const latest = list.find((r) => r.session.asset === asset && isOpen(r.session));
    if (latest) setActiveId(latest.session.id);
  }, [list, asset]);

  useEffect(() => {
    if (!token || activeId === null) {
      setView(null);
      return;
    }
    let alive = true;
    const load = () => api.session(token, activeId).then((v) => alive && setView(v)).catch(() => alive && setView(null));
    load();
    const id = setInterval(load, 60_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [token, activeId]);

  const onOpened = async (v: SessionView) => {
    setView(v);
    setActiveId(v.session.id);
    setReload((n) => n + 1);
    await refresh();
  };

  if (!token && !loading) {
    return (
      <div className="relative flex min-h-screen flex-col overflow-hidden bg-paper">
        <Aurora />
        <TopBar asset={asset} onAsset={setAsset} me={null} onSignOut={signOut} />
        <div className="flex flex-1 items-center justify-center px-6">
          <div className="surface relative max-w-[460px] rounded-[32px] p-10 text-center">
            <h1 className="text-[30px] font-semibold tracking-[-0.03em]">Sign in to start a session.</h1>
            <p className="mt-3 text-[16px] leading-relaxed text-ink-2">
              You get three credits every week. Each credit opens a session with the model's reading, your own call, and an analyst you can ask about it.
            </p>
            <Button size="lg" className="mt-8" onClick={() => setSignIn(true)}>Sign in</Button>
            <p className="mt-6 text-[13px] text-muted"><Link to="/" className="text-recall hover:underline">Back to the homepage</Link></p>
          </div>
        </div>
        <SignInDialog open={signIn} onClose={() => setSignIn(false)} />
      </div>
    );
  }

  const shown = view && view.session.asset === asset ? view : null;
  return (
    <div className="relative min-h-screen overflow-hidden bg-paper pb-20">
      <Aurora className="h-[720px]" />
      <TopBar asset={asset} onAsset={chooseAsset} me={me} onSignOut={signOut} onTour={() => setTourOpen(true)} />
      <main className="relative mx-auto max-w-[1180px] px-4 pt-8 sm:px-5">
        <PriceHero asset={asset} windowStart={shown?.session.slot_t ?? Math.ceil(Date.now() / HOUR) * HOUR}
          projection={shown?.forecast ? {
            pUp: shown.forecast.recall_p, noCall: shown.forecast.recall_action === "NO_CALL", call: shown.pick?.direction ?? null,
          } : null}
          onNew={shown ? () => setActiveId(null) : undefined} />
        <div className="mt-5">
          {shown ? (
            <Workspace view={shown} token={token!} onChange={async (v) => { setView(v); setReload((n) => n + 1); await refresh(); }} />
          ) : (
            <StartPanel asset={asset} me={me} token={token} onOpened={onOpened} />
          )}
        </div>
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <SessionsCard rows={list} activeId={shown?.session.id ?? null}
            onOpen={(s) => { setAsset(s.asset); setActiveId(s.id); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
          <RecordCard token={token} reload={reload} />
        </div>
        <div className="mt-5 grid gap-5 lg:grid-cols-[1.45fr_1fr]">
          <RaceCard asset={asset} />
          <LedgerCard me={me} />
        </div>
      </main>
      <Tour steps={TOUR_STEPS} open={tourOpen} onClose={closeTour} />
    </div>
  );
}

function TopBar({ asset, onAsset, me, onSignOut, onTour }: {
  asset: Asset; onAsset: (a: Asset) => void; me: Me | null; onSignOut: () => void; onTour?: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-white/60 bg-white/60 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between gap-2 px-3 sm:gap-3 sm:px-5">
        <Logo compact />
        <span data-tour="assets"><Segmented label="Asset" options={ASSETS} value={asset} onChange={onAsset} /></span>
        {me ? (
          <div className="flex items-center gap-1.5 sm:gap-3">
            {onTour && (
              <button onClick={onTour} title="How to use MarketRecall" aria-label="Start the guided tour"
                className="press flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-hair bg-white/70 px-2.5 text-[13px] font-medium text-ink-2 hover:border-recall/40 hover:text-recall">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-current text-[10px] font-bold"><span className="text-white">?</span></span>
                <span className="hidden sm:inline">Tour</span>
              </button>
            )}
            <span key={me.credits} data-tour="credits" className="bubble-in tabular rounded-full bg-recall-soft px-3 py-1 text-[13px] font-semibold text-recall">
              {me.credits}<span className="hidden sm:inline"> credit{me.credits === 1 ? "" : "s"}</span>
            </span>
            <button onClick={onSignOut} title="Sign out" aria-label={`Sign out of ${shortAddress(me.address)}`}
              className="press cursor-pointer rounded-full px-2 py-1 font-mono text-[12px] text-muted hover:bg-white/70 hover:text-ink">
              <span className="hidden sm:inline">{shortAddress(me.address)}</span>
              <svg className="sm:hidden" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
            </button>
          </div>
        ) : <span className="w-10 sm:w-24" />}
      </div>
    </header>
  );
}

function Card({ children, className = "", tour }: { children: React.ReactNode; className?: string; tour?: string }) {
  return <section data-tour={tour} className={`surface rounded-[28px] p-6 sm:p-8 ${className}`}>{children}</section>;
}

function CardTitle({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <h2 className="text-[19px] font-semibold tracking-[-0.02em]">{children}</h2>
      {aside && <div className="text-right text-[13px] text-muted">{aside}</div>}
    </div>
  );
}

const RANGES = [
  { label: "24H", hours: 24 },
  { label: "3D", hours: 72 },
  { label: "7D", hours: 168 },
  { label: "30D", hours: 720 },
];

function PriceHero({ asset, windowStart, projection, onNew }: {
  asset: Asset; windowStart: number; projection: Projection | null; onNew?: () => void;
}) {
  const [range, setRange] = useState(RANGES[1]);
  const [hover, setHover] = useState<Candle | null>(null);
  const candles = useFetch(() => api.candles(asset, range.hours), [asset, range.hours], 300_000).data ?? [];
  const first = candles[0]?.close;
  const last = candles.at(-1);
  const shown = hover ?? last;
  const narrowScreen = typeof window !== "undefined" && window.innerWidth < 640;
  const change = first && shown ? shown.close / first - 1 : 0;

  return (
    <Card tour="chart" className="!pb-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[14px] text-muted">
            <span className="font-medium text-ink">{ASSET_NAMES[asset]}</span>
            <span>{asset} / USD</span>
          </div>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
            <span className="tabular text-[40px] font-semibold tracking-[-0.035em] sm:text-[52px]">
              {shown ? `$${price(shown.close)}` : "—"}
            </span>
            <span className={`tabular text-[16px] font-medium ${change >= 0 ? "text-up" : "text-down"}`}>
              {change >= 0 ? "+" : ""}{(change * 100).toFixed(2)}%
            </span>
            <span className="text-[14px] text-muted">
              {hover ? dateTime(hover.open_time + HOUR) : `past ${range.label.toLowerCase()}`}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Segmented label="Range" size="sm" options={RANGES.map((r) => r.label)} value={range.label}
            onChange={(l) => setRange(RANGES.find((r) => r.label === l)!)} />
          {onNew && <Button variant="light" size="sm" className="!bg-mist" onClick={onNew}>New session</Button>}
        </div>
      </div>
      <div className="mt-6">
        <PriceChart candles={candles} onHover={setHover} windowStart={windowStart} projection={projection}
          height={narrowScreen ? 240 : 320} />
      </div>
      {projection ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-muted">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-up/50" /> chance it closes higher</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-down/50" /> chance it closes lower</span>
          <span>The fan shows the typical 4-hour range based on recent volatility. The model forecasts direction only, not a price target.</span>
        </div>
      ) : (
        <p className="mt-2 text-[12px] text-faint">Hourly closes from Tatum. Run the model to see its forecast for the shaded 4-hour window.</p>
      )}
    </Card>
  );
}

function StartPanel({ asset, me, token, onOpened }: {
  asset: Asset; me: Me | null; token: string | null; onOpened: (v: SessionView) => Promise<void>;
}) {
  const now = useNow(1000);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const slot = Math.ceil(now / HOUR) * HOUR;
  const existing = me?.picks.find((p) => p.asset === asset && p.slot_t === slot);
  const noCredits = (me?.credits ?? 0) < (me?.session_cost ?? 1);

  const open = async (mode: Mode, direction?: Direction) => {
    if (!token) return;
    setBusy(direction ?? mode);
    setError(null);
    try {
      await onOpened(await api.openSession(token, asset, mode, direction));
    } catch (e) {
      setError(errorText(e, "Could not open the session."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card tour="start" className="!p-0 overflow-hidden">
      <div className="px-6 pt-7 sm:px-10 sm:pt-10">
        <p className="eyebrow">New session · {asset}</p>
        <h1 className="mt-2 text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] sm:text-[40px]">
          Higher or lower by {hourLabel(slot + WINDOW_H * HOUR)}?
        </h1>
        <p className="mt-3 max-w-[620px] text-[16px] leading-relaxed text-ink-2">
          Start with your own call or with the model's forecast. Either way you get the full reading and can ask the
          analyst about it.
        </p>
      </div>

      <div className="mt-8 grid gap-4 px-4 sm:px-6 md:grid-cols-2">
        <div data-tour="own" className="lift flex flex-col rounded-[24px] border border-hair/70 bg-white p-6 sm:p-8">
          <div className="text-[13px] font-medium text-muted">Your call first</div>
          <h3 className="mt-2 text-[24px] font-semibold tracking-[-0.02em]">Make your call, then compare.</h3>
          <p className="mt-2 flex-1 text-[15px] leading-relaxed text-ink-2">
            Lock in higher or lower for {windowLabel(slot)}, then see how the model reads the same market and where you differ.
          </p>
          {existing ? (
            <p className="mt-6 rounded-[18px] bg-mist px-5 py-4 text-[14px] text-ink-2">
              You already have a {asset} call for this window. Run the model to open another session.
            </p>
          ) : (
            <div className="mt-6 grid grid-cols-2 gap-3">
              <DirectionButton dir="UP" busy={busy === "UP"} disabled={!!busy || noCredits} onClick={() => open("own", "UP")} />
              <DirectionButton dir="DOWN" busy={busy === "DOWN"} disabled={!!busy || noCredits} onClick={() => open("own", "DOWN")} />
            </div>
          )}
        </div>
        <div data-tour="model" className="lift relative flex flex-col overflow-hidden rounded-[24px] bg-[linear-gradient(140deg,#16181f_0%,#1d2240_60%,#2a2463_100%)] p-6 text-white sm:p-8">
          <span aria-hidden className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-[radial-gradient(circle,rgb(91_140_255/0.45),transparent_65%)] blur-2xl" />
          <div className="text-[13px] font-medium text-[#8fb0ff]">Model first</div>
          <h3 className="mt-2 text-[24px] font-semibold tracking-[-0.02em]">Run the model.</h3>
          <p className="mt-2 flex-1 text-[15px] leading-relaxed text-white/70">
            See its probability, the main inputs behind it, and its record in similar markets. You can lock in a call afterwards.
          </p>
          <button onClick={() => open("model")} disabled={!!busy || noCredits}
            className="press group relative mt-6 flex cursor-pointer items-center justify-center gap-2 rounded-[20px] bg-white py-5 text-[17px] font-semibold text-ink hover:shadow-[0_12px_36px_-10px_rgb(91_140_255/0.7)] disabled:cursor-not-allowed disabled:opacity-50">
            {busy === "model" ? "Running…" : <>Run the model <span className="nudge-x">→</span></>}
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2 px-6 py-6 text-[13px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-10">
        <span>
          {me?.session_cost ?? 1} credit per session · includes one call and {me?.questions_per_session ?? 10} questions ·
          a correct call returns {me?.call_reward ?? 2}
        </span>
        <span className="tabular">Calls for {windowLabel(slot)} lock in {countdown(slot, now)}</span>
      </div>
      {error && <p className="mx-6 mb-6 rounded-xl bg-down-soft px-4 py-3 text-[14px] text-down sm:mx-10">{error}</p>}
      {noCredits && me && (
        <p className="mx-6 mb-6 rounded-xl bg-mist px-4 py-3 text-[14px] text-ink-2 sm:mx-10">
          You're out of credits. Your balance resets to {me.weekly_floor} on Monday, and any open calls can still return credits when they resolve.
        </p>
      )}
    </Card>
  );
}

function DirectionButton({ dir, busy, disabled, onClick }: { dir: Direction; busy: boolean; disabled: boolean; onClick: () => void }) {
  const up = dir === "UP";
  return (
    <button onClick={onClick} disabled={disabled}
      className={`press group flex cursor-pointer items-center justify-center gap-2 rounded-[20px] py-5 text-[18px] font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${
        up ? "bg-up-soft text-up hover:bg-up hover:text-white hover:shadow-[0_12px_28px_-12px_rgb(31_138_76/0.8)]"
           : "bg-down-soft text-down hover:bg-down hover:text-white hover:shadow-[0_12px_28px_-12px_rgb(210_59_47/0.8)]"}`}>
      {busy ? "…" : <><span className={up ? "nudge-up" : "nudge-down"}><Arrow up={up} /></span> {up ? "Higher" : "Lower"}</>}
    </button>
  );
}

const Arrow = ({ up, size = 14 }: { up: boolean; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden style={{ transform: up ? undefined : "rotate(180deg)" }}>
    <path d="M7 12V2M2.5 6.5L7 2l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

function Workspace({ view, token, onChange }: { view: SessionView; token: string; onChange: (v: SessionView) => Promise<void> }) {
  return (
    <div className="grid items-start gap-5 lg:grid-cols-[1.15fr_1fr]">
      <ReadingCard view={view} token={token} onChange={onChange} />
      <ChatCard view={view} token={token} />
    </div>
  );
}

function ReadingCard({ view, token, onChange }: { view: SessionView; token: string; onChange: (v: SessionView) => Promise<void> }) {
  const f = view.forecast;
  const d = f?.trace.decision;
  const cred = d ? d.credibility[d.voice] : undefined;
  const drivers = view.session.context.drivers ?? [];
  const maxWeight = Math.max(...drivers.map((x) => x.weight), 0.01);
  const evidence = [...(f?.trace.evidence?.credibility ?? []), ...(f?.trace.evidence?.episodes ?? [])].slice(0, 4);
  const ctx = view.session.context;
  const noCall = f?.recall_action === "NO_CALL";

  return (
    <Card tour="reading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-mist px-3 py-1 text-[12px] font-medium text-ink-2">
            {view.session.mode === "own" ? "Your call first" : "Model first"}
          </span>
          {f && <span className="rounded-full bg-recall-soft px-3 py-1 text-[12px] font-medium text-recall">{ACTION_LABEL[f.recall_action]}</span>}
        </div>
        <span className="text-[13px] text-muted">{f ? `Reading of ${dateTime(f.t)}` : ""}</span>
      </div>

      <YourCall view={view} token={token} onChange={onChange} />

      <div className="mx-auto mt-6 max-w-[440px]">
        <ProbabilityDial amnesiac={f?.amnesiac_p ?? 0.5} recall={f?.recall_p ?? 0.5} noCall={noCall} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-6">
        <Stat label="Without memory" value={f ? `${pct(f.amnesiac_p)} up` : "—"} />
        <Stat label="Model reading" value={f ? (noCall ? "No call" : `${pct(f.recall_p)} up`) : "—"} accent />
      </div>
      {f?.trace.explanation?.text && <p className="mt-6 text-[16px] leading-[1.6] text-ink">{f.trace.explanation.text}</p>}

      {drivers.length > 0 && (
        <div className="mt-7 border-t border-hair pt-6">
          <div className="text-[13px] font-medium text-ink">Main inputs</div>
          <div className="mt-4 space-y-3">
            {drivers.map((x) => (
              <div key={x.feature} className="grid grid-cols-[1fr_96px] items-center gap-4 sm:grid-cols-[1fr_140px]">
                <span className="text-[14px] text-ink-2">{x.feature[0].toUpperCase() + x.feature.slice(1)}</span>
                <span className="flex items-center gap-2">
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-mist">
                    <span className={`grow-x block h-full rounded-full ${x.pushes === "UP" ? "bg-up" : "bg-down"}`}
                      style={{ width: `${Math.max(8, (x.weight / maxWeight) * 100)}%` }} />
                  </span>
                  <span className={`w-4 ${x.pushes === "UP" ? "text-up" : "text-down"}`}><Arrow up={x.pushes === "UP"} size={12} /></span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {cred && (
        <div className="mt-7 grid grid-cols-3 gap-4 rounded-[22px] bg-mist p-5">
          <Mini label="Similar hours" value={cred.n.toLocaleString()} />
          <Mini label="Model said up" value={pct(cred.avg_p)} />
          <Mini label="Went up" value={pct(cred.freq_up)} />
        </div>
      )}

      <div className="mt-6 flex flex-wrap gap-2">
        {f && <Chip>{regimeSentence(f.regime)}</Chip>}
        {ctx.move_4h_pct != null && <Chip>4h {signed(ctx.move_4h_pct)}</Chip>}
        {ctx.move_24h_pct != null && <Chip>24h {signed(ctx.move_24h_pct)}</Chip>}
        {ctx.volatility_rank_30d_pct != null && <Chip>volatility rank {Math.round(ctx.volatility_rank_30d_pct)}/100</Chip>}
      </div>

      {evidence.length > 0 && (
        <div className="mt-6 border-t border-hair pt-4">
          <div className="text-[12px] text-muted">Memories recalled from Walrus</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {evidence.map((e) => (
              <a key={e.blob_id} href={`https://aggregator.walrus-mainnet.walrus.space/v1/blobs/${encodeURIComponent(e.blob_id)}`} target="_blank" rel="noreferrer"
                title={e.text} className="rounded-full bg-mist px-3 py-1 font-mono text-[11px] text-walrus hover:underline">
                {shortBlob(e.blob_id)}
              </a>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

const signed = (x: number) => `${x >= 0 ? "+" : ""}${x.toFixed(2)}%`;

function YourCall({ view, token, onChange }: { view: SessionView; token: string; onChange: (v: SessionView) => Promise<void> }) {
  const now = useNow(1000);
  const [busy, setBusy] = useState<Direction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const p = view.pick;
  const slot = view.session.slot_t;

  const lock = async (direction: Direction) => {
    setBusy(direction);
    setError(null);
    try {
      await onChange(await api.lockCall(token, view.session.id, direction));
    } catch (e) {
      setError(errorText(e, "Could not lock the call."));
    } finally {
      setBusy(null);
    }
  };

  if (p) return <CallSummary pick={p} />;
  if (!view.can_call) {
    return <p className="mt-5 rounded-[18px] bg-mist px-5 py-4 text-[14px] text-muted">No call was made in this session, and the window has now started.</p>;
  }
  return (
    <div className="mt-5 rounded-[22px] border border-hair p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[15px] font-medium">Your call for {windowLabel(slot)}</span>
        <span className="tabular text-[13px] text-muted">locks in {countdown(slot, now)} · included</span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <DirectionButton dir="UP" busy={busy === "UP"} disabled={!!busy} onClick={() => lock("UP")} />
        <DirectionButton dir="DOWN" busy={busy === "DOWN"} disabled={!!busy} onClick={() => lock("DOWN")} />
      </div>
      {error && <p className="mt-3 text-[14px] text-down">{error}</p>}
    </div>
  );
}

function CallSummary({ pick }: { pick: Pick }) {
  const up = pick.direction === "UP";
  const resolved = pick.status === "WON" || pick.status === "LOST";
  const agree = pick.agrees_with_model;
  return (
    <div className={`mt-5 flex flex-wrap items-center justify-between gap-3 rounded-[22px] px-5 py-4 ${
      pick.status === "WON" ? "bg-up-soft" : pick.status === "LOST" ? "bg-down-soft" : "bg-mist"}`}>
      <div className="flex items-center gap-3">
        <span className={`flex h-9 w-9 items-center justify-center rounded-full bg-white ${up ? "text-up" : "text-down"}`}><Arrow up={up} /></span>
        <div>
          <div className="text-[15px] font-semibold">You called {up ? "higher" : "lower"} for {windowLabel(pick.slot_t)}</div>
          <div className="text-[13px] text-ink-2">
            {agree === null ? "The model had no directional lean." : agree ? "Same direction as the model." : "Opposite to the model's forecast."}
          </div>
        </div>
      </div>
      <span className="tabular text-[13px] font-medium text-ink-2">
        {resolved
          ? `${pick.status === "WON" ? "Correct · +2 credits" : "Incorrect"} · $${price(pick.close_at_t!)} → $${price(pick.close_at_resolve!)}`
          : pick.status === "REFUNDED" ? "Refunded" : `Resolves ${hourLabel(pick.slot_t + WINDOW_H * HOUR)}`}
      </span>
    </div>
  );
}

function Stat({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`border-l-2 pl-4 ${accent ? "border-recall" : "border-amnesiac"}`}>
      <div className={`text-[13px] ${accent ? "text-recall" : "text-muted"}`}>{label}</div>
      <div className={`tabular mt-1 text-[28px] font-semibold tracking-[-0.03em] ${accent ? "" : "text-ink-2"}`}>{value}</div>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[12px] text-muted">{label}</div>
      <div className="tabular mt-0.5 text-[19px] font-semibold tracking-[-0.02em]">{value}</div>
    </div>
  );
}

const Chip = ({ children }: { children: React.ReactNode }) => (
  <span className="rounded-full bg-mist px-3 py-1 text-[12px] text-ink-2">{children}</span>
);

function suggestions(view: SessionView): string[] {
  const p = view.pick;
  const out = [
    "What is driving this forecast?",
    "How reliable has the model been in similar markets?",
    "What would change the forecast?",
    "How have my past calls gone?",
    "How does this compare with the other tokens?",
  ];
  if (p && p.agrees_with_model === false) out.unshift("Why does the model disagree with my call?");
  if (p && (p.status === "WON" || p.status === "LOST")) out.unshift("What happened during my window?");
  return out.slice(0, 5);
}

function ChatCard({ view, token }: { view: SessionView; token: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>(view.messages);
  const [left, setLeft] = useState(view.questions_left);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const ended = !view.active || left <= 0;

  useEffect(() => {
    setMessages(view.messages);
    setLeft(view.questions_left);
  }, [view.session.id, view.messages.length, view.questions_left]);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, busy]);

  const send = async (q: string) => {
    const question = q.trim();
    if (!question || busy || ended) return;
    setBusy(true);
    setError(null);
    setText("");
    const pending: ChatMessage = { id: -Date.now(), ts: new Date().toISOString(), role: "user", text: question, by: null };
    setMessages((m) => [...m, pending]);
    try {
      const out = await api.ask(token, view.session.id, question);
      setMessages((m) => [...m, out.answer]);
      setLeft(out.questions_left);
    } catch (e) {
      setMessages((m) => m.filter((x) => x.id !== pending.id));
      setText(question);
      setError(errorText(e, "The analyst could not answer."));
    } finally {
      setBusy(false);
    }
  };

  const chips = useMemo(() => suggestions(view), [view]);
  const asked = new Set(messages.filter((m) => m.role === "user").map((m) => m.text));

  return (
    <Card tour="chat" className="flex flex-col lg:sticky lg:top-20">
      <CardTitle aside={<span className="tabular">{left} of {view.session.max_messages} questions left</span>}>Ask the analyst</CardTitle>
      <div ref={scroller} className="mt-5 max-h-[460px] min-h-[220px] flex-1 space-y-3 overflow-y-auto pr-1">
        <Bubble role="assistant">
          I have this session's {view.session.asset} forecast, its main inputs, the model's record in similar
          markets{view.pick ? ", your call" : ""} and your history from Walrus. What would you like to know?
        </Bubble>
        {messages.map((m) => <Bubble key={m.id} role={m.role}>{m.text}</Bubble>)}
        {busy && <Bubble role="assistant"><span className="inline-flex gap-1"><Dot /><Dot d={150} /><Dot d={300} /></span></Bubble>}
      </div>

      {!ended && (
        <div className="mt-4 flex flex-wrap gap-2">
          {chips.filter((c) => !asked.has(c)).slice(0, 3).map((c) => (
            <button key={c} onClick={() => send(c)} disabled={busy}
              className="press cursor-pointer rounded-full border border-hair bg-white/70 px-3 py-1.5 text-left text-[13px] text-ink-2 hover:-translate-y-0.5 hover:border-recall/40 hover:bg-recall-soft hover:text-recall disabled:opacity-50">
              {c}
            </button>
          ))}
        </div>
      )}

      {ended ? (
        <p className="mt-5 rounded-[18px] bg-mist px-5 py-4 text-[14px] text-muted">
          This session is closed. Start a new one for a fresh reading.
        </p>
      ) : (
        <form className="mt-4 flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} maxLength={300}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
            placeholder="Ask about this forecast…" aria-label="Your question"
            className="max-h-32 min-h-[48px] flex-1 resize-none rounded-[18px] bg-mist px-4 py-3 text-[15px] outline-none placeholder:text-faint focus:ring-2 focus:ring-recall/30" />
          <button type="submit" disabled={busy || !text.trim()} aria-label="Send"
            className="press glow group flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full bg-recall text-white disabled:cursor-not-allowed disabled:opacity-40">
            <span className="nudge-up"><Arrow up size={16} /></span>
          </button>
        </form>
      )}
      {error && <p className="mt-3 text-[14px] text-down">{error}</p>}
      <p className="mt-4 text-[12px] leading-relaxed text-faint">
        Answers are based only on this session's data, and every number is checked before it is shown. Not financial advice.
      </p>
    </Card>
  );
}

function Bubble({ role, children }: { role: "user" | "assistant"; children: React.ReactNode }) {
  const mine = role === "user";
  return (
    <div className={`bubble-in flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[88%] rounded-[20px] px-4 py-3 text-[15px] leading-[1.55] ${
        mine ? "rounded-br-md bg-[linear-gradient(135deg,#2f6bff,#5b5cff)] text-white shadow-[0_8px_20px_-10px_rgb(47_107_255/0.7)]" : "rounded-bl-md bg-mist text-ink"}`}>
        {children}
      </div>
    </div>
  );
}

const Dot = ({ d = 0 }: { d?: number }) => (
  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-faint" style={{ animationDelay: `${d}ms` }} />
);

const STATUS_STYLE: Record<string, string> = {
  PENDING: "bg-mist text-muted",
  WON: "bg-up-soft text-up",
  LOST: "bg-down-soft text-down",
  REFUNDED: "bg-mist text-muted",
};
const STATUS_LABEL: Record<string, string> = { PENDING: "Open", WON: "Right", LOST: "Wrong", REFUNDED: "Refunded" };

function SessionsCard({ rows, activeId, onOpen }: {
  rows: { session: PredictSession; pick: Pick | null }[]; activeId: number | null; onOpen: (s: PredictSession) => void;
}) {
  return (
    <Card tour="sessions">
      <CardTitle aside={rows.length ? `${rows.length} total` : undefined}>Your sessions</CardTitle>
      {rows.length === 0 ? (
        <p className="mt-4 text-[15px] text-muted">No sessions yet. Start one above to see the model's forecast.</p>
      ) : (
        <div className="mt-3 divide-y divide-hair">
          {rows.slice(0, 8).map(({ session: s, pick }) => (
            <button key={s.id} onClick={() => onOpen(s)}
              className={`press grid w-full cursor-pointer grid-cols-[56px_1fr_auto] items-center gap-3 rounded-xl px-3 py-3 text-left text-[14px] hover:bg-mist ${s.id === activeId ? "bg-mist" : ""}`}>
              <span className="font-medium">{s.asset}</span>
              <span className="truncate text-ink-2">
                {s.mode === "own" ? "Your call first" : "Model first"} · {dateTime(utcMs(s.created_at))}
                {pick && <span className="text-muted"> · {pick.direction === "UP" ? "higher" : "lower"}</span>}
              </span>
              {pick ? (
                <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-medium ${STATUS_STYLE[pick.status]}`}>{STATUS_LABEL[pick.status]}</span>
              ) : (
                <span className="text-[12px] text-faint">{isOpen(s) ? "Open" : "No call"}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}

function RecordCard({ token, reload }: { token: string | null; reload: number }) {
  const rec = useFetch(() => (token ? api.record(token) : Promise.resolve(null)), [token, reload], 300_000).data;
  const t = rec?.total;
  const rate = (right: number, n: number) => (n ? `${right}/${n}` : "—");
  return (
    <Card tour="record">
      <CardTitle aside="from your Walrus memory">Your record</CardTitle>
      {!t || t.calls === 0 ? (
        <p className="mt-4 text-[15px] leading-relaxed text-muted">
          Resolved calls are saved to your own Walrus memory. Once you have a few, this shows how often you are right
          when you agree with the model and when you don't.
        </p>
      ) : (
        <div className="mt-5 grid grid-cols-3 gap-4">
          <Mini label="Right calls" value={rate(t.right, t.calls)} />
          <Mini label="With the model" value={rate(t.agreed_right, t.agreed_calls)} />
          <Mini label="Against it" value={rate(t.disagreed_right, t.disagreed_calls)} />
        </div>
      )}
      {rec && rec.memory_blobs.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-2 border-t border-hair pt-4">
          {rec.memory_blobs.slice(0, 4).map((b) => (
            <a key={b} href={`https://aggregator.walrus-mainnet.walrus.space/v1/blobs/${encodeURIComponent(b)}`} target="_blank" rel="noreferrer"
              className="rounded-full bg-mist px-3 py-1 font-mono text-[11px] text-walrus hover:underline">{shortBlob(b)}</a>
          ))}
        </div>
      )}
    </Card>
  );
}

function RaceCard({ asset }: { asset: Asset }) {
  const race = useFetch(() => api.race(asset), [asset], 300_000).data;
  const last = race?.series.at(-1);
  return (
    <Card tour="race">
      <CardTitle aside={race ? `${race.n} resolved` : undefined}>Model track record · {asset}</CardTitle>
      <p className="mt-1 text-[14px] text-muted">
        Cumulative Brier score on resolved forecasts. Lower is better.
        {last && <> Without memory {last.amnesiac.toFixed(3)} · <span className="text-recall">with memory {last.recall.toFixed(3)}</span></>}
      </p>
      <div className="mt-5"><RaceChart series={race?.series ?? []} height={220} /></div>
    </Card>
  );
}

const REASON_LABEL: Record<string, string> = {
  signup: "Welcome credits",
  weekly_refill: "Weekly top-up",
  session: "Opened a session",
  session_refund: "Session refunded",
  call_right: "Correct call",
  call_refund: "Call refunded",
};

function LedgerCard({ me }: { me: Me | null }) {
  return (
    <Card tour="ledger">
      <CardTitle aside={me ? `week ${me.week.split("-W")[1]} · max ${me.cap}` : undefined}>Credits</CardTitle>
      <div className="mt-4 divide-y divide-hair">
        {(me?.ledger ?? []).slice(0, 8).map((e) => (
          <div key={e.id} className="grid grid-cols-[1fr_auto_40px] items-center gap-3 py-3 text-[14px]">
            <span className="text-ink-2">{REASON_LABEL[e.reason] ?? e.reason}</span>
            <span className={`tabular font-medium ${e.delta > 0 ? "text-up" : e.delta < 0 ? "text-ink" : "text-muted"}`}>
              {e.delta > 0 ? "+" : ""}{e.delta}
            </span>
            <span className="tabular text-right text-muted">{e.balance}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
