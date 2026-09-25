/* ============================================================
   IADEBAYO Foundation - staff area, management enhancements

   Same contract as site.js and staff.js: everything here is additive, and the
   pages work with this file blocked. That is not a slogan, it is the reason the
   markup looks the way it does -

     · the on/off switches in a list are <form>s with a submit button, not
       checkboxes this file has to post;
     · reordering has ▲▼ submit buttons, and the drag handler below is a
       shortcut on top of them (native drag-and-drop has no touch equivalent, so
       on a phone the buttons are not a fallback - they are the mechanism);
     · the filter bar has an Apply button, so the selects are never controls
       that appear to do nothing;
     · the nav rail is a <details>, which opens without any script at all.

   Blocked, you lose: filter auto-submit, the bulk-selection counter, the
   confirm prompts, the picked-file preview, slug suggestions, drag-to-reorder,
   and the warning about leaving a half-typed form. Nothing else.

   Sections: 1. filters · 2. bulk selection · 3. confirms · 4. file preview
             5. slug suggestion · 6. drag to reorder · 7. unsaved changes
   ============================================================ */
(function () {
  "use strict";

  // Native details remains usable when JavaScript is unavailable.
  var rail = document.querySelector(".staff-rail");
  if (rail && window.matchMedia) {
    var narrow = window.matchMedia("(max-width: 1000px)");
    var syncRail = function () { rail.open = !narrow.matches; };
    syncRail();
    narrow.addEventListener("change", syncRail);
  }


  /* ============================================ 1. filter auto-submit */
  document.querySelectorAll("[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () {
      var form = select.form;
      if (!form) return;
      // Drop the page number: page 4 of the old filter is rarely a page of the
      // new one, and landing on an empty page reads as "no results".
      var page = form.querySelector("[name=page]");
      if (page) page.remove();
      form.submit();
    });
  });

  /* ============================================ 2. bulk selection */
  var bulkBar = document.querySelector("[data-bulk-bar]");
  if (bulkBar) {
    var note = bulkBar.querySelector("[data-bulk-count]");
    var actions = [].slice.call(bulkBar.querySelectorAll("button"));
    var boxes = [].slice.call(document.querySelectorAll("input[name=pks]"));
    var all = document.querySelector("[data-check-all]");
    var matching = bulkBar.querySelector("[data-select-matching]");

    var sync = function () {
      var acrossPages = matching && matching.checked;
      var picked = acrossPages ? Number(matching.dataset.count) : boxes.filter(function (b) { return b.checked; }).length;
      bulkBar.classList.toggle("has-picked", picked > 0);
      if (note) {
        note.textContent = acrossPages ? "All " + picked + " matching records selected" : picked
          ? picked + (picked === 1 ? " row selected" : " rows selected")
          : "Tick rows to act on them";
      }
      // Disabled rather than hidden: the buttons stay where they were, so the
      // bar does not reflow under the pointer as rows are ticked.
      actions.forEach(function (b) { b.disabled = picked === 0; });
      if (all) {
        all.checked = acrossPages || (picked > 0 && picked === boxes.length);
        all.indeterminate = !acrossPages && picked > 0 && picked < boxes.length;
      }
      boxes.forEach(function (b) { b.disabled = !!acrossPages; });
    };

    boxes.forEach(function (b) { b.addEventListener("change", sync); });
    if (matching) matching.addEventListener("change", sync);
    if (all) {
      all.addEventListener("change", function () {
        if (matching) matching.checked = false;
        boxes.forEach(function (b) { b.checked = all.checked; });
        sync();
      });
    }
    sync();
  }

  /* ============================================ 3. confirm before destroying */
  /* Only on the bulk delete. Deleting one row already goes through a
     confirmation *page* that shows what is about to go - a browser dialog on
     top of that would be a second "are you sure" with less information in it. */
  document.querySelectorAll("[data-confirm]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      if (!window.confirm(button.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  /* ============================================ 4. picked-file preview */
  /* "flier-final-v3.png" tells you nothing about which flier that is. Show the
     image the moment it is chosen, before the upload is committed. */
  document.querySelectorAll("input[data-file-preview]").forEach(function (input) {
    input.addEventListener("change", function () {
      var existing = input.parentNode.querySelector(".field-preview");
      if (existing) existing.remove();

      var file = input.files && input.files[0];
      if (!file) return;

      var box = document.createElement("p");
      box.className = "field-preview";

      if (/^image\//.test(file.type)) {
        var img = document.createElement("img");
        img.alt = "";
        img.src = URL.createObjectURL(file);
        // Freed once the browser has decoded it; without this every re-pick
        // leaks another copy of the file for the life of the page.
        img.onload = function () { URL.revokeObjectURL(img.src); };
        box.appendChild(img);
      }

      var label = document.createElement("span");
      label.textContent = "New: " + file.name +
        " (" + Math.max(1, Math.round(file.size / 1024)) + " KB) - not saved yet";
      box.appendChild(label);
      input.parentNode.appendChild(box);
    });
  });

  /* ============================================ 5. slug suggestion */
  document.querySelectorAll("input[data-slug-from]").forEach(function (slug) {
    var source = document.getElementById("id_" + slug.getAttribute("data-slug-from"));
    if (!source) return;

    // Never touch a slug someone typed, and never touch one that already has a
    // value - a published post's URL is a promise to everyone who linked to it.
    var auto = slug.value === "";
    slug.addEventListener("input", function () { auto = false; });

    source.addEventListener("input", function () {
      if (!auto) return;
      slug.value = source.value
        .toLowerCase()
        .normalize("NFKD").replace(/[\u0300-\u036f]/g, "")   // strip accents
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 220);
    });
  });

  /* ============================================ 6. drag to reorder */
  var table = document.querySelector("table[data-reorder]");
  var orderForm = document.getElementById("orderform");
  if (table && orderForm) {
    var body = table.querySelector("tbody");
    var carried = null;

    // The row is only draggable while the handle is held. Making the whole <tr>
    // permanently draggable turns every attempt to select a name in the table
    // into a drag.
    table.querySelectorAll("[data-grip]").forEach(function (grip) {
      var row = grip.closest("tr");
      grip.addEventListener("mousedown", function () { row.draggable = true; });
      row.addEventListener("dragend", function () { row.draggable = false; });
    });

    body.addEventListener("dragstart", function (event) {
      carried = event.target.closest("tr");
      if (!carried) return;
      carried.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
      // Firefox will not start a drag without data on the transfer.
      try { event.dataTransfer.setData("text/plain", carried.dataset.pk); } catch (e) {}
    });

    body.addEventListener("dragover", function (event) {
      if (!carried) return;
      event.preventDefault();
      var over = event.target.closest("tr");
      if (!over || over === carried) return;

      body.querySelectorAll(".is-over").forEach(function (r) { r.classList.remove("is-over"); });
      over.classList.add("is-over");

      // Past the midpoint means below it, which is what makes dragging to the
      // last position possible at all.
      var box = over.getBoundingClientRect();
      var below = event.clientY > box.top + box.height / 2;
      body.insertBefore(carried, below ? over.nextSibling : over);
    });

    body.addEventListener("drop", function (event) { event.preventDefault(); });

    body.addEventListener("dragend", function () {
      if (!carried) return;
      carried.classList.remove("is-dragging");
      body.querySelectorAll(".is-over").forEach(function (r) { r.classList.remove("is-over"); });
      carried = null;

      // Post the order the rows are in now. The server renumbers from that list
      // and redirects back, so the page ends up showing what the database
      // actually holds rather than what the DOM was left looking like.
      orderForm.querySelectorAll("input[name=ids]").forEach(function (i) { i.remove(); });
      body.querySelectorAll("tr[data-pk]").forEach(function (row) {
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = "ids";
        input.value = row.dataset.pk;
        orderForm.appendChild(input);
      });
      orderForm.submit();
    });
  }

  /* ============================================ 7. unsaved changes */
  /* Someone types three paragraphs of an alumni story and clicks a nav link.
     The browser's own dialog is the only thing that can stop that. Armed only
     once something has actually changed, and disarmed on submit, so it never
     fires on a form nobody touched. */
  var editForm = document.querySelector(".edit-form");
  if (editForm) {
    var dirty = false;
    editForm.addEventListener("input", function () { dirty = true; });
    editForm.addEventListener("change", function () { dirty = true; });
    editForm.addEventListener("submit", function () { dirty = false; });
    window.addEventListener("beforeunload", function (event) {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";               // required by older browsers
    });
  }
})();
