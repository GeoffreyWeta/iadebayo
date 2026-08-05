/* ============================================================
   IADEBAYO Foundation — staff area enhancements

   Same contract as site.js: everything here is additive. The dashboard is fully
   drawn by the server (see core/analytics.py — geometry is computed in Python
   and rendered as inline SVG), so with this file blocked you lose the crosshair
   read-out, the count-up and the password toggle, and nothing else.

   Reveal animations are NOT here — they ride on site.js section 3, which the
   staff shell already loads.

   Sections: 1. password reveal · 2. plot crosshair + tooltip · 3. count-up
   ============================================================ */
(function () {
  "use strict";

  var REDUCED = window.matchMedia &&
                window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ============================================ 1. password reveal */
  /* Injected rather than shipped in the template: a "Show" button that cannot
     work is worse than no button, so it only exists once the script that drives
     it is running. */
  document.querySelectorAll("[data-password-wrap]").forEach(function (wrap) {
    var input = wrap.querySelector("input");
    if (!input) return;

    var button = document.createElement("button");
    button.type = "button";                     // never submit the form
    button.className = "staff-peek";
    button.textContent = "Show";
    button.setAttribute("aria-label", "Show password");
    wrap.appendChild(button);

    button.addEventListener("click", function () {
      var hidden = input.type === "password";
      input.type = hidden ? "text" : "password";
      button.textContent = hidden ? "Hide" : "Show";
      button.setAttribute("aria-label", (hidden ? "Hide" : "Show") + " password");
      // Keep the caret where the user left it — flipping `type` moves it to the
      // start in several browsers, which feels like the field was cleared.
      var end = input.value.length;
      input.focus();
      try { input.setSelectionRange(end, end); } catch (e) { /* number-ish inputs */ }
    });
  });

  /* ============================================ 2. plot crosshair + tooltip */
  document.querySelectorAll("[data-plot]").forEach(function (wrap) {
    var svg = wrap.querySelector("svg.plot");
    var tip = wrap.querySelector("[data-tip]");
    var cursor = wrap.querySelector(".plot-cursor");
    var focus = wrap.querySelector(".plot-focus");
    var crosshair = wrap.querySelector(".plot-crosshair");
    var hits = [].slice.call(wrap.querySelectorAll(".plot-hit"));
    if (!svg || !tip || !cursor || !hits.length) return;

    // The SVG scales to the column, so user units are not pixels. One ratio,
    // recomputed per pointer entry rather than per move — it only changes when
    // the column resizes, and reading offsetWidth on every mousemove is what
    // turns a hover into a layout thrash.
    var scale = 1;
    function measure() {
      var box = svg.getBoundingClientRect();
      var view = svg.viewBox.baseVal;
      scale = view && view.width ? box.width / view.width : 1;
    }

    function show(hit) {
      var x = parseFloat(hit.getAttribute("data-x"));
      var y = parseFloat(hit.getAttribute("data-y"));
      var value = hit.getAttribute("data-value");

      cursor.removeAttribute("hidden");
      crosshair.setAttribute("x1", x);
      crosshair.setAttribute("x2", x);
      focus.setAttribute("cx", x);
      focus.setAttribute("cy", y);

      tip.innerHTML = "";
      var strong = document.createElement("b");
      strong.textContent = value + (value === "1" ? " application" : " applications");
      var when = document.createElement("span");
      when.className = "plot-tip-date";
      when.textContent = hit.getAttribute("data-date");
      tip.appendChild(strong);
      tip.appendChild(when);

      // Position in CSS pixels, clamped so the tip never hangs off the card.
      var left = x * scale;
      var width = tip.offsetWidth || 120;
      var limit = svg.getBoundingClientRect().width;
      tip.style.left = Math.max(width / 2, Math.min(limit - width / 2, left)) + "px";
      tip.style.top = (y * scale) + "px";
      tip.removeAttribute("hidden");
    }

    function hide() {
      cursor.setAttribute("hidden", "");
      tip.setAttribute("hidden", "");
    }

    hits.forEach(function (hit) {
      hit.addEventListener("mouseenter", function () { show(hit); });
      // Touch: follow the finger along the chart rather than requiring a tap
      // per column, and let the page keep scrolling vertically.
      hit.addEventListener("touchstart", function () { measure(); show(hit); }, { passive: true });
    });
    svg.addEventListener("mouseenter", measure);
    svg.addEventListener("mouseleave", hide);
    svg.addEventListener("touchend", hide);
    window.addEventListener("resize", hide);
  });

  /* ============================================ 3. tile count-up */
  /* The final number is already in the HTML — this replaces it for the length of
     the animation only, so a failure here (or reduced motion, or no
     IntersectionObserver) leaves the correct figure on screen. */
  if (!REDUCED && "IntersectionObserver" in window) {
    var tiles = [].slice.call(document.querySelectorAll(".tile-value"));

    var countUp = function (el) {
      var target = parseInt(el.textContent.replace(/[^\d-]/g, ""), 10);
      if (!isFinite(target) || target <= 0) return;
      var DURATION = 900;
      var started = null;
      var final = el.textContent;

      function frame(now) {
        if (started === null) started = now;
        var t = Math.min((now - started) / DURATION, 1);
        // easeOutExpo, to match the CSS the bars animate with.
        var eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
        el.textContent = Math.round(target * eased);
        if (t < 1) requestAnimationFrame(frame);
        else el.textContent = final;          // restore any formatting verbatim
      }
      requestAnimationFrame(frame);
    };

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        countUp(e.target);
      });
    }, { threshold: 0.5 });
    tiles.forEach(function (el) { io.observe(el); });
  }
})();
