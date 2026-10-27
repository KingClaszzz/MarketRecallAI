import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

export type TourStep = {
  /** `data-tour` name of the element to highlight; omit for a centred card. */
  target?: string;
  title: string;
  body: React.ReactNode;
  action?: string;
};

type Rect = { top: number; left: number; width: number; height: number };

const PAD = 10;
const NAV = 56; // top bar height

function findTarget(name?: string): HTMLElement | null {
  if (!name) return null;
  const el = document.querySelector<HTMLElement>(`[data-tour="${name}"]`);
  return el && el.offsetParent !== null ? el : null;
}

export function Tour({ steps, open, onClose }: { steps: TourStep[]; open: boolean; onClose: (finished: boolean) => void }) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const [cardH, setCardH] = useState(220);
  const card = useRef<HTMLDivElement>(null);
  const step = steps[index];
  const last = index === steps.length - 1;

  useEffect(() => { if (open) setIndex(0); }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = findTarget(step.target);
    if (el) {
      const r = el.getBoundingClientRect();
      const room = window.innerHeight - NAV;
      const top = r.height + 2 * PAD < room * 0.62
        ? r.top + window.scrollY - NAV - (room - r.height) / 2 + 60
        : r.top + window.scrollY - NAV - 24;
      window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    }
    let frame = 0;
    const track = () => {
      const target = findTarget(step.target);
      if (target) {
        const r = target.getBoundingClientRect();
        setRect((prev) => (prev && Math.abs(prev.top - r.top) < 0.5 && Math.abs(prev.left - r.left) < 0.5 && prev.width === r.width && prev.height === r.height
          ? prev : { top: r.top, left: r.left, width: r.width, height: r.height }));
      } else {
        setRect(null);
      }
      frame = requestAnimationFrame(track);
    };
    track();
    return () => cancelAnimationFrame(frame);
  }, [open, step]);

  useLayoutEffect(() => {
    if (card.current) setCardH(card.current.offsetHeight);
  }, [index, open, rect === null]);

  const go = useCallback((d: number) => {
    const n = index + d;
    if (n >= steps.length) onClose(true);
    else setIndex(Math.max(0, n));
  }, [index, steps.length, onClose]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "Enter") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "Escape") onClose(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, go, onClose]);

  if (!open) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const narrow = vw < 640;
  const cardW = Math.min(380, vw - 32);
  let cardStyle: React.CSSProperties;
  if (!rect || narrow) {
    cardStyle = narrow ? { left: 16, right: 16, bottom: 16 } : { left: (vw - cardW) / 2, top: Math.max(80, (vh - cardH) / 2), width: cardW };
  } else if (rect.height > vh * 0.45) {
    // tall target: place the card beside it
    const top = Math.min(Math.max(NAV + 16, rect.top), vh - cardH - 16);
    const right = rect.left + rect.width + PAD + 16;
    const left = rect.left - PAD - 16 - cardW;
    cardStyle = right + cardW < vw - 16 ? { top, width: cardW, left: right }
      : left > 16 ? { top, width: cardW, left }
      // full-width target: bottom-left
      : { top: vh - cardH - 24, width: cardW, left: Math.max(16, rect.left + 24) };
  } else {
    const below = rect.top + rect.height + PAD + 14;
    const above = rect.top - PAD - 14 - cardH;
    const top = below + cardH < vh - 12 ? below : above > NAV + 8 ? above : Math.max(NAV + 12, vh - cardH - 16);
    const left = Math.min(Math.max(16, rect.left + rect.width / 2 - cardW / 2), vw - cardW - 16);
    cardStyle = { top, left, width: cardW };
  }

  return (
    <div className="fixed inset-0 z-[70]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {rect ? (
        <div aria-hidden className="pointer-events-none fixed rounded-[24px] ring-2 ring-white/80 transition-all duration-500 ease-[var(--ease-out-soft)]"
          style={{
            top: rect.top - PAD, left: rect.left - PAD, width: rect.width + 2 * PAD, height: rect.height + 2 * PAD,
            boxShadow: "0 0 0 9999px rgb(14 18 32 / 0.55)",
          }} />
      ) : (
        <div aria-hidden className="fade-in fixed inset-0 bg-[rgb(14_18_32/0.55)] backdrop-blur-[2px]" />
      )}
      <div className="fixed inset-0" onClick={(e) => e.stopPropagation()} />

      <div ref={card} key={index} className="bubble-in fixed rounded-[24px] bg-white p-6 shadow-[0_30px_80px_-20px_rgb(14_18_32/0.5)]" style={cardStyle}>
        <div className="flex items-center justify-between">
          <span className="tabular text-[12px] font-medium text-recall">Step {index + 1} of {steps.length}</span>
          <button onClick={() => onClose(false)} className="press cursor-pointer rounded-full px-2 py-1 text-[12px] text-muted hover:bg-mist hover:text-ink">
            Skip tour
          </button>
        </div>
        <h2 id="tour-title" className="mt-3 text-[20px] font-semibold leading-snug tracking-[-0.02em]">{step.title}</h2>
        <div className="mt-2 text-[15px] leading-relaxed text-ink-2">{step.body}</div>
        {step.action && (
          <p className="mt-3 rounded-[14px] bg-recall-soft px-3.5 py-2.5 text-[13px] leading-relaxed text-recall">{step.action}</p>
        )}
        <div className="mt-5 flex items-center justify-between gap-3">
          <div className="flex gap-1.5" aria-hidden>
            {steps.map((_, i) => (
              <span key={i} className={`h-1.5 rounded-full transition-all duration-300 ${i === index ? "w-5 bg-recall" : i < index ? "w-1.5 bg-recall/40" : "w-1.5 bg-hair"}`} />
            ))}
          </div>
          <div className="flex gap-2">
            {index > 0 && (
              <button onClick={() => go(-1)} className="press cursor-pointer rounded-full bg-mist px-4 py-2 text-[14px] font-medium text-ink hover:bg-hair">
                Back
              </button>
            )}
            <button onClick={() => go(1)} autoFocus
              className="press glow cursor-pointer rounded-full bg-recall px-5 py-2 text-[14px] font-medium text-white hover:bg-[#1f57e6]">
              {last ? "Finish" : index === 0 ? "Start tour" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
