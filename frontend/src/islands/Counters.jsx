import { useEffect } from "react";

/** Counts [data-count] numbers up from 0 when they scroll into view. */
export default function Counters({ host }) {
  useEffect(() => {
    const els = [...host.querySelectorAll("[data-count]")];
    if (els.length === 0) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        io.unobserve(entry.target);
        const el = entry.target;
        const target = parseInt(el.dataset.count, 10) || 0;
        if (reduced || target === 0) { el.textContent = el.textContent; return; }
        const dur = 1400;
        const t0 = performance.now();
        function tick(t) {
          const p = Math.min((t - t0) / dur, 1);
          el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3))).toLocaleString();
          if (p < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });
    }, { threshold: 0.4 });
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [host]);

  return null;
}
