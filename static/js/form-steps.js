/* Multi-step form: one section at a time, a browser-local draft so an applicant
   can close the tab and come back, and — once they have left contact details —
   a quiet copy of the same draft on the server so the Foundation can reach the
   ones who never come back.

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
  var SKIP = { csrfmiddlewaretoken: 1, "g-recaptcha-response": 1, website_url: 1,
               draft_id: 1 };
  var storageKey = "iadebayo:draft:" + (form.dataset.draftKey || "form");

  // Replaced by the progress-capture block below when the form asks for it;
  // a no-op on every other form so the draft saver can call it unconditionally.
  var queueProgress = function () {};
  var progressIdKey = storageKey + ":id";

  /* ------------------------------------------------------------ stepping */

  // Land on the first section that came back with errors, else the first.
  var current = 0;
  for (var i = 0; i < steps.length; i++) {
    if (steps[i].dataset.hasErrors) { current = i; break; }
  }

  /* Restart the entrance animation on the section being revealed. The class
     has to come off and go back on with a reflow in between, or the browser
     sees no change and replays nothing. Skipped for the initial call — the
     page has its own entrance and does not need the form sliding too. */
  var settled = false;
  function animateIn(step, goingBack) {
    if (!settled) return;
    step.classList.remove("is-entering", "is-entering-back");
    void step.offsetWidth;
    step.classList.add(goingBack ? "is-entering-back" : "is-entering");
  }

  function show(index, focus) {
    var previous = current;
    current = Math.max(0, Math.min(index, steps.length - 1));
    steps.forEach(function (s, i) { s.hidden = i !== current; });
    animateIn(steps[current], current < previous);
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
    try {
      localStorage.removeItem(storageKey);
      // The draft id goes with it, so a second application (a later cohort, a
      // shared family laptop) starts its own row rather than overwriting the
      // one belonging to the application just sent.
      localStorage.removeItem(progressIdKey);
    } catch (err) { /* nothing to do */ }
  }

  // Don't overwrite a server round-trip: those values are more current.
  if (!form.querySelector("[data-has-errors]")) restoreDraft();

  var saveTimer;
  function queueSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 250);
    queueProgress();
  }
  form.addEventListener("input", queueSave);
  form.addEventListener("change", queueSave);
  if (draftNote) draftNote.hidden = false;

  /* ------------------------------------------- unfinished-application capture */
  /* Most people who open this form never reach the end of it, and the draft
     above only helps the ones who come back. So once the applicant has typed
     something we could actually contact them on, the same answers go to the
     server too — see submissions.models.PartialApplication for what is kept.

     Deliberately quiet: no spinner, no "saved" tick, nothing that could read as
     "your application is in". It is not. The only thing on screen that changes
     is the draft note under the buttons, which says so in plain words.

     The whole block is a no-op if the form carries no progress URL, so the
     other forms on the site are untouched. */
  (function progressCapture() {
    var url = form.dataset.progressUrl;
    if (!url) return;

    var emailField = form.querySelector('[name="email"]');
    var phoneField = form.querySelector('[name="phone"]');
    if (!emailField && !phoneField) return;

    var idKey = progressIdKey;
    var token = form.querySelector('[name="csrfmiddlewaretoken"]');
    var stamp = form.querySelector('input[name="draft_id"]');
    var lastSent = "";

    /* One id per browser, kept beside the local draft, so an applicant filling
       the form over three evenings updates one row instead of leaving three.
       randomUUID needs a secure context and is missing on older Androids —
       hence the fallback, which does not have to be cryptographic, only
       unlikely to collide. */
    function draftId() {
      var id;
      try { id = localStorage.getItem(idKey); } catch (err) { /* private mode */ }
      if (id) return id;
      if (window.crypto && window.crypto.randomUUID) {
        id = window.crypto.randomUUID();
      } else {
        id = "d" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      }
      try { localStorage.setItem(idKey, id); } catch (err) { /* fine, new id next time */ }
      return id;
    }

    // Same test the server applies, so we don't post rows it will refuse.
    function reachable() {
      var email = emailField ? emailField.value.trim() : "";
      var phone = phoneField ? phoneField.value.trim() : "";
      return (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)
              || phone.replace(/\D/g, "").length >= 7);
    }

    function payload() {
      var data = new FormData();
      data.append("draft_id", draftId());
      data.append("furthest_step", String(current + 1));
      if (token) data.append("csrfmiddlewaretoken", token.value);
      controls().forEach(function (el) {
        if ((el.type === "checkbox" || el.type === "radio") && !el.checked) return;
        if (el.value) data.append(el.name, el.value);
      });
      return data;
    }

    // Cheap fingerprint of what we last sent, so idle typing in one field does
    // not re-post the whole form every few seconds.
    function fingerprint(data) {
      var parts = [];
      data.forEach(function (value, key) {
        if (key !== "csrfmiddlewaretoken") parts.push(key + "=" + value);
      });
      return parts.join("&");
    }

    function send(leaving) {
      if (!reachable()) return;
      var data = payload();
      var print = fingerprint(data);
      if (print === lastSent) return;
      lastSent = print;
      // On the way out there is no time for a response — sendBeacon survives
      // the page going away, which is exactly the applicant we most want to
      // have captured.
      if (leaving && navigator.sendBeacon && navigator.sendBeacon(url, data)) return;
      // keepalive only on the way out: it caps the body at 64 KB, and a long
      // answer in every textarea can pass that on an ordinary mid-typing save.
      var options = { method: "POST", body: data, credentials: "same-origin" };
      if (leaving) options.keepalive = true;
      fetch(url, options)
        .catch(function () { lastSent = ""; });   // offline — try again next time
    }

    // Carried on the real submit too, so the server can mark this person's
    // unfinished row as finished instead of chasing them about it.
    if (stamp) stamp.value = draftId();

    var progressTimer;
    function queue() {
      clearTimeout(progressTimer);
      progressTimer = setTimeout(send, 3000);
    }
    queueProgress = queue;                 // hook the draft saver up to this

    // Moving between sections is the strongest signal we have that a chunk of
    // answers is settled, so don't wait out the timer for it.
    [btnNext, btnPrev].forEach(function (b) {
      b.addEventListener("click", function () { clearTimeout(progressTimer); send(false); });
    });
    // pagehide, not unload: unload is ignored on iOS Safari and blocks the
    // back-forward cache everywhere else.
    window.addEventListener("pagehide", function () {
      clearTimeout(progressTimer);
      send(true);
    });
  })();

  /* --------------------------------------------- country → region picker */
  /* Pick a country and the region field becomes that country's own list —
     37 states for Nigeria, 47 counties for Kenya, 9 provinces for South
     Africa — with the label renamed to the word that country actually uses.

     The `state` text input remains the only control that submits. A <select>
     with NO `name` sits in front of it and writes into it. Three things fall
     out of that, all of them the point:

       * Server-side validation does not change at all. `state` stays free
         text, so every legacy row, and every region ISO has never heard of,
         stays valid. A dropdown that could reject a real place name would be
         worse than the text box it replaced.
       * Nothing can ever submit two values for one field — the failure you get
         by naming the picker and forgetting to disable the input.
       * With this script off, or on a country we have no list for, the
         applicant just types, exactly as before.

     Runs after restoreDraft() on purpose: a restored or server-re-rendered
     value has to be reflected in the picker, not overwritten by it.

     Data: static/js/subdivisions.js — generated from ISO 3166-2, top-level
     subdivisions only, 66 countries. Anywhere else falls back to the text box.
  */
  (function regionPicker() {
    var countrySelect = form.querySelector("#id_country");
    var stateInput = form.querySelector("#id_state");
    var DATA = window.IADEBAYO_SUBDIVISIONS;
    if (!countrySelect || !stateInput || !DATA) return;

    // Sentinel for the escape-hatch option. Underscored, and deliberately not
    // something exotic like a control character: `select.value = x` resolves
    // silently to "" when nothing matches, so a sentinel that does not survive
    // a DOM round-trip reads as "they picked the blank option", not as a bug.
    var OTHER = "__other__";
    var label = form.querySelector('label[for="' + stateInput.id + '"]');
    var rawLabel = label ? label.textContent.trim() : "";
    var star = /\*\s*$/.test(rawLabel) ? " *" : "";
    var baseLabel = rawLabel.replace(/\s*\*\s*$/, "");
    var basePlaceholder = stateInput.placeholder;

    var picker = document.createElement("select");
    picker.className = "form-input form-select";
    picker.id = "id_state_picker";
    picker.hidden = true;
    stateInput.parentNode.insertBefore(picker, stateInput);

    function setLabel(text, forId) {
      if (!label) return;
      label.textContent = text + star;
      // Move `for` with the visible control, so clicking the label focuses
      // what the applicant can actually see.
      label.setAttribute("for", forId);
    }

    function fill(entry) {
      picker.textContent = "";
      picker.add(new Option("Select " + entry.label.toLowerCase() + "…", ""));
      entry.items.forEach(function (name) { picker.add(new Option(name, name)); });
      picker.add(new Option("Other / not listed", OTHER));
    }

    function showTextBox(placeholder) {
      stateInput.hidden = false;
      stateInput.placeholder = placeholder;
    }

    function sync(countryChanged) {
      var entry = DATA[countrySelect.value];

      if (!entry) {                       // no list for this country
        picker.hidden = true;
        showTextBox(basePlaceholder);
        setLabel(baseLabel, stateInput.id);
        return;
      }

      fill(entry);
      picker.hidden = false;
      setLabel(entry.label, picker.id);

      // Changing country invalidates whatever region was chosen for the old one.
      if (countryChanged) stateInput.value = "";
      var current = stateInput.value.trim();

      var options = picker.options;
      for (var i = 0; i < options.length; i++) {
        if (current && options[i].value === current) {
          picker.selectedIndex = i;
          stateInput.hidden = true;
          return;
        }
      }
      if (current) {                      // theirs is not on the list — keep it
        picker.value = OTHER;
        showTextBox("Your " + entry.label.toLowerCase());
      } else {
        picker.selectedIndex = 0;
        stateInput.hidden = true;
      }
    }

    picker.addEventListener("change", function () {
      var entry = DATA[countrySelect.value];
      if (picker.value === OTHER) {
        stateInput.value = "";
        showTextBox(entry ? "Your " + entry.label.toLowerCase() : basePlaceholder);
        stateInput.focus();
      } else {
        stateInput.hidden = true;
        stateInput.value = picker.value;
      }
      // Setting .value in script fires nothing, and the draft saver listens for
      // real events — tell it explicitly or the choice is not saved.
      form.dispatchEvent(new Event("change", { bubbles: true }));
    });

    countrySelect.addEventListener("change", function () { sync(true); });
    sync(false);
  })();

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
  settled = true;      // from here on, every move animates
})();
