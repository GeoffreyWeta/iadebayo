/* Vanilla progressive enhancements: mobile nav + staggered scroll reveals. */
(function () {
  var toggle = document.getElementById("nav-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var open = document.body.classList.toggle("nav-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Reveal-on-scroll with per-group stagger (respects reduced-motion via CSS)
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("is-visible"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12 });
    var counts = new Map();
    document.querySelectorAll(".reveal").forEach(function (el) {
      var idx = counts.get(el.parentElement) || 0;
      counts.set(el.parentElement, idx + 1);
      el.style.transitionDelay = Math.min(idx * 90, 450) + "ms";
      io.observe(el);
    });
    // heading underline draw
    var io2 = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("is-visible"); io2.unobserve(e.target); }
      });
    }, { threshold: 0.5 });
    document.querySelectorAll(".section-head").forEach(function (el) { io2.observe(el); });
  } else {
    document.querySelectorAll(".reveal, .section-head").forEach(function (el) { el.classList.add("is-visible"); });
  }

  // Gold spark badge: back to top
  var spark = document.getElementById("spark-top");
  if (spark) {
    window.addEventListener("scroll", function () {
      spark.classList.toggle("show", window.scrollY > 600);
    }, { passive: true });
    spark.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: "smooth" }); });
  }

  // Click-to-play video posters. Until someone presses play the page carries a
  // thumbnail instead of a YouTube iframe, which keeps six alumni videos on one
  // page affordable. See templates/includes/video_embed.html.
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

  // Auto-dismiss flash messages
  setTimeout(function () {
    document.querySelectorAll(".flash").forEach(function (f) {
      f.style.transition = "opacity .6s ease"; f.style.opacity = "0";
      setTimeout(function () { f.remove(); }, 700);
    });
  }, 6000);

  // ---------------------------------------------------------------- promo modal
  // The campaign flier (admin: Promo popups). Shown once per visitor per
  // version; closing it is remembered in localStorage under data-promo-key.
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
      document.body.classList.remove("promo-open");
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
      document.body.classList.add("promo-open");
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
