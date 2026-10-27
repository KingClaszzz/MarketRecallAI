import { useEffect, useRef } from "react";

const INTERACTIVE = "a, button, [role=tab], input, textarea, label, summary";

/** Ring that trails the cursor. Not rendered on touch screens or with reduced motion. */
export function CursorFollower() {
  const ring = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ring.current;
    if (!el) return;
    const fine = window.matchMedia("(pointer: fine)").matches;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!fine || still) return;

    let x = -100, y = -100, tx = -100, ty = -100, scale = 1, aimScale = 1;
    let frame = 0;
    const tick = () => {
      x += (tx - x) * 0.2;
      y += (ty - y) * 0.2;
      scale += (aimScale - scale) * 0.2;
      el.style.transform = `translate3d(${x - 16}px, ${y - 16}px, 0) scale(${scale})`;
      frame = requestAnimationFrame(tick);
    };
    const onMove = (e: PointerEvent) => {
      tx = e.clientX;
      ty = e.clientY;
      el.style.opacity = "1";
      const target = e.target as Element | null;
      const hot = !!target?.closest?.(INTERACTIVE);
      aimScale = hot ? 1.7 : 1;
      el.dataset.hot = hot ? "1" : "";
    };
    const onLeave = () => { el.style.opacity = "0"; };
    const onDown = () => { aimScale *= 0.8; };
    const onUp = () => { aimScale /= 0.8; };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointerup", onUp);
    };
  }, []);

  return <div ref={ring} aria-hidden className="cursor-ring" />;
}
