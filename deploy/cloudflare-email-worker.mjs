/**
 * Cloudflare Email Worker for iadebayo.foundation.
 *
 * The domain's mail (MX) is Cloudflare Email Routing. This worker receives
 * each message Email Routing hands it and posts the raw email to the site,
 * which files it in the staff mailbox at /staff/mail/.
 *
 * Setup is in docs/staff-mailbox.md. Variables, under this worker's
 * Settings > Variables and Secrets:
 *
 *   INBOUND_URL     text    https://www.iadebayo.foundation/hooks/email/
 *   INBOUND_SECRET  secret  the MAIL_INBOUND_SECRET in the droplet's .env
 *   FORWARD_TO      text    optional: comma-separated addresses that also get
 *                           a copy. Each must be a verified destination
 *                           address in Email Routing.
 *
 * If the site cannot be reached after a few tries and no copy was forwarded,
 * the message is refused, so the sender's server tells them it bounced. A
 * message is never accepted and then silently dropped.
 */

const ATTEMPTS = 3;

export default {
  async email(message, env) {
    // Read once, up front, so the same bytes can be posted again on a retry.
    const raw = await new Response(message.raw).arrayBuffer();
    const forwarded = await forwardCopies(message, env);
    const delivered = await deliver(raw, message, env);
    if (!delivered && !forwarded) {
      message.setReject("Temporary problem receiving mail for this address. Please try again later.");
    }
  },
};

export async function forwardCopies(message, env) {
  const targets = String(env.FORWARD_TO || "")
    .split(",").map((s) => s.trim()).filter(Boolean);
  let forwarded = false;
  for (const address of targets) {
    try {
      await message.forward(address);
      forwarded = true;
    } catch (err) {
      console.error(`Forwarding a copy to ${address} failed: ${err}`);
    }
  }
  return forwarded;
}

export async function deliver(raw, message, env, fetchImpl = fetch) {
  if (!env.INBOUND_URL || !env.INBOUND_SECRET) {
    console.error("INBOUND_URL or INBOUND_SECRET is not set on this worker.");
    return false;
  }
  const delay = env.RETRY_DELAY_MS === undefined ? 2000 : Number(env.RETRY_DELAY_MS);
  for (let attempt = 1; attempt <= ATTEMPTS; attempt += 1) {
    try {
      const response = await fetchImpl(env.INBOUND_URL, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.INBOUND_SECRET}`,
          "Content-Type": "message/rfc822",
          "X-Envelope-From": message.from || "",
          "X-Envelope-To": message.to || "",
        },
        body: raw,
      });
      if (response.ok) return true;
      console.error(`Delivery attempt ${attempt}: HTTP ${response.status}`);
      // A wrong secret or an oversized message fails the same way every time.
      const permanent = response.status >= 400 && response.status < 500
        && response.status !== 408 && response.status !== 429;
      if (permanent) return false;
    } catch (err) {
      console.error(`Delivery attempt ${attempt}: ${err}`);
    }
    if (attempt < ATTEMPTS && delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay * attempt));
    }
  }
  return false;
}
