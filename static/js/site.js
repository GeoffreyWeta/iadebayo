/* Vanilla progressive enhancements.

   Everything here is additive: with the script blocked the page is the same
   server-rendered document it always was. The one thing CSS needs to know is
   whether we ran at all — base.html sets `html.js` inline in <head>, and the
   v22 block in site.css unwinds every animation start state when that class
   is missing, so a failed script can never leave content invisible.

   Sections: mobile nav · header on scroll · scroll reveals · floating
   actions · video facades · flash messages · promo modal.
*/
(function () {
  "use strict";

  var root = document.documentElement;
  var body = document.body;
  var toggle = document.getElementById("nav-toggle");
  var nav = document.getElementById("main-nav");
  var spark = document.getElementById("spark-top");

  var MOBILE = "(max-width: 960px)";
  function isMobile() { return window.matchMedia(MOBILE).matches; }

  /* ==================================================== 1. mobile nav */
  /* The panel is a child of the sticky header, so opening it must also stop
     the header auto-hiding: a transformed header becomes the containing
     block for the fixed panel inside it and the panel would shrink to the
     bar. `.header-hidden:not(.nav-open)` in CSS guards the same thing. */

  function navIsOpen() { return body.classList.contains("nav-open"); }

  function focusables() {
    if (!nav) return [];
    return Array.prototype.filter.call(
      nav.querySelectorAll('a[href], button:not([disabled])'),
      function (el) { return el.offsetParent !== null || el.getClientRects().length; }
    );
  }

  function setNav(open) {
    if (navIsOpen() === open) return;
    var cameFromInside = nav && nav.contains(document.activeElement);
    body.classList.toggle("nav-open", open);
    if (toggle) {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    }
    if (open) {
      body.classList.remove("header-hidden");
      lastY = window.scrollY;                  // don't fire a hide on reopen
      var first = focusables()[0];
      if (first) first.focus({ preventScroll: true });
    } else if (toggle && cameFromInside) {
      // Focus was inside the panel we just hid; park it somewhere real.
      toggle.focus({ preventScroll: true });
    }
  }

  if (toggle && nav) {
    toggle.addEventListener("click", function () { setNav(!navIsOpen()); });

    // Any link tap closes the panel. Same-page anchors need the panel gone
    // before the scroll lands, or the target sits underneath it.
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a[href]")) setNav(false);
    });

    document.addEventListener("keydown", function (e) {
      if (!navIsOpen()) return;
      if (e.key === "Escape") { e.preventDefault(); setNav(false); return; }
      if (e.key !== "Tab") return;
      var items = focusables();
      if (!items.length) return;
      // Tab cycles: hamburger → panel links → hamburger. The hamburger is
      // part of the loop so the panel can always be closed from the keyboard.
      var first = items[0], last = items[items.length - 1];
      var here = document.activeElement;
      if (e.shiftKey) {
        if (here === first) { e.preventDefault(); toggle.focus(); }
        else if (here === toggle) { e.preventDefault(); last.focus(); }
      } else {
        if (here === last) { e.preventDefault(); toggle.focus(); }
        else if (here === toggle) { e.preventDefault(); first.focus(); }
      }
    });

    // Rotating a phone past the breakpoint would otherwise leave the body
    // scroll-locked with no visible panel.
    window.addEventListener("resize", function () {
      if (navIsOpen() && !isMobile()) setNav(false);
    });
  }

  /* ================================================ 2. header on scroll */

  var lastY = window.scrollY;
  var queued = false;

  function typing() {
    var el = document.activeElement;
    if (!el) return false;
    var tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  }

  function onScroll() {
    var y = window.scrollY;
    var scrollable = root.scrollHeight - window.innerHeight;
    root.style.setProperty("--scroll-progress", scrollable > 0 ? (y / scrollable).toFixed(4) : "0");
    body.classList.toggle("header-scrolled", y > 24);

    // Hide the bar on the way down, hand it back on the way up. Never while
    // the menu is open, never near the top, and never while a field is
    // focused (the soft keyboard fires spurious scroll events).
    if (!navIsOpen() && !typing()) {
      if (y > lastY + 6 && y > 180) body.classList.add("header-hidden");
      else if (y < lastY - 6) body.classList.remove("header-hidden");
    }

    if (spark) spark.classList.toggle("show", y > 520);
    body.classList.toggle("show-apply", y > 340);
    lastY = y;
  }

  window.addEventListener("scroll", function () {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { onScroll(); queued = false; });
  }, { passive: true });
  onScroll();

  /* ================================================= 3. scroll reveals */
  /* Two mechanisms, one observer:

       .reveal      — hand-placed in templates. Fades and rises, staggered
                      against its siblings.
       .stagger     — added here to lists and grids whose children carry no
                      .reveal of their own, so every page animates without
                      editing every template.

     Anything else in EFFECTS just gets `.is-visible` and lets CSS decide
     what that means (a rule drawing itself, a curtain lifting off a photo).
  */

  // Containers worth staggering — skipped when their children already reveal.
  // .faq-columns is excluded on purpose: its <details> already animate their
  // own panel open, and it is a multi-column container, which is the one
  // place stacking two effects on a fragmented child tends to misrender.
  var STAGGER = [
    ".impact-grid", ".ticklist", ".curriculum-list", ".chip-row",
    ".faq:not(.faq-columns)", ".card-grid", ".people-grid", ".post-grid",
    ".testimonial-grid", ".video-grid", ".gallery-grid",
    ".footer-col ul", ".social"
  ].join(",");

  // Elements whose CSS reacts to `.is-visible` on its own.
  var EFFECTS = [".section-head", ".schedule", ".media-frame", ".article-cover"].join(",");

  function inViewport(el) {
    var r = el.getBoundingClientRect();
    return r.top < window.innerHeight && r.bottom > 0;
  }

  var watch = [];

  document.querySelectorAll(STAGGER).forEach(function (el) {
    // Already animating from the template — a second layer would fight it.
    if (el.querySelector(":scope > .reveal")) return;
    if (el.classList.contains("reveal")) return;
    el.classList.add("stagger");
    // Deferred scripts can run after first paint. Anything already on screen
    // is marked visible in the same tick, so it is never painted hidden.
    if (inViewport(el)) el.classList.add("is-visible");
    else watch.push(el);
  });

  document.querySelectorAll(EFFECTS).forEach(function (el) { watch.push(el); });

  // Per-group stagger for hand-placed .reveal elements.
  var seen = new Map();
  document.querySelectorAll(".reveal").forEach(function (el) {
    var i = seen.get(el.parentElement) || 0;
    seen.set(el.parentElement, i + 1);
    el.style.setProperty("--rv-delay", Math.min(i * 85, 420) + "ms");
    watch.push(el);
  });

  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("is-visible");
        io.unobserve(e.target);
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -6% 0px" });
    watch.forEach(function (el) { io.observe(el); });
  } else {
    watch.forEach(function (el) { el.classList.add("is-visible"); });
  }

  /* ============================================== 4. floating actions */
  /* The apply pill and the back-to-top badge share the bottom-right corner
     on a phone. They fade out together over the footer, which already
     carries every link they offer and is where the newsletter field lives —
     a pill parked on top of the Subscribe button is the whole reason. */

  body.classList.add("js-float");

  if (spark) {
    spark.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  var footer = document.querySelector(".site-footer");
  if (footer && "IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      body.classList.toggle("near-footer", entries[0].isIntersecting);
    }, { rootMargin: "0px 0px -40px 0px" }).observe(footer);
  }

  /* ================================================= 5. video facades */
  /* Until someone presses play the page carries a thumbnail instead of a
     YouTube iframe, which keeps six alumni videos on one page affordable.
     See templates/includes/video_embed.html. */

  document.querySelectorAll("[data-video-facade]").forEach(function (box) {
    var trigger = box.querySelector(".video-facade");
    if (!trigger) return;
    trigger.addEventListener("click", function (event) {
      event.preventDefault();          // the href is the no-JS fallback
      var frame = document.createElement("iframe");
      frame.src = box.getAttribute("data-embed");
      frame.title = box.getAttribute("data-title") || "Video";
      frame.allow = "accelerometer; autoplay; encrypted-media; picture-in-picture";
      frame.allowFullscreen = true;
      frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      box.replaceChildren(frame);
      frame.focus();
    });
  });

  /* ================================================ 6. flash messages */

  setTimeout(function () {
    document.querySelectorAll(".flash").forEach(function (f) {
      f.style.transition = "opacity .5s ease, transform .5s ease";
      f.style.opacity = "0";
      f.style.transform = "translateY(-12px)";
      setTimeout(function () { f.remove(); }, 600);
    });
  }, 6000);

  /* =================================================== 7. promo modal */
  /* The campaign flier (admin: Promo popups). Shown once per visitor per
     version; closing it is remembered in localStorage under data-promo-key. */

  var promo = document.getElementById("promo-modal");
  if (promo) {
    var KEY = promo.getAttribute("data-promo-key");
    var dialog = promo.querySelector(".promo-dialog");
    var opener = null;

    // Private browsing and locked-down settings make localStorage throw on
    // access, not just on write. A visitor there should still see the flier
    // and still be able to close it — they just see it again next visit.
    function seen() {
      try { return window.localStorage.getItem(KEY) === "1"; } catch (e) { return false; }
    }
    function remember() {
      try { window.localStorage.setItem(KEY, "1"); } catch (e) { /* nothing to do */ }
    }

    function close() {
      remember();
      promo.classList.remove("is-open");
      body.classList.remove("promo-open");
      var done = function () {
        promo.hidden = true;
        promo.removeEventListener("transitionend", done);
      };
      promo.addEventListener("transitionend", done);
      setTimeout(done, 400);            // transitionend never fires if motion is reduced
      if (opener && opener.focus) opener.focus();
    }

    function open() {
      opener = document.activeElement;
      promo.hidden = false;
      body.classList.add("promo-open");
      // Next frame, so the browser paints the hidden state first and the
      // transition actually runs instead of being skipped.
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { promo.classList.add("is-open"); });
      });
      if (dialog) dialog.focus();
    }

    promo.querySelectorAll("[data-promo-close]").forEach(function (b) {
      b.addEventListener("click", close);
    });
    // Backdrop click, but not a click that started inside the dialog.
    promo.addEventListener("click", function (e) {
      if (e.target === promo) close();
    });
    document.addEventListener("keydown", function (e) {
      if (promo.hidden) return;
      if (e.key === "Escape") { close(); return; }
      if (e.key !== "Tab") return;
      // Keep Tab inside the dialog while it is modal.
      var focusable = promo.querySelectorAll("a[href], button:not([disabled])");
      if (!focusable.length) return;
      var first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });

    // Let the page land before interrupting it.
    if (!seen()) setTimeout(open, 1200);
  }
})();
