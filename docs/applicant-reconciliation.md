# Applicant reconciliation

The unfinished staff list, its CSV export, admin list/export, dashboard counts,
and sector/country summary use the same queue:

- Exclude drafts marked completed.
- Exclude drafts whose trimmed, lowercase email matches a submitted application
  or another completed draft, including historical records with missing stamps.
- Keep the most recently updated open draft per email (highest ID breaks ties).
- Keep email-less drafts separately. They are not verified unique people.

Sector comes from the latest draft's answers. Missing sectors/countries appear
as "Not provided". The country field is self-reported location; it does not
establish nationality or country of birth. Summaries cover the full filtered
queue, not just the current page. Both CSV exports include a sector column.

Previously, only browser draft IDs were unique. Submitted applications could
reuse an email. The public form now normalizes email and checks legacy submissions;
a unique email reservation also prevents two prevalidated submissions saving twice.
Migration 0013 reserves existing emails without merging or deleting applications.
Different email addresses can still belong to one person. Names and phone numbers
are not used as automatic identity proofs. This is site-wide: applications currently
have no cohort association, so accepting repeat applications for a future cohort
will require an explicit cohort-specific identity rule.

## Deployment and live analysis

Deploy the code and run `python manage.py migrate` before accepting submissions.
Then run this read-only command against the live database:

```sh
python manage.py audit_applicants
```

It reports raw submissions, distinct normalized emails, duplicate email groups,
extra rows sharing emails, missing emails, and the unfinished sector/country
breakdown. It outputs no names or contact details and sends no messages.
Compare `submitted_unique_emails` with the reported 248; do not replace actual
counts with that number without reconciling the same export/date range.

The local database inspected during this change contains 2 submissions and no
drafts. It cannot substantiate the live total or an unfinished-applicant analysis.
Existing duplicate submissions remain available for staff review; the completed
application table and its analytics still count stored submissions.
