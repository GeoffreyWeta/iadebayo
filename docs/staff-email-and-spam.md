# Staff email and contact moderation

In Unfinished applications, select **Select all matching records across every
page**, then **Email selected**. The selection follows the search and filters.
The compose page pins the recipient IDs so new drafts cannot silently join it.
Completed applicants are checked again before each send. Missing addresses and
previously emailed applicants are shown; include previous recipients explicitly
only when a repeat message is intended.

Leave **Mark successfully sent recipients** checked to mark accepted sends as
followed up. This records provider acceptance, not delivery to the inbox.
Failed sends remain unmarked. With JavaScript, one explicit send processes one
recipient per request with progress and a stop control; keep the page open.
Without JavaScript, each submission sends at most ten recipients and offers the
remaining recipients to continue. After a connection interruption, check stamps
and provider logs before retrying, especially if repeat sending was enabled.

Contact message detail pages provide Block/Unblock sender controls. A block
applies to the normalized email address, stops new contact submissions and
marks existing messages reviewed without deleting records. Contact submissions
also reject duplicate message text from the same email within 24 hours and
limit accepted messages to three per email per rolling hour. These controls
do not identify a person who changes addresses and do not block a language.

Server operators can use `python manage.py block_contact_sender ADDRESS` and
the same command with `--unblock`. Run migrations before using these controls.

## Outgoing messages appearing in Spam

Provider acceptance is not proof of inbox delivery. Inspect an affected
message's Authentication-Results (SPF, DKIM, DMARC), the DKIM signing domain and
selector, Return-Path, and ZeptoMail's delivery log. Confirm the exact domain
verification records shown in the relevant ZeptoMail account; do not replace
existing DNS records or invent a DKIM selector.

On 2026-09-25, public DNS lookups returned no `_dmarc.iadebayo.foundation`
record and root SPF `v=spf1 include:_spf.mx.cloudflare.net ~all`. This is an
authentication finding, not a diagnosis of a particular message: ZeptoMail may
use a separate return-path for SPF and a DKIM signature for DMARC alignment.

References: https://support.google.com/mail/answer/81126 and
https://www.zoho.com/zeptomail/guide/email-deliverability.html.
