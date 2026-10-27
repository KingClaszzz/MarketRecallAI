import { Background3D } from "../components/Background3D";
import { CursorFollower } from "../components/CursorFollower";
import { GuideChat } from "../components/GuideChat";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RaceChart, Sparkline } from "../components/Charts";
import { Aurora, Button, CountUp, Footer, Logo, Segmented } from "../components/Chrome";
import { ProbabilityDial } from "../components/ProbabilityDial";
import { Reveal } from "../components/Reveal";
import { SignInDialog } from "../components/SignInDialog";
import { api, ASSET_NAMES, ASSETS, type Asset, type Candle, type Forecast, type Lesson, type Memory } from "../lib/api";
import { ACTION_LABEL, pct, price, regimeSentence, shortBlob } from "../lib/format";
import { useSession } from "../lib/session";
import { useFetch } from "../lib/useFetch";

export default function Landing() {
  const navigate = useNavigate();
  const { token } = useSession();
  const [signIn, setSignIn] = useState(false);
  const live = useFetch(api.live, [], 60_000).data;
  const stats = useFetch(api.stats, [], 120_000).data;
  const memories = useFetch(() => api.memories(6), [], 120_000).data ?? [];
  const candles = useFetch(() => api.candles("SUI", 48), [], 300_000).data ?? [];

  const openApp = () => (token ? navigate("/app") : setSignIn(true));

  return (
    <div className="isolate min-h-screen bg-paper">
      <Background3D />
      <CursorFollower />
      <Nav onOpenApp={openApp} signedIn={Boolean(token)} />
      <Hero forecasts={live?.forecasts} onOpenApp={openApp} />
      <Bento forecasts={live?.forecasts} episodes={stats?.episodes_learned} stored={stats?.memories_stored}
        memories={memories} closes={candles.map((c) => c.close)} />
      <TwoForecasters forecasts={live?.forecasts} />
      <Distrust forecasts={live?.forecasts} />
      <Gate />
      <Sessions onOpenApp={openApp} />
      <OnWalrus count={stats?.memories_stored} memories={memories} />
      <OnTatum candles={candles} />
      <Race />
      <FinalCta onOpenApp={openApp} />
      <Footer />
      <GuideChat onOpenApp={openApp} />
      <SignInDialog open={signIn} onClose={() => setSignIn(false)} onSignedIn={() => navigate("/app")} />
    </div>
  );
}

function Nav({ onOpenApp, signedIn }: { onOpenApp: () => void; signedIn: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/60 bg-white/60 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex h-14 max-w-[1080px] items-center justify-between px-6">
        <Logo />
        <nav className="hidden items-center gap-8 text-[13px] text-ink-2 md:flex">
          <a href="#how" className="link py-1 hover:text-ink">How it works</a>
          <a href="#gate" className="link py-1 hover:text-ink">Validation</a>
          <a href="#sessions" className="link py-1 hover:text-ink">Sessions</a>
          <a href="#walrus" className="link py-1 hover:text-ink">Memory</a>
          <a href="#race" className="link py-1 hover:text-ink">Track record</a>
        </nav>
        <Button size="sm" onClick={onOpenApp}>{signedIn ? "Open app" : "Sign in"}</Button>
      </div>
    </header>
  );
}

const THEME = [["Forecast", "var(--color-recall)"], ["Remember", "var(--color-walrus)"], ["Improve", "var(--color-lilac)"]];

