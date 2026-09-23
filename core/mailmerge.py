"""Placeholders for the emails the team sends applicants by hand.

A template written in the staff area says "Dear {{ first_name }}," and this
turns that into "Dear Chidi,". That is the whole job.

Why not Django's template engine
--------------------------------
Because the text is typed into a textarea by a person who is writing an email,
not a program. Handing that to `Template(...).render()` would mean a stray
`{%` is a crash rather than a typo, and `{{ obj.applicant.user.password }}`
would be a reachable expression rather than nonsense. A flat dictionary and one
regex can do exactly one thing, which is the property worth having here: what
can appear in a sent email is enumerable by reading `FIELDS` below.

Unknown placeholders are an error, never silently blanked. `{{ frist_name }}`
blanked out reads as "Dear ," to the person receiving it, and nobody would have
noticed until it was sent. `unknown()` is checked when a template is saved and
again before anything goes out.
"""
import re

# `{{ name }}`, `{{name}}` - one lowercase identifier, nothing else. No dots, no
# filters, no tags: anything cleverer than a name is not a placeholder here.
TOKEN = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


def _first_name(full):
    """"Chidi" out of "Chidi Okafor", and "there" out of nothing.

    The fallback matters: an application with no name still has an email
    address, and "Dear ," is worse than "Dear there,".
    """
    first = (full or "").strip().split(" ")[0]
    return first or "there"


# name -> (what it means in the staff UI, how to get it off the submission).
# Adding a placeholder is one line here; it shows up in the help panel on the
# compose page automatically.
FIELDS = {
    "first_name": ("Their first name only, e.g. Chidi",
                   lambda o: _first_name(getattr(o, "name", ""))),
    "name": ("Their full name, as they typed it",
             lambda o: (getattr(o, "name", "") or "").strip()),
    "email": ("The address this message is going to",
              lambda o: getattr(o, "email", "") or ""),
    "business_name": ("Their business name",
                      lambda o: getattr(o, "business_name", "") or ""),
    "country": ("The country they applied from",
                lambda o: getattr(o, "country", "") or ""),
    "resume_link": ("Unfinished applications only: a private link back to their "
                    "own part-filled form. Expires after 45 days.",
                    lambda o: getattr(o, "resume_url", "")),
    "cohort": ("The cohort currently being advertised, e.g. Cohort 5",
               lambda o: _cohort().name),
    "notifications_from": ("First day of the notification window",
                           lambda o: _date(_cohort().notify_from)),
    "notifications_to": ("Last day of the notification window",
                         lambda o: _date(_cohort().notify_to)),
}


def _cohort():
    # Imported late: core.cohort reads the database, and importing it at module
    # scope would pull models in before the app registry is ready.
    from . import cohort
    return cohort.current()


def _date(value):
    return f"{value.day} {value:%B %Y}" if value else ""


def catalogue():
    """[(token, what it means)] for the help panel beside the compose box."""
    return [(f"{{{{ {name} }}}}", meaning) for name, (meaning, _) in FIELDS.items()]


def context_for(obj):
    """Every placeholder's value for one submission."""
    return {name: str(get(obj)) for name, (_, get) in FIELDS.items()}


def unknown(*texts):
    """Placeholder names used in `texts` that this module cannot fill.

    Sorted so the error message is stable, which matters because it is asserted
    on in the tests and read by a person fixing a typo.
    """
    used = set()
    for text in texts:
        used.update(TOKEN.findall(text or ""))
    return sorted(used - set(FIELDS))


def render(text, context):
    """Substitute every known placeholder. Unknown ones are left untouched.

    Left untouched rather than blanked because this is the last line of
    defence, not the check - `unknown()` is what refuses the send. If one ever
    does slip through, `{{ frist_name }}` sitting in the body is at least a
    thing a person can see went wrong.
    """
    return TOKEN.sub(
        lambda m: context.get(m.group(1), m.group(0)), text or "")
