// The Cloudflare Email Worker (deploy/cloudflare-email-worker.mjs), run with
// a stand-in for Cloudflare's message object and for fetch.
import assert from "node:assert/strict";
import test from "node:test";

import worker from "../deploy/cloudflare-email-worker.mjs";

const RAW = "From: Ada <ada@example.com>\r\nTo: embark@iadebayo.foundation\r\nSubject: Hi\r\n\r\nHello\r\n";
const ENV = { INBOUND_URL: "https://site.test/hooks/email/", INBOUND_SECRET: "s3cret", RETRY_DELAY_MS: "0" };

function incoming() {
  return {
    from: "ada@example.com",
    to: "embark@iadebayo.foundation",
    raw: new Response(RAW).body,
    forwarded: [],
    rejected: null,
    async forward(address) { this.forwarded.push(address); },
    setReject(reason) { this.rejected = reason; },
  };
}

function withFetch(responses, run) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    const next = responses.shift();
    if (next instanceof Error) throw next;
    return new Response("{}", { status: next });
  };
  return run(calls).finally(() => { globalThis.fetch = original; });
}

test("posts the raw message with the secret and the envelope", () => withFetch([200], async (calls) => {
  const message = incoming();
  await worker.email(message, ENV);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, ENV.INBOUND_URL);
  assert.equal(calls[0].init.headers.Authorization, "Bearer s3cret");
  assert.equal(calls[0].init.headers["X-Envelope-To"], "embark@iadebayo.foundation");
  assert.equal(new TextDecoder().decode(calls[0].init.body), RAW);
  assert.equal(message.rejected, null);
}));

test("retries when the site is briefly down", () => withFetch([503, new Error("reset"), 200], async (calls) => {
  const message = incoming();
  await worker.email(message, ENV);
  assert.equal(calls.length, 3);
  assert.equal(message.rejected, null);
}));

test("a wrong secret is not retried, and the sender gets a bounce", () => withFetch([401, 200], async (calls) => {
  const message = incoming();
  await worker.email(message, ENV);
  assert.equal(calls.length, 1);
  assert.match(message.rejected, /Temporary problem/);
}));

test("a forwarded copy means a failed delivery is not bounced", () => withFetch([500, 500, 500], async () => {
  const message = incoming();
  await worker.email(message, { ...ENV, FORWARD_TO: "team@gmail.com, other@gmail.com" });
  assert.deepEqual(message.forwarded, ["team@gmail.com", "other@gmail.com"]);
  assert.equal(message.rejected, null);
}));

test("missing settings bounce rather than swallow mail", () => withFetch([], async (calls) => {
  const message = incoming();
  await worker.email(message, { INBOUND_URL: "" });
  assert.equal(calls.length, 0);
  assert.ok(message.rejected);
}));