function Hero({ forecasts, onOpenApp }: { forecasts?: Record<Asset, Forecast | null>; onOpenApp: () => void }) {
  const [asset, setAsset] = useState<Asset>("WAL");
  const [pinned, setPinned] = useState(false);
  useEffect(() => {
    if (pinned) return;
    const id = setInterval(() => setAsset((a) => ASSETS[(ASSETS.indexOf(a) + 1) % ASSETS.length]), 6000);
    return () => clearInterval(id);
  }, [pinned]);
  const f = forecasts?.[asset] ?? null;

  return (
    <section className="relative overflow-hidden">
      <Aurora />
      <div className="relative mx-auto max-w-[1080px] px-6 pb-16 text-center">
        <Reveal className="flex min-h-[calc(100svh-56px)] flex-col items-center justify-center py-12">
          <div className="flex flex-wrap items-center justify-center gap-2">
            {THEME.map(([w, c], i) => (
              <span key={w} className="flex items-center gap-2">
                {i > 0 && <span aria-hidden className="text-faint">›</span>}
                <span className="chip text-ink-2">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} />
                  {w}
                </span>
              </span>
            ))}
          </div>
          <p className="eyebrow mt-6">Hourly 4-hour forecasts for SUI, WAL and CETUS</p>
          <h1 className="display mx-auto mt-5 max-w-[880px] text-[44px] sm:text-[76px]">
            The forecaster that <span className="text-gradient">remembers</span> when it was wrong.
          </h1>
          <p className="mx-auto mt-6 max-w-[620px] text-[19px] leading-[1.5] text-ink-2 sm:text-[21px]">
            Make your own call or run the model first, then ask questions about the reading. Every forecast is scored
            and stored on Walrus, and the model adjusts its confidence to how it has performed in similar markets.
          </p>
          <div className="mt-9 flex items-center justify-center gap-6">
            <Button size="lg" onClick={onOpenApp}>Start a session</Button>
            <a href="#sessions" className="link group text-[17px] text-recall">How it works <span className="nudge-x inline-block">›</span></a>
          </div>
        </Reveal>

        <Reveal delay={150}>
          <div className="glass glass-sheen lift mx-auto mt-0 max-w-[880px] rounded-[36px] px-6 pb-10 pt-6 sm:px-12" onPointerMove={sheen}>
            <div className="flex items-center justify-between">
              <Segmented label="Asset" tone="white" options={ASSETS} value={asset} onChange={(a) => { setAsset(a); setPinned(true); }} />
              <span className="flex items-center gap-2 text-[12px] text-muted">
                <span className="pulse-dot h-2 w-2 rounded-full bg-up" /> Live<span className="hidden sm:inline"> · next 4 hours</span>
              </span>
            </div>

            <div className="mx-auto mt-6 max-w-[520px]">
              <ProbabilityDial amnesiac={f?.amnesiac_p ?? 0.5} recall={f?.recall_p ?? 0.5} noCall={f?.recall_action === "NO_CALL"} />
            </div>

            <div className="mt-2 grid grid-cols-2 gap-4 text-left sm:gap-10">
              <div className="border-l-2 border-amnesiac pl-4">
                <div className="text-[13px] text-muted">Without memory</div>
                <div className="tabular mt-1 text-[34px] font-semibold tracking-[-0.03em] text-ink-2 sm:text-[44px]">
                  {f ? pct(f.amnesiac_p) : "—"}<span className="ml-1 text-[15px] font-normal text-muted">up</span>
                </div>
              </div>
              <div className="border-l-2 border-recall pl-4">
                <div className="text-[13px] text-recall">With memory</div>
                <div className="tabular mt-1 text-[34px] font-semibold tracking-[-0.03em] sm:text-[44px]">
                  {f ? (f.recall_action === "NO_CALL" ? "No call" : pct(f.recall_p)) : "—"}
                  {f && f.recall_action !== "NO_CALL" && <span className="ml-1 text-[15px] font-normal text-muted">up</span>}
                </div>
              </div>
            </div>
            <p className="mx-auto mt-8 max-w-[640px] text-[15px] leading-relaxed text-ink-2">
              {f ? (
                <>
                  {ASSET_NAMES[asset]} at ${price(f.close_at_t)} in a {regimeSentence(f.regime)}.{" "}
                  {f.trace.decision.n_matched > 0 && (
                    <span className="text-muted">Based on {f.trace.decision.n_matched.toLocaleString()} similar hours in memory.</span>
                  )}
                </>
              ) : (
                <span className="text-muted">Loading the latest forecast…</span>
              )}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function sheen(e: React.PointerEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
}

function Tile({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} onPointerMove={sheen} className="glass glass-sheen lift group flex h-full flex-col rounded-[28px] p-7">
      {children}
    </a>
  );
}

