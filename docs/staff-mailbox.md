# Staff mailbox

`/staff/mail/` is the team's shared mailbox. Staff can write to any address,
read what comes back, and reply in the same conversation. Messages sent from
the applicant screens are filed here too: a decision email, a nudge, or a bulk
send. An applicant's reply therefore lands next to the message it answers. Each
application page lists the conversations held with that applicant's address.

## How mail moves

    Sending:    staff page -> Django -> ZeptoMail HTTPS API -> recipient
    Receiving:  sender -> Cloudflare Email Routing (the domain's MX)
                       -> Email Worker -> POST /hooks/email/ -> mailroom app

Sending needs nothing new. It uses the existing `EMAIL_BACKEND=zeptomail`
setup. Receiving needs the three steps below. Until they are done, the inbox
shows a notice and nothing arrives in it. Sending still works.

## Switching receiving on

1. **Secret.** On the droplet, generate a secret:

       python3 -c "import secrets; print(secrets.token_urlsafe(32))"

   Add `MAIL_INBOUND_SECRET=<that value>` to `/srv/iadebayo/.env`. The file
   must stay owned by `deploy`. Then run `sudo systemctl restart iadebayo`.
   Type the value in. Do not paste a multi-line block, because a placeholder
   left in `.env` fails in exactly the way a wrong secret does.

2. **Worker.** In Cloudflare, go to Workers & Pages, choose Create, and create
   a Worker named, for example, `iadebayo-inbound-mail`. Replace its code with
   [deploy/cloudflare-email-worker.mjs](../deploy/cloudflare-email-worker.mjs)
   and deploy it. Under the Worker's Settings, open Variables and Secrets and
   add:
   - `INBOUND_URL` (text): `https://www.iadebayo.foundation/hooks/email/`.
     Its host must be in `DJANGO_ALLOWED_HOSTS`.
   - `INBOUND_SECRET` (secret): the same value as `MAIL_INBOUND_SECRET`.
   - `FORWARD_TO` (text, optional): addresses that should still get a copy
     of every message, comma-separated, such as the Gmail inbox mail is
     forwarded to today. Each one must be a verified destination address in
     Email Routing.

3. **Routes.** In the domain's Email, open Email Routing and then Routing
   rules. Change the action for `embark@` and `hello@` to "Send to a Worker"
   and pick the Worker. Do the same for any other address the team answers.
   Pointing the catch-all address at the Worker is an option. This replaces
   the rule's current "Send to an email" action, so set `FORWARD_TO` first if
   people should keep receiving copies in Gmail.

**Test.** Send an email from a personal account to `embark@`. It should appear
in `/staff/mail/` within seconds. Reply to it from there, then reply again from
the personal account. The second reply must join the same conversation. If
nothing arrives, check the Worker's logs first. A `401` there means the two
secrets differ. The site logs `Received email could not be stored` when it
failed on its side.

Cloudflare does not document whether `message.forward()` still works after the
Worker has read the raw message, which this Worker does. If `FORWARD_TO` is
set, confirm the copy also reaches Gmail during the test.

## What staff can do

- **Folders.** Inbox, Sent, Archived, Junk, All mail. Read and unread are
  shared by the whole team: opening a conversation marks it read for everyone.
- **Write.** Send from any address in `STAFF_MAILBOXES`, with To, Cc, Bcc and
  attachments (10 MB in total). Email templates can be loaded. Placeholders
  are filled in only when the message goes to one person the site has a
  record for. Otherwise the send stops rather than mailing `{{ first_name }}`.
- **Reply.** By default a reply goes to the sender, or to their Reply-To, with
  everyone else from their message in Cc. All of these fields can be edited.
  Their message is quoted below the reply.
- **Junk and block.** A new conversation whose sender fails DMARC goes to Junk.
  So does mail from a blocked sender. "Block sender" uses the same block list
  as the contact form, so it stops both. Nothing is deleted.

A failed send records nothing and keeps the text in the box. A successful
send is filed even when it was made from the applicant screens.

## How replies find their conversation

A reply is matched in this order:

1. its `In-Reply-To` or `References` header names a message the mailbox holds;
2. otherwise, the same subject (ignoring Re:/Fwd:) from an address already on
   the conversation, within the last 120 days.

The second rule is the one that matters for mail sent through ZeptoMail.
ZeptoMail sets its own Message-ID and does not report it back, so a reply to
it names an ID the site never saw. A reply that changes the subject *and*
comes from a different address starts a new conversation.

Replies sent from here carry `In-Reply-To` and `References`, so they thread in
the recipient's mail app. ZeptoMail does not document whether it accepts
these headers. If it refuses them, the message is sent again without them, and
the log records `ZeptoMail refused the threading headers`.

## Storage and privacy

Received messages are stored in `private/mail/` under the project directory,
or in `MAIL_FILES_ROOT` if that is set. Each message's original `.eml` is kept
along with its attachments. That directory is outside `/media/` on purpose,
because nginx serves `/media/` to anyone. Include it in backups next to the
database. Files are served only through staff-only views. HTML and other
active file types are always downloaded rather than opened.

Received HTML is shown in a sandboxed frame. Scripts and forms cannot run in
it, and remote images are blocked until someone presses "Show images" on that
message. Blocked images also stop senders from tracking when an email was
opened.

## Without the Worker

`python manage.py receive_email message.eml` files a saved message exactly as
the webhook would, and keeps its original date. Running it twice on the same
message is harmless. Use it to try the inbox locally, or to bring in mail that
arrived before receiving was switched on. In Gmail, open the message, then use
⋮ and "Download message".
