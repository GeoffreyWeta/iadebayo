/* A single explicit send starts sequential requests for the previewed recipients. */
(function () {
  "use strict";
  var form = document.querySelector("[data-bulk-email]");
  if (!form || !window.fetch || !window.FormData) return;
  var send = form.querySelector("[data-mail-send]");
  var stop = form.querySelector("[data-mail-stop]");
  var progress = form.querySelector("[data-mail-progress]");
  var again = form.querySelector("[name=again]");
  var count = form.querySelector("[data-recipient-count]");
  var running = false;
  var stopped = false;
  var completed = new Set();

  function recipients() {
    var selector = "[data-mail-recipient]";
    if (again && again.checked) selector += ", [data-mail-repeat]";
    return Array.from(new Set(Array.from(form.querySelectorAll(selector), function (input) {
      return input.value;
    }))).filter(function (pk) { return !completed.has(pk); });
  }

  function sync() {
    var total = recipients().length;
    count.textContent = total;
    send.textContent = "Send to " + total;
    send.disabled = running || total === 0;
  }
  if (again) again.addEventListener("change", sync);
  stop.addEventListener("click", function () { stopped = true; stop.disabled = true; });
  window.addEventListener("beforeunload", function (event) {
    if (running) { event.preventDefault(); event.returnValue = ""; }
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (running) return;
    var ids = recipients();
    if (!ids.length || !window.confirm("Send this message to " + ids.length + " recipients?")) return;
    var snapshot = new FormData(form);
    snapshot.delete("pks");
    snapshot.delete("all");
    snapshot.set("send", "1");
    snapshot.set("bulk_async", "1");
    var fields = Array.from(form.querySelectorAll("input, textarea, select"));
    var disabledBefore = fields.map(function (field) { return field.disabled; });
    fields.forEach(function (field) { field.disabled = true; });
    running = true;
    stopped = false;
    stop.hidden = false;
    stop.disabled = false;
    sync();
    var sent = 0, failed = 0, skipped = 0, processed = 0;
    var error = "";
    try {
      for (var pk of ids) {
        if (stopped) break;
        progress.textContent = "Sending " + (processed + 1) + " of " + ids.length + ". Keep this page open.";
        snapshot.set("pks", pk);
        var response = await fetch(form.action || window.location.href, {
          method: "POST", body: snapshot, credentials: "same-origin",
          headers: { "Accept": "application/json" }
        });
        if (!(response.headers.get("content-type") || "").includes("application/json")) {
          throw new Error("Sending stopped. Check the message fields and your connection, then reload to check recorded sends before retrying.");
        }
        var result = await response.json();
        if (!response.ok) {
          var details = Object.values(result.errors || {}).flat().map(function (item) { return item.message; }).join(" ");
          throw new Error((result.error || "Sending stopped.") + " " + details);
        }
        sent += result.sent;
        failed += result.failed;
        skipped += result.skipped;
        processed += 1;
        if (result.sent || result.skipped) completed.add(pk);
      }
    } catch (failure) {
      error = failure.message;
    } finally {
      running = false;
      fields.forEach(function (field, index) { field.disabled = disabledBefore[index]; });
      stop.hidden = true;
      progress.textContent = sent + " accepted by the email provider; " + failed + " failed; " + skipped + " skipped. " +
        (error || (stopped ? "Stopped. " : "")) +
        (recipients().length ? "Remaining recipients can be retried. Check delivery status before retrying an interrupted send." : "Sending complete. Inbox delivery is not confirmed.");
      sync();
    }
  });
  sync();
})();