function TileHead({ label, color }: { label: string; color: string }) {
  return (
    <div className="flex items-center justify-between text-[13px] font-medium" style={{ color }}>
      {label}
      <span aria-hidden className="nudge-x text-faint">›</span>
    </div>
  );
}

function Bento({ forecasts, episodes, stored, memories, closes }: {
  forecasts?: Record<Asset, Forecast | null>; episodes?: number; stored?: number; memories: Memory[]; closes: number[];
}) {
  const f = forecasts?.WAL ?? null;
  const bars: [string, number | undefined, string][] = [
    ["Amnesiac", f?.amnesiac_p, "var(--color-amnesiac)"],
    ["Recall", f?.recall_p, "var(--color-recall)"],
  ];
  return (
    <section>
      <div className="mx-auto max-w-[1080px] px-6 pb-16 pt-4">
        <div className="grid grid-cols-[minmax(0,1fr)] gap-5 sm:grid-cols-2 md:grid-cols-6 [&>*]:min-w-0">
          <Reveal className="sm:col-span-2 md:col-span-4 md:row-span-2">
            <Tile href="#walrus">
              <TileHead label="Walrus Memory" color="var(--color-walrus)" />
              <h3 className="mt-3 max-w-[440px] text-[26px] font-semibold leading-tight tracking-[-0.02em] sm:text-[28px]">
                Every resolved forecast is written to Walrus mainnet.
              </h3>
              <div className="mt-6 flex items-baseline gap-2">
                <span className="text-[48px] font-semibold leading-none tracking-[-0.04em]"><CountUp value={stored} /></span>
                <span className="text-[14px] text-muted">memories stored</span>
              </div>
              <div className="mt-auto space-y-2 pt-8">
                {memories.slice(0, 4).map((m) => (
                  <div key={m.id} className="flex items-center gap-3 rounded-[14px] bg-white/60 px-3.5 py-2.5">
                    <span className="w-[84px] shrink-0 text-[11px] font-medium tracking-wide text-walrus">{m.kind}</span>
                    <span className="truncate text-[13px] text-ink-2">{m.text.split("\n")[0].replace(/^\[[^\]]+\](\[[^\]]+\])?\s*/, "")}</span>
                    <span className="ml-auto hidden shrink-0 font-mono text-[11px] text-faint sm:inline">{m.blob_id ? shortBlob(m.blob_id) : "pending"}</span>
                  </div>
                ))}
              </div>
            </Tile>
          </Reveal>

          <Reveal delay={80} className="md:col-span-2">
            <Tile href="#how">
              <TileHead label="Amnesiac vs Recall" color="var(--color-recall)" />
              <p className="mt-2 text-[15px] leading-relaxed text-ink-2">Same model, with and without memory. WAL this hour:</p>
              <div className="mt-auto space-y-3 pt-6">
                {bars.map(([label, p, color]) => (
                  <div key={label}>
                    <div className="flex justify-between text-[13px]">
                      <span className="text-muted">{label}</span>
                      <span className="tabular font-medium">{p === undefined ? "—" : `${pct(p)} up`}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-hair">
                      <div className="h-full rounded-full transition-[width] duration-700 ease-[var(--ease-out-soft)]"
                        style={{ width: `${(p ?? 0.5) * 100}%`, background: color }} />
                    </div>
                  </div>
                ))}
              </div>
            </Tile>
          </Reveal>

          <Reveal delay={160} className="md:col-span-2">
            <Tile href="#data">
              <TileHead label="Tatum data" color="var(--color-lilac)" />
              <p className="mt-2 text-[15px] leading-relaxed text-ink-2">Live 1h candles and Sui gRPC checkpoints.</p>
              <div className="mt-auto pt-6">
                {closes.length > 1 && <Sparkline values={closes} height={40} stroke="var(--color-lilac)" />}
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="tabular text-[24px] font-semibold tracking-[-0.03em]">{closes.length ? `$${price(closes.at(-1)!)}` : "—"}</span>
                  <span className="text-[12px] text-muted">SUI, last 48h</span>
                </div>
              </div>
            </Tile>
          </Reveal>

          <Reveal delay={80} className="md:col-span-3">
            <Tile href="#sessions">
              <TileHead label="Sessions & credits" color="var(--color-up)" />
              <div className="mt-4 grid grid-cols-3 gap-3">
                {[["1", "credit per session"], ["10", "analyst questions"], ["+2", "for a correct call"]].map(([v, l]) => (
                  <div key={l}>
                    <div className="tabular text-[32px] font-semibold leading-none tracking-[-0.04em]">{v}</div>
                    <div className="mt-2 text-[13px] leading-snug text-muted">{l}</div>
                  </div>
                ))}
              </div>
              <p className="mt-auto pt-6 text-[13px] text-muted">3 free credits a week, up to 10. Nothing to buy.</p>
            </Tile>
          </Reveal>

          <Reveal delay={160} className="md:col-span-3">
            <Tile href="#race">
              <TileHead label="Track record" color="var(--color-ink-2)" />
              <div className="mt-4 flex items-baseline gap-2">
                <span className="text-[32px] font-semibold leading-none tracking-[-0.04em]"><CountUp value={episodes} /></span>
                <span className="text-[13px] text-muted">hours of history evaluated</span>
              </div>
              <p className="mt-auto pt-6 text-[13px] text-muted">Both forecasters are scored every hour against a coin flip.</p>
            </Tile>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

