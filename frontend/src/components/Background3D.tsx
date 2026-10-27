import { useEffect, useRef } from "react";

type Ripple = { x: number; y: number; t0: number };

const COLS = 64;
const ROWS = 30;
const LENS = 150; // px radius of the cursor bump
const RIPPLE_LIFE = 2600;

/**
 * Perspective dot wave behind the landing page. Yaws toward the cursor, lifts and brightens dots under it,
 * sends a ripple on click and drifts forward on scroll. With no pointer (touch, idle) a slow virtual cursor
 * orbits instead. Paused when hidden, static for reduced motion.
 */
export function Background3D() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const fine = window.matchMedia("(pointer: fine)").matches;
    let w = 0, h = 0, dpr = 1, step = 33;
    let yaw = 0, pitch = 0;
    let px = -1e4, py = -1e4, aimX = -1e4, aimY = -1e4, lastMove = -1e9;
    let scroll = window.scrollY, drift = scroll;
    const ripples: Ripple[] = [];
    let frame = 0, last = 0;

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      w = window.innerWidth;
      h = window.innerHeight;
      step = fine && w >= 768 ? 16 : 33;
      el.width = Math.round(w * dpr);
      el.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (t: number) => {
      const time = t / 1000;
      if (t - lastMove > 3500) {
        aimX = w / 2 + Math.cos(time * 0.27) * w * 0.32;
        aimY = h * 0.68 + Math.sin(time * 0.41) * h * 0.14;
      }
      px = px < -1e3 ? aimX : px + (aimX - px) * 0.08;
      py = py < -1e3 ? aimY : py + (aimY - py) * 0.08;
      yaw += ((px / w - 0.5) * 0.36 - yaw) * 0.05;
      pitch += ((py / h - 0.5) * 0.08 - pitch) * 0.05;
      drift += (scroll - drift) * 0.06;

      ctx.clearRect(0, 0, w, h);
      const glow = ctx.createRadialGradient(px, py, 0, px, py, LENS * 1.8);
      glow.addColorStop(0, "rgb(47 107 255 / 0.10)");
      glow.addColorStop(1, "rgb(47 107 255 / 0)");
      ctx.fillStyle = glow;
      ctx.fillRect(px - LENS * 2, py - LENS * 2, LENS * 4, LENS * 4);

      for (let i = ripples.length - 1; i >= 0; i--) if (t - ripples[i].t0 > RIPPLE_LIFE) ripples.splice(i, 1);

      const fov = Math.min(w, 960) * 0.92;
      const horizon = h * (0.4 + pitch);
      const cos = Math.cos(yaw), sin = Math.sin(yaw);
      const travel = drift * 0.0035;
      const zc = 4;
      for (let r = 0; r < ROWS; r++) {
        const z0 = 1.2 + (r / (ROWS - 1)) * 6;
        const fade = 1 - r / ROWS;
        ctx.fillStyle = `rgb(${Math.round(47 + 77 * (1 - fade))}, ${Math.round(107 - 15 * (1 - fade))}, 255)`;
        for (let c = 0; c < COLS; c++) {
          const x0 = (c / (COLS - 1) - 0.5) * 10;
          const x = x0 * cos - (z0 - zc) * sin;
          const z = zc + x0 * sin + (z0 - zc) * cos;
          if (z < 0.7) continue;
          let y = Math.sin(x0 * 0.9 + time * 0.6) * 0.24 + Math.cos(z0 * 1.3 - time * 0.45 + travel) * 0.2;
          const sx = w / 2 + (x / z) * fov;
          if (sx < -20 || sx > w + 20) continue;
          let sy = horizon + ((1.25 - y) / z) * fov * 0.55;

          const dx = sx - px, dy = sy - py;
          const lens = Math.exp(-(dx * dx + dy * dy) / (2 * LENS * LENS));
          let wave = 0;
          for (const rp of ripples) {
            const age = t - rp.t0;
            const d = Math.hypot(sx - rp.x, sy - rp.y) - age * 0.55;
            wave += Math.sin(d * 0.045) * Math.exp(-(d * d) / 3600) * (1 - age / RIPPLE_LIFE);
          }
          y += lens * 0.55 + wave * 0.35;
          sy = horizon + ((1.25 - y) / z) * fov * 0.55;

          const size = Math.max(0.7, 2.8 / z) * (1 + lens * 1.1 + Math.abs(wave) * 0.6);
          const lift = (y + 0.4) / 0.8;
          ctx.globalAlpha = Math.min(0.95, (0.14 + 0.46 * fade) * (0.6 + 0.4 * lift) + lens * 0.45 + Math.abs(wave) * 0.3);
          ctx.fillRect(sx - size / 2, sy - size / 2, size, size);
        }
      }
      ctx.globalAlpha = 1;
    };

    const loop = (t: number) => {
      frame = requestAnimationFrame(loop);
      if (t - last < step) return;
      last = t;
      draw(t);
    };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      aimX = e.clientX;
      aimY = e.clientY;
      lastMove = performance.now();
    };
    const onDown = (e: PointerEvent) => {
      ripples.push({ x: e.clientX, y: e.clientY, t0: performance.now() });
      if (ripples.length > 4) ripples.shift();
    };
    const onScroll = () => { scroll = window.scrollY; };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden && !still) frame = requestAnimationFrame(loop);
    };

    resize();
    window.addEventListener("resize", resize);
    if (still) {
      draw(0);
    } else {
      window.addEventListener("pointermove", onMove, { passive: true });
      window.addEventListener("pointerdown", onDown, { passive: true });
      window.addEventListener("scroll", onScroll, { passive: true });
      document.addEventListener("visibilitychange", onVisibility);
      frame = requestAnimationFrame(loop);
    }
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("scroll", onScroll);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return <canvas ref={canvas} aria-hidden className="pointer-events-none fixed inset-0 -z-10 h-full w-full" />;
}
