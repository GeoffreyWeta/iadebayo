/**
 * React islands — small interactive widgets mounted onto server-rendered
 * Django pages (SEO stays intact; React only enhances).
 *
 *   <section data-island="hero-slider">  → crossfading hero background
 *   <div data-island="counters">         → count-up impact numbers
 */
import { createRoot } from "react-dom/client";
import HeroSlider from "./islands/HeroSlider.jsx";
import Counters from "./islands/Counters.jsx";
import RotateWords from "./islands/RotateWords.jsx";

const ISLANDS = { "hero-slider": HeroSlider, counters: Counters, "rotate-words": RotateWords };

document.querySelectorAll("[data-island]").forEach((el) => {
  const Component = ISLANDS[el.dataset.island];
  if (!Component) return;
  const mount = document.createElement(el.tagName === "SPAN" ? "span" : "div");
  mount.style.display = "contents";
  el.appendChild(mount);
  createRoot(mount).render(<Component host={el} />);
});
