import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";

type Turn = { role: "user" | "assistant"; text: string };

const SUGGESTIONS = [
  "What is MarketRecall?",
  "How do I start?",
  "How do credits work?",
  "Why does it use Walrus?",
  "Apakah ada uang yang dipakai?",
];

export function GuideChat({ onOpenApp }: { onOpenApp: () => void }) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns.length, busy]);
  useEffect(() => {
    if (!open) return;
    // not on phones: the keyboard would cover the answers
    if (window.matchMedia("(pointer: fine)").matches) input.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const send = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    setBusy(true);
    setError(null);
    setText("");
    const history = turns;
    setTurns((t) => [...t, { role: "user", text: question }]);
    try {
      const out = await api.guide(question, history);
      setTurns((t) => [...t, { role: "assistant", text: out.text }]);
    } catch (e) {
      setTurns((t) => t.slice(0, -1));
      setText(question);
      setError(e instanceof ApiError ? e.message : "The guide is unavailable right now.");
    } finally {
      setBusy(false);
    }
  };

  const asked = new Set(turns.filter((t) => t.role === "user").map((t) => t.text));

  return (
    // closed: icon docked bottom-right; open: slides to the centre with the panel above it
    <div className="pointer-events-none fixed bottom-4 z-50 flex flex-col items-center transition-[right,transform] duration-500 ease-[var(--ease-out-soft)] sm:bottom-6"
      style={{ right: open ? "50%" : "20px", transform: open ? "translateX(50%)" : "none" }}>
      {open && (
        <div role="dialog" aria-label="MarketRecall guide"
          className="bubble-in pointer-events-auto mb-3 flex border border-hair/70 bg-white max-h-[min(560px,72vh)] w-[min(420px,calc(100vw-32px))] flex-col overflow-hidden rounded-[28px] shadow-[0_30px_80px_-24px_rgb(30_50_110/0.45)]">
          <div className="flex items-center justify-between border-b border-hair/70 px-5 py-4">
            <div className="flex items-center gap-3">
              <Spark className="h-8 w-8" />
              <div>
                <div className="text-[15px] font-semibold tracking-[-0.01em]">MarketRecall guide</div>
                <div className="text-[12px] text-muted">Product questions. Forecasts are in the app.</div>
              </div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close guide"
              className="press -mr-1 cursor-pointer rounded-full p-2 text-muted hover:bg-mist hover:text-ink">
              <svg width="12" height="12" viewBox="0 0 14 14"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
            </button>
          </div>

          <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
            <Bubble role="assistant">
              Hi, I can explain what MarketRecall does, how sessions and credits work, and how its memory on Walrus is
              used. You can ask in English or Bahasa Indonesia.
            </Bubble>
            {turns.map((t, i) => <Bubble key={i} role={t.role}>{t.text}</Bubble>)}
            {busy && (
              <Bubble role="assistant">
                <span className="inline-flex gap-1">
                  {[0, 150, 300].map((d) => <span key={d} className="h-1.5 w-1.5 animate-bounce rounded-full bg-faint" style={{ animationDelay: `${d}ms` }} />)}
                </span>
              </Bubble>
            )}
          </div>

          <div className="border-t border-hair/70 px-5 pb-4 pt-3">
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.filter((s) => !asked.has(s)).slice(0, turns.length ? 2 : 4).map((s) => (
                <button key={s} onClick={() => send(s)} disabled={busy}
                  className="press cursor-pointer rounded-full border border-hair bg-white/70 px-3 py-1.5 text-[12px] text-ink-2 hover:border-recall/40 hover:bg-recall-soft hover:text-recall disabled:opacity-50">
                  {s}
                </button>
              ))}
            </div>
            <form className="mt-3 flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); send(text); }}>
              <input ref={input} value={text} onChange={(e) => setText(e.target.value)} maxLength={300}
                placeholder="Ask about MarketRecall…" aria-label="Your question"
                className="h-11 flex-1 rounded-full bg-mist px-4 text-[14px] outline-none focus-visible:outline-none placeholder:text-faint focus:ring-2 focus:ring-recall/30" />
              <button type="submit" disabled={busy || !text.trim()} aria-label="Send"
                className="press glow flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full bg-recall text-white disabled:cursor-not-allowed disabled:opacity-40">
                <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M7 12V2M2.5 6.5L7 2l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </form>
            {error && <p className="mt-2 text-[12px] text-down">{error}</p>}
            <p className="mt-2 text-[11px] leading-relaxed text-faint">
              Answers cover the product only and are not financial advice. For a forecast,{" "}
              <button onClick={onOpenApp} className="link cursor-pointer text-recall">open a session</button>.
            </p>
          </div>
        </div>
      )}

      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={open ? "Close guide" : "Ask about MarketRecall"}
        title={open ? undefined : "Ask about MarketRecall"}
        className={`press group pointer-events-auto flex cursor-pointer items-center rounded-full border border-white/80 bg-white/85 p-1 text-[14px] font-medium text-ink shadow-[0_16px_40px_-14px_rgb(30_50_110/0.45)] backdrop-blur-xl transition-[padding] duration-500 hover:shadow-[0_18px_44px_-12px_rgb(47_107_255/0.6)] ${open ? "pr-5" : ""}`}>
        <Spark className={`transition-[transform,width,height] duration-500 ease-[var(--ease-spring)] group-hover:rotate-12 ${open ? "h-8 w-8" : "h-11 w-11"}`} />
        <span aria-hidden className={`overflow-hidden whitespace-nowrap transition-[max-width,opacity,margin] duration-500 ease-[var(--ease-out-soft)] ${
          open ? "ml-2.5 max-w-[120px] opacity-100" : "ml-0 max-w-0 opacity-0"}`}>
          Close guide
        </span>
      </button>
    </div>
  );
}

function Bubble({ role, children }: { role: Turn["role"]; children: React.ReactNode }) {
  const mine = role === "user";
  return (
    <div className={`bubble-in flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[88%] rounded-[18px] px-3.5 py-2.5 text-[14px] leading-[1.55] ${
        mine ? "rounded-br-md bg-[linear-gradient(135deg,#2f6bff,#5b5cff)] text-white" : "rounded-bl-md bg-mist text-ink"}`}>
        {children}
      </div>
    </div>
  );
}

function Spark({ className = "" }: { className?: string }) {
  return <img src="/aibot.svg" alt="" aria-hidden className={`shrink-0 ${className}`} />;
}
