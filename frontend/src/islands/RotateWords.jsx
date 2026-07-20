import { useEffect, useState } from "react";

/**
 * Rotating headline word (seven30.co-style).
 *
 * Usage in a template:
 *   <span data-island="rotate-words"
 *         data-words="entrepreneurs.|innovators.|job creators.">entrepreneurs.</span>
 *
 * The server-rendered first word stays in the HTML for SEO; once React
 * mounts, it takes over and cycles through the list with a rise animation.
 */
export default function RotateWords({ host }) {
  const words = (host.dataset.words || "").split("|").filter(Boolean);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (words.length < 2) return;
    // Hide the original server-rendered text node (React renders its own).
    [...host.childNodes].forEach((n) => {
      if (n.nodeType === Node.TEXT_NODE) n.textContent = "";
    });
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;
    const t = setInterval(() => setIndex((i) => (i + 1) % words.length), 2600);
    return () => clearInterval(t);
  }, [host]);

  if (words.length === 0) return null;
  return (
    <span className="rw" key={index}>
      {words[index]}
    </span>
  );
}
