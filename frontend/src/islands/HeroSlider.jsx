import { useEffect } from "react";

/**
 * Crossfades between .hero-slide elements already rendered by Django.
 * Slides declare their image via data-src; missing images are skipped,
 * so the branded gradient remains the graceful fallback.
 */
export default function HeroSlider({ host }) {
  useEffect(() => {
    const slides = [...host.querySelectorAll(".hero-slide")];
    if (slides.length === 0) return;

    // Load images; keep only the ones that exist.
    const usable = [];
    let pending = slides.length;
    slides.forEach((slide) => {
      const src = slide.dataset.src;
      const img = new Image();
      img.onload = () => { slide.style.backgroundImage = `url(${src})`; usable.push(slide); done(); };
      img.onerror = done;
      img.src = src;
      function done() { if (--pending === 0) start(); }
    });

    let timer;
    function start() {
      if (usable.length < 2) return; // nothing to rotate
      usable.sort((a, b) => slides.indexOf(a) - slides.indexOf(b));
      let i = usable.findIndex((s) => s.classList.contains("is-active"));
      if (i < 0) { i = 0; usable[0].classList.add("is-active"); }
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduced) return;
      timer = setInterval(() => {
        usable[i].classList.remove("is-active");
        i = (i + 1) % usable.length;
        usable[i].classList.add("is-active");
      }, 6000);
    }
    return () => clearInterval(timer);
  }, [host]);

  return null;
}