function SectionHead({ eyebrow, title, body, center = false }: { eyebrow: string; title: React.ReactNode; body?: React.ReactNode; center?: boolean }) {
  return (
    <Reveal className={center ? "text-center" : ""}>
      <p className="eyebrow">{eyebrow}</p>
      <h2 className={`display mt-4 text-balance text-[38px] sm:text-[56px] ${center ? "mx-auto max-w-[820px]" : "max-w-[760px]"}`}>{title}</h2>
      {body && <p className={`mt-5 text-[19px] leading-[1.55] text-ink-2 ${center ? "mx-auto max-w-[640px]" : "max-w-[620px]"}`}>{body}</p>}
    </Reveal>
  );
}

function TwoForecasters({ forecasts }: { forecasts?: Record<Asset, Forecast | null> }) {
  return (
    <section id="how" className="bg-mist/55">
      <div className="mx-auto max-w-[1080px] px-6 py-28">
        <SectionHead eyebrow="How it works" title={<>Same model.<br />One of them remembers.</>}
          body="Both forecasts use the same inputs: hourly prices and Sui network activity. Only one checks how its past forecasts performed before publishing a number." />
        <div className="mt-14 grid gap-5 md:grid-cols-2">
          <Reveal>
            <div className="surface lift h-full rounded-[28px] p-8">
              <div className="text-[13px] font-medium text-muted">Amnesiac</div>
              <h3 className="mt-3 text-[26px] font-semibold tracking-[-0.02em]">No memory of past errors.</h3>
              <p className="mt-3 text-[16px] leading-relaxed text-ink-2">
                A logistic regression trained on a rolling 60-day window of price and on-chain features. Its confidence
                never reflects how its previous forecasts turned out.
              </p>
            </div>
          </Reveal>
          <Reveal delay={100}>
            <div className="lift relative h-full overflow-hidden rounded-[28px] bg-[linear-gradient(140deg,#16181f_0%,#1d2240_60%,#2a2463_100%)] p-8 text-white">
              <div className="text-[13px] font-medium text-[#8fb0ff]">Recall</div>
              <h3 className="mt-3 text-[26px] font-semibold tracking-[-0.02em]">Calibrated by its own history.</h3>
              <p className="mt-3 text-[16px] leading-relaxed text-white/75">
                The same output, adjusted by a memory policy. It looks up its results in similar market regimes and
                lowers its confidence where it has been overconfident.
              </p>
            </div>
          </Reveal>
        </div>

        <Reveal delay={150}>
          <div className="mt-5 overflow-hidden rounded-[28px] bg-white">
            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-6 border-b border-hair px-8 py-4 text-[13px] text-muted sm:gap-x-12">
              <span>Current forecast</span><span className="text-right">Amnesiac</span><span className="text-right">Recall</span><span className="text-right">Similar hours</span>
            </div>
            {ASSETS.map((a) => {
              const f = forecasts?.[a];
              return (
                <div key={a} className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-x-6 border-b border-hair px-8 py-5 last:border-0 sm:gap-x-12">
                  <span className="text-[17px] font-medium">{ASSET_NAMES[a]} <span className="text-muted">{a}</span></span>
                  <span className="tabular text-right text-[17px] text-muted">{f ? pct(f.amnesiac_p) : "—"}</span>
                  <span className="tabular text-right text-[17px] font-semibold text-recall">
                    {f ? (f.recall_action === "NO_CALL" ? "No call" : pct(f.recall_p)) : "—"}
                  </span>
                  <span className="tabular text-right text-[15px] text-muted">{f ? `${f.trace.decision.n_matched} hrs` : "—"}</span>
                </div>
              );
            })}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Distrust({ forecasts }: { forecasts?: Record<Asset, Forecast | null> }) {
  const f = ASSETS.map((a) => forecasts?.[a]).find((x) => x && x.recall_action === "ADJUSTED") ?? forecasts?.SUI ?? null;
  const c = f ? f.trace.decision.credibility[f.trace.decision.voice] : undefined;
  return (
    <section>
      <div className="mx-auto grid max-w-[1080px] items-center gap-14 px-6 py-28 md:grid-cols-[1.05fr_1fr]">
        <SectionHead eyebrow="Memory in practice" title="It learns where it is unreliable."
          body="Memory here is not a chat log. It is a running record of how often the model was right in each market regime, and it directly changes the published probability." />
        <Reveal delay={100}>
          <div className="surface lift rounded-[28px] p-8">
            <div className="flex items-baseline justify-between">
              <span className="text-[13px] text-muted">{f ? `${ASSET_NAMES[f.asset]} · this hour` : "This hour"}</span>
              <span className="rounded-full bg-recall-soft px-3 py-1 text-[12px] font-medium text-recall">
                {f ? ACTION_LABEL[f.recall_action] : "—"}
              </span>
            </div>
            {c && (
              <div className="mt-6 grid grid-cols-2 gap-6">
                <Metric label="Average forecast" value={pct(c.avg_p)} />
                <Metric label="Observed up rate" value={pct(c.freq_up)} accent />
              </div>
            )}
            <div className="mt-6 h-px bg-hair" />
            <p className="mt-6 text-[18px] leading-[1.55] tracking-[-0.01em]">
              “{f?.trace.explanation?.text ?? "Loading the latest explanation…"}”
            </p>
            {f && (
              <p className="mt-4 text-[13px] text-muted">
                Based on {f.trace.decision.n_matched} similar hours. Written by the agent; every figure is checked against the data.
              </p>
            )}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="text-[13px] text-muted">{label}</div>
      <div className={`tabular mt-1 text-[40px] font-semibold tracking-[-0.03em] ${accent ? "text-recall" : ""}`}>{value}</div>
    </div>
  );
}

const RULES: { rule: string; name: string; text: string }[] = [
  { rule: "shrink", name: "Reduce overconfidence", text: "Pull the probability toward 50% according to how well calibrated the model has been in similar regimes." },
  { rule: "abstain", name: "Decline when unreliable", text: "Publish no forecast when no model has shown skill in the current regime." },
  { rule: "switch", name: "Defer to the stronger model", text: "Use whichever model has the best record in similar regimes." },
];

function Gate() {
  const lessons = useFetch(() => api.lessons(), [], 300_000).data ?? [];
  const status = (asset: Asset, rule: string) =>
    lessons.find((l: Lesson) => l.asset === asset && l.rule === rule)?.status ?? "pending";
  return (
    <section id="gate" className="overflow-hidden bg-mist/55">
      <div className="mx-auto max-w-[1080px] px-6 py-28">
        <SectionHead center eyebrow="Validation" title="Each rule has to prove itself."
          body="A memory rule is enabled only if it improves the forecast on two separate periods of historical data. Rules that fail stay off, and their status is shown below." />
        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {RULES.map((r, i) => (
            <Reveal key={r.rule} delay={i * 140} from="right">
              <div className="surface lift flex h-full flex-col rounded-[28px] p-7">
                <h3 className="text-[21px] font-semibold tracking-[-0.02em]">{r.name}</h3>
                <p className="mt-2 flex-1 text-[15px] leading-relaxed text-ink-2">{r.text}</p>
                <div className="mt-6 space-y-2">
                  {ASSETS.map((a) => {
                    const s = status(a, r.rule);
                    return (
                      <div key={a} className="flex items-center justify-between text-[14px]">
                        <span className="text-muted">{a}</span>
                        <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-medium ${
                          s === "validated" ? "bg-up-soft text-up" : s === "rejected" ? "bg-mist text-muted" : "bg-mist text-faint"}`}>
                          {s === "validated" ? "Active" : s === "rejected" ? "Rejected" : "Pending"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  { n: "01", title: "Choose how to start", text: "Lock in your own call for the next four hours, or run the model first and decide afterwards." },
  { n: "02", title: "Review the reading", text: "Probability with and without memory, the main inputs behind it, and the model's record in similar conditions." },
  { n: "03", title: "Ask follow-up questions", text: "Up to ten per session. Answers are generated from your session's data, and every number is checked." },
  { n: "04", title: "Resolution", text: "Calls resolve automatically after four hours. A correct call returns two credits, and the result is saved to your Walrus memory." },
];

function Sessions({ onOpenApp }: { onOpenApp: () => void }) {
  return (
    <section id="sessions">
      <div className="mx-auto max-w-[1080px] px-6 py-28">
        <SectionHead eyebrow="Sessions" title={<>Not you versus the model.<br className="hidden sm:block" /> You, with it.</>}
          body="A session gives you the model's full reading, a place to record your own call, and an analyst you can question about both." />
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <Reveal key={s.n} delay={i * 80}>
              <div className="surface lift group flex h-full flex-col rounded-[28px] p-7">
                <div className="tabular flex h-10 w-10 items-center justify-center rounded-full bg-recall-soft text-[13px] font-semibold text-recall transition-colors duration-300 group-hover:bg-recall group-hover:text-white">
                  {s.n}
                </div>
                <div className="mt-6 text-[19px] font-semibold leading-snug tracking-[-0.01em]">{s.title}</div>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-2">{s.text}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={150}>
          <div className="mt-5 grid gap-5 md:grid-cols-[1.2fr_1fr]">
            <ChatPreview />
            <div className="surface lift flex flex-col justify-between rounded-[28px] p-8">
              <div className="grid grid-cols-3 gap-4">
                {[["3", "credits per week"], ["1", "per session"], ["+2", "for a correct call"]].map(([v, l]) => (
                  <div key={l}>
                    <div className="tabular text-[44px] font-semibold leading-none tracking-[-0.04em] text-recall">{v}</div>
                    <div className="mt-2 text-[14px] text-muted">{l}</div>
                  </div>
                ))}
              </div>
              <p className="mt-8 text-[15px] leading-relaxed text-ink-2">
                Credits have no monetary value and cannot be purchased. Sign in with a Sui wallet or Google; signing is free and moves no funds.
              </p>
              <div className="mt-6"><Button size="lg" variant="dark" onClick={onOpenApp}>Get started</Button></div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function ChatPreview() {
  const lines: { me: boolean; text: string }[] = [
    { me: true, text: "Why is it only 51% when it said 54% before memory?" },
    { me: false, text: "In 139 similar hours the model averaged 57% up, but price rose only 49% of the time. It has been overconfident in calm, falling markets, so memory pulls the forecast toward 50%." },
    { me: true, text: "And my own calls?" },
    { me: false, text: "From your Walrus memory: 3 of 4 calls correct, including both times you went against the model." },
  ];
  return (
    <div className="surface lift rounded-[28px] p-6 sm:p-8">
      <div className="flex items-center justify-between text-[13px] text-muted">
        <span className="flex items-center gap-2"><span className="pulse-dot h-2 w-2 rounded-full bg-up" /> Session · WAL · model first</span>
        <span className="tabular">8 of 10 questions left</span>
      </div>
      <div className="mt-6 space-y-3">
        {lines.map((l, i) => (
          <div key={i} className={`bubble-in flex ${l.me ? "justify-end" : "justify-start"}`} style={{ animationDelay: `${300 + i * 650}ms` }}>
            <div className={`max-w-[85%] rounded-[20px] px-4 py-3 text-[15px] leading-[1.55] ${l.me ? "rounded-br-md bg-[linear-gradient(135deg,#2f6bff,#5b5cff)] text-white" : "rounded-bl-md bg-mist"}`}>
              {l.text}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-5 text-[12px] text-faint">Example conversation. Real answers only use figures from your session.</p>
    </div>
  );
}

function OnWalrus({ count, memories }: { count?: number; memories: Memory[] }) {
  return (
    <section id="walrus" className="bg-ink text-white">
      <div className="mx-auto max-w-[1080px] px-6 py-28">
        <Reveal>
          <p className="text-[13px] font-medium text-white/50">Verifiable memory</p>
          <h2 className="display mt-4 max-w-[760px] text-[38px] sm:text-[56px]">Stored on Walrus, not just in our database.</h2>
          <p className="mt-5 max-w-[620px] text-[19px] leading-[1.55] text-white/70">
            Resolved forecasts, validated rules and learned statistics are written to Walrus mainnet, and your calls are
            saved to your own namespace. If our database is lost, the forecaster rebuilds its state from Walrus alone.
          </p>
        </Reveal>
        <Reveal delay={120}>
          <div className="mt-14 overflow-hidden rounded-[28px] border border-white/10">
            <div className="flex items-center justify-between border-b border-white/10 px-7 py-4 text-[13px] text-white/50">
              <span>Latest memories</span>
              <span className="tabular">{count ?? "—"} stored</span>
            </div>
            {memories.map((m) => (
              <a key={m.id} href={m.blob_url ?? undefined} target="_blank" rel="noreferrer"
                className="group grid grid-cols-[90px_1fr_auto] items-center gap-4 border-b border-white/10 px-7 py-4 transition-colors duration-300 last:border-0 hover:bg-white/[0.06]">
                <span className="text-[12px] font-medium tracking-wide text-[#7fd6d6]">{m.kind}</span>
                <span className="truncate text-[14px] text-white/80">{m.text.split("\n")[0].replace(/^\[[^\]]+\](\[[^\]]+\])?\s*/, "")}</span>
                <span className="font-mono text-[12px] text-white/40 transition-colors group-hover:text-[#7fd6d6]">{m.blob_id ? shortBlob(m.blob_id) : "pending"} <span className="nudge-x inline-block">↗</span></span>
              </a>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function OnTatum({ candles }: { candles: Candle[] }) {
  const onchain = useFetch(() => api.onchain(26), [], 300_000).data ?? [];
  const tx = onchain.slice(1).map((r, i) => r.total_tx - onchain[i].total_tx);
  const lastTx = tx.at(-1);
  const cards = [
    { title: "Prices", sub: "Hourly OHLCV candles for SUI, WAL and CETUS from Tatum's market data API.",
      value: candles.at(-1) ? `$${price(candles.at(-1)!.close)}` : "—", note: "SUI, last close", spark: candles.map((c) => c.close) },
    { title: "Network activity", sub: "Checkpoint data sampled hourly from Tatum's Sui gRPC endpoint: transactions, gas and epochs.",
      value: lastTx ? `${Math.round(lastTx / 1000)}k` : "—", note: "transactions in the last hour", spark: tx },
    { title: "Sign-in", sub: "Wallet and Google (zkLogin) signatures are verified on Sui through Tatum's signature verification service.",
      value: "0 gas", note: "to sign in", spark: [] as number[] },
  ];
  return (
    <section id="data">
      <div className="mx-auto max-w-[1080px] px-6 py-28">
        <SectionHead eyebrow="Data" title="Sourced directly from Sui." body="Network activity is one of the model's inputs. In walk-forward testing it improved the tree-based model on all three tokens." />
        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {cards.map((c, i) => (
            <Reveal key={c.title} delay={i * 90}>
              <div className="surface lift flex h-full flex-col rounded-[28px] p-7">
                <h3 className="text-[19px] font-semibold tracking-[-0.01em]">{c.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-ink-2">{c.sub}</p>
                <div className="mt-auto pt-8">
                  {c.spark.length > 1 && <Sparkline values={c.spark} height={44} stroke="var(--color-recall)" />}
                  <div className="tabular mt-3 text-[32px] font-semibold tracking-[-0.03em]">{c.value}</div>
                  <div className="text-[13px] text-muted">{c.note}</div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function Race() {
  const race = useFetch(() => api.race(), [], 300_000).data;
  const last = race?.series.at(-1);
  return (
    <section id="race" className="bg-mist/55">
      <div className="mx-auto max-w-[1080px] px-6 py-28">
        <SectionHead eyebrow="Track record" title="Scored publicly, every hour."
          body="Cumulative Brier score on live forecasts. Lower is better, and a coin flip scores 0.250. If memory stops helping, this chart will show it." />
        <Reveal delay={100}>
          <div className="mt-12 rounded-[28px] bg-white p-6 sm:p-10">
            <div className="mb-6 flex flex-wrap gap-8 text-[14px]">
              <Legend color="var(--color-amnesiac)" label="Amnesiac" value={last?.amnesiac} />
              <Legend color="var(--color-recall)" label="Recall" value={last?.recall} />
              <span className="text-muted">{race ? `${race.n} resolved forecasts` : ""}</span>
            </div>
            <RaceChart series={race?.series ?? []} />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Legend({ color, label, value }: { color: string; label: string; value?: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      {label}
      {value !== undefined && <span className="tabular text-muted">{value.toFixed(3)}</span>}
    </span>
  );
}

function FinalCta({ onOpenApp }: { onOpenApp: () => void }) {
  return (
    <section className="relative overflow-hidden">
      <Aurora className="top-24" />
      <div className="relative mx-auto max-w-[1080px] px-6 py-32 text-center">
        <Reveal>
          <h2 className="display mx-auto max-w-[760px] text-[44px] sm:text-[68px]">Make the call.<br />Then ask <span className="text-gradient">why</span>.</h2>
          <p className="mx-auto mt-6 max-w-[520px] text-[19px] text-ink-2">Three free credits every week. No payment, no gas, no funds required.</p>
          <div className="mt-10">
            <Button size="lg" onClick={onOpenApp}>Start a session</Button>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
