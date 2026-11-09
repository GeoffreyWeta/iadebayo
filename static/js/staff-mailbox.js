/* Staff mailbox: size received-mail frames to their content, and stop a
   double click sending the same email twice.

   Everything here is an improvement on a page that already works without it:
   the frame has a fixed height and scrolls, and the send button posts. */
(function () {
  "use strict";

  function fit(frame) {
    try {
      var doc = frame.contentDocument;
      if (!doc || !doc.documentElement || !doc.body) return;
      // scrollHeight is never less than the frame's own height, so collapse
      // the frame first or a short message keeps the tall fallback height.
      frame.style.height = "1px";
      var height = doc.documentElement.scrollHeight;
      frame.style.height = (height > 1 ? height + 8 : 360) + "px";
    } catch (err) {
      /* Not readable (sandbox without same-origin): keep the CSS height. */
    }
  }

  document.querySelectorAll("[data-mail-frame]").forEach(function (frame) {
    frame.addEventListener("load", function () {
      fit(frame);
      // Images inside arrive after load and change the height again.
      try {
        frame.contentDocument.querySelectorAll("img").forEach(function (img) {
          img.addEventListener("load", function () { fit(frame); });
        });
      } catch (err) { /* see fit() */ }
    });
    fit(frame);
  });

  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      document.querySelectorAll("[data-mail-frame]").forEach(fit);
    }, 150);
  });

  document.querySelectorAll("[data-mail-send]").forEach(function (button) {
    var form = button.form;
    if (!form) return;
    var label = button.textContent;
    // Coming back with the Back button restores the page as it was left,
    // switched-off button included.
    window.addEventListener("pageshow", function () {
      button.disabled = false;
      button.textContent = label;
    });
    form.addEventListener("submit", function () {
      // Disabled after the browser has collected the form, so the click that
      // submitted it still counts; a second click finds it switched off.
      setTimeout(function () {
        button.disabled = true;
        button.textContent = "Sending…";
      }, 0);
    });
  });
})();
