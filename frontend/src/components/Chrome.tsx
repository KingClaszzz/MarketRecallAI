import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

export function Logo({ className = "", compact = false }: { className?: string; compact?: boolean }) {
  return (
    <Link to="/" className={`group flex items-center gap-2 ${className}`} aria-label="MarketRecall home">
      <img src="/favicon.svg" alt="" width="26" height="26" className="h-[26px] w-[26px] transition-transform duration-500 ease-[var(--ease-spring)] group-hover:-rotate-12" />
      <span className={`text-[17px] font-semibold tracking-[-0.02em] ${compact ? "hidden sm:inline" : ""}`}>MarketRecall</span>
    </Link>
  );
}

export function Button({ children, onClick, variant = "primary", size = "md", disabled, className = "" }: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "dark" | "ghost" | "light";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  className?: string;
}) {
  const sizes = { sm: "px-4 py-1.5 text-[13px]", md: "px-5 py-2.5 text-[15px]", lg: "px-7 py-3.5 text-[17px]" };
  const variants = {
    primary: "bg-recall text-white hover:bg-[#1f57e6] glow",
    dark: "bg-ink text-white hover:bg-ink-2 hover:shadow-[0_12px_30px_-12px_rgb(29_29_31/0.6)]",
    light: "bg-white text-ink hover:bg-mist shadow-[0_1px_2px_rgb(16_24_40/0.06)]",
    ghost: "bg-transparent text-recall link rounded-none",
  };
  return (
    <button onClick={onClick} disabled={disabled}
      className={`press group inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-full font-medium disabled:cursor-not-allowed disabled:opacity-50 ${sizes[size]} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Segmented<T extends string>({ options, value, onChange, size = "md", tone = "mist", label }: {
  options: readonly T[] | { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md";
  tone?: "mist" | "white";
  label: string;
}) {
  const items = (options as (T | { value: T; label: string })[]).map((o) => (typeof o === "string" ? { value: o, label: o } : o));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const [pill, setPill] = useState<{ x: number; w: number } | null>(null);
  const index = items.findIndex((i) => i.value === value);

  useLayoutEffect(() => {
    const measure = () => {
      const el = refs.current[index];
      if (el) setPill({ x: el.offsetLeft, w: el.offsetWidth });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [index, items.length]);

  const pad = size === "sm" ? "px-3 py-1 text-[12px]" : "px-3.5 py-1 text-[13px] sm:px-4";
  return (
    <div role="tablist" aria-label={label}
      className={`relative inline-flex rounded-full p-1 ${tone === "mist" ? "bg-mist" : "bg-white shadow-[0_1px_2px_rgb(16_24_40/0.06)]"}`}>
      {pill && (
        <span aria-hidden className={`absolute bottom-1 top-1 left-0 rounded-full transition-[transform,width] duration-500 ease-[var(--ease-spring)] ${
          tone === "mist" ? "bg-white shadow-[0_1px_3px_rgb(16_24_40/0.12)]" : "bg-ink"}`}
          style={{ width: pill.w, transform: `translateX(${pill.x}px)` }} />
      )}
      {items.map((it, i) => (
        <button key={it.value} ref={(el) => { refs.current[i] = el; }} role="tab" aria-selected={it.value === value}
          onClick={() => onChange(it.value)}
          className={`press relative z-10 cursor-pointer rounded-full font-medium ${pad} ${
            it.value === value ? (tone === "white" ? "text-white" : "text-ink") : "text-muted hover:text-ink"}`}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

/** Needs a `relative overflow-hidden` parent. */
export function Aurora({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`aurora ${className}`}><i /><i /><i /></div>;
}

export function CountUp({ value, duration = 1400 }: { value: number | undefined; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(0);
  const [started, setStarted] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setStarted(true), { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  useEffect(() => {
    if (!started || value === undefined) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    let frame = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / duration);
      setShown(Math.round(value * (1 - Math.pow(1 - k, 3))));
      if (k < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [started, value, duration]);
  return <span ref={ref} className="tabular">{value === undefined ? "—" : shown.toLocaleString()}</span>;
}

export function Footer() {
  return (
    <footer className="border-t border-hair bg-mist">
      <div className="mx-auto max-w-[1080px] px-6 py-10 text-[12px] leading-relaxed text-muted">
        <p>
          MarketRecall publishes probabilistic estimates for research and educational purposes. Nothing here is investment
          advice, and past performance does not guarantee future results. Credits have no monetary value and cannot be bought or sold.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-hair pt-6">
          <span>Built for the Walrus × Tatum Total Recall hackathon. Memory on Walrus mainnet, data from Tatum.</span>
          <span>Covers SUI · WAL · CETUS</span>
        </div>
      </div>
    </footer>
  );
}
