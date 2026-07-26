/* Multi-step form: one section at a time, plus a browser-local draft so an
   applicant can close the tab and come back.

   Progressive enhancement — with JS off, every fieldset is visible, Back/Next
   stay hidden, and the form submits in one go exactly as before. */
(function () {
  "use strict";

  var form = document.querySelector("form.form-steps");
  if (!form) return;

  var steps = Array.prototype.slice.call(form.querySelectorAll(".form-step"));
  if (steps.length < 2) return;

  var railItems = Array.prototype.slice.call(form.querySelectorAll(".step-rail-item"));
  var btnPrev = form.querySelector("[data-step-prev]");
  var btnNext = form.querySelector("[data-step-next]");
  var btnSubmit = form.querySelector("[data-step-submit]");
  var draftNote = form.querySelector(".form-draft-note");
  var SKIP = { csrfmiddlewaretoken: 1, "g-recaptcha-response": 1, website_url: 1 };
  var storageKey = "iadebayo:draft:" + (form.dataset.draftKey || "form");

  /* ------------------------------------------------------------ stepping */

  // Land on the first section that came back with errors, else the first.
  var current = 0;
  for (var i = 0; i < steps.length; i++) {
    if (steps[i].dataset.hasErrors) { current = i; break; }
  }

  function show(index, focus) {
    current = Math.max(0, Math.min(index, steps.length - 1));
    steps.forEach(function (s, i) { s.hidden = i !== current; });
    railItems.forEach(function (item, i) {
      item.classList.toggle("is-current", i === current);
      item.classList.toggle("is-done", i < current);
    });
    btnPrev.hidden = current === 0;
    btnNext.hidden = current === steps.length - 1;
    btnSubmit.hidden = current !== steps.length - 1;
    if (focus) {
      var legend = steps[current].querySelector(".form-step-title");
      if (legend) legend.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  /* Validate just the visible section. The form carries `novalidate` so the
     browser never blocks submit on its own; checkValidity() still reports. */
  function stepIsValid(step) {
    var firstBad = null;
    step.querySelectorAll(".form-error.is-live").forEach(function (n) { n.remove(); });

    step.querySelectorAll("input, select, textarea").forEach(function (el) {
      if (el.type === "hidden" || el.disabled) return;
      if (!el.checkValidity() && !firstBad) firstBad = el;
    });

    // Checkbox groups can't use the required attribute (it would demand every
    // box), so enforce "at least one" here.
    step.querySelectorAll('.form-field.is-choices[data-required="1"]').forEach(function (fieldEl) {
      var boxes = fieldEl.querySelectorAll('input[type="checkbox"]');
      if (!boxes.length) return;
      var anyChecked = Array.prototype.some.call(boxes, function (b) { return b.checked; });
      if (!anyChecked) {
        var msg = document.createElement("div");
        msg.className = "form-error is-live";
        msg.textContent = "Please tick at least one option.";
        fieldEl.appendChild(msg);
        if (!firstBad) firstBad = boxes[0];
      }
    });

    if (firstBad) {
      var wrap = firstBad.closest(".form-field");
      if (wrap) wrap.classList.add("has-error");
      firstBad.focus({ preventScroll: true });
      firstBad.scrollIntoView({ behavior: "smooth", block: "center" });
      if (typeof firstBad.reportValidity === "function") firstBad.reportValidity();
      return false;
    }
    return true;
  }

  btnNext.addEventListener("click", function () {
    if (stepIsValid(steps[current])) show(current + 1, true);
  });
  btnPrev.addEventListener("click", function () { show(current - 1, true); });

  railItems.forEach(function (item, index) {
    item.tabIndex = 0;
    item.setAttribute("role", "button");
    function go() {
      // Forward only through validated steps; back is always allowed.
      if (index <= current || stepIsValid(steps[current])) show(index, true);
    }
    item.addEventListener("click", go);
    item.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
    });
  });

  // Enter inside a text field should advance, not submit from step 1.
  form.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "textarea" || tag === "button") return;
    if (current < steps.length - 1) { e.preventDefault(); btnNext.click(); }
  });

  /* -------------------------------------------------------------- drafts */

  function controls() {
    return Array.prototype.filter.call(
      form.querySelectorAll("input, select, textarea"),
      function (el) { return el.name && !SKIP[el.name] && el.type !== "file"; });
  }

  function saveDraft() {
    var data = {};
    controls().forEach(function (el) {
      if (el.type === "checkbox" || el.type === "radio") {
        if (el.checked) (data[el.name] = data[el.name] || []).push(el.value);
      } else if (el.value) {
        data[el.name] = el.value;
      }
    });
    try {
      localStorage.setItem(storageKey, JSON.stringify({ saved: Date.now(), data: data }));
    } catch (err) { /* private mode / quota — drafting is a bonus, not a promise */ }
  }

  function restoreDraft() {
    var raw;
    try { raw = localStorage.getItem(storageKey); } catch (err) { return; }
    if (!raw) return;
    var data;
    try { data = JSON.parse(raw).data || {}; } catch (err) { return; }
    controls().forEach(function (el) {
      var stored = data[el.name];
      if (stored === undefined) return;
      if (el.type === "checkbox" || el.type === "radio") {
        if (Array.isArray(stored) && stored.indexOf(el.value) !== -1) el.checked = true;
      } else if (!el.value) {
        el.value = stored;
      }
    });
  }

  function clearDraft() {
    try { localStorage.removeItem(storageKey); } catch (err) { /* nothing to do */ }
  }

  // Don't overwrite a server round-trip: those values are more current.
  if (!form.querySelector("[data-has-errors]")) restoreDraft();

  var saveTimer;
  function queueSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 250);
  }
  form.addEventListener("input", queueSave);
  form.addEventListener("change", queueSave);
  if (draftNote) draftNote.hidden = false;

  /* ------------------------------------------------------------- submit */

  form.addEventListener("submit", function (e) {
    // Answers on a hidden step can be wrong too — check every section and
    // jump to the first that fails rather than round-tripping to the server.
    for (var i = 0; i < steps.length; i++) {
      var wasHidden = steps[i].hidden;
      steps[i].hidden = false;
      var ok = stepIsValid(steps[i]);
      steps[i].hidden = wasHidden;
      if (!ok) {
        e.preventDefault();
        show(i, true);
        stepIsValid(steps[i]);   // re-run now it's visible, to focus + message
        return;
      }
    }
    clearTimeout(saveTimer);
    clearDraft();
  });

  show(current, false);
})();
