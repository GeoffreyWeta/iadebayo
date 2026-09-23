"""The dates of the cohort currently being advertised, held as real dates.

Three places need the application period: the public schedule band on /embark/
and /embark/apply/, the "window" meter on the staff dashboard, and the "This
cohort" range preset in the analytics. It used to exist only as the display
string "1 August – 30 September 2026", which a dashboard cannot do arithmetic
on. Keeping the dates as dates and *deriving* the strings means the band and the
meter can never disagree about when applications close.

Where the dates live
--------------------
In the database, as a `core.Cohort` row the team edits at /staff/c/cohort/. The
module constants below are the fallback for when there is no row - a fresh
install, or a test database - and nothing else. They are not the source of
truth; `current()` is.

That change was the point of the staff area. A cohort's dates slipping by a week
is an ordinary thing that happens to a programme, and until this was a model it
meant editing Python and redeploying the site, which in practice meant the
schedule band said one thing and the team said another.

Read the dates through `current()`, never by importing the constants. The
fallbacks are deliberately named DEFAULT_* so that a call site reaching for them
directly reads as obviously wrong.
"""
import datetime as dt
from typing import NamedTuple

DEFAULT_NAME = "Cohort 5"
DEFAULT_APPLICATIONS_OPEN = dt.date(2026, 8, 1)
DEFAULT_APPLICATIONS_CLOSE = dt.date(2026, 9, 30)
DEFAULT_NOTIFY_FROM = dt.date(2026, 9, 25)
DEFAULT_NOTIFY_TO = dt.date(2026, 10, 7)


class Dates(NamedTuple):
    """One cohort's dates, whether they came from the database or the fallback."""
    name: str
    applications_open: dt.date
    applications_close: dt.date
    notify_from: dt.date
    notify_to: dt.date


FALLBACK = Dates(DEFAULT_NAME, DEFAULT_APPLICATIONS_OPEN, DEFAULT_APPLICATIONS_CLOSE,
                 DEFAULT_NOTIFY_FROM, DEFAULT_NOTIFY_TO)


def current():
    """The cohort being advertised, or the built-in dates if none is set.

    Deliberately tolerant of a database that cannot answer. This is called while
    rendering the public Embark page, and a missing table during a deploy - or
    the moment between `migrate` creating it and the team filling it in - should
    degrade to the shipped dates, not take the page down.
    """
    from django.db import DatabaseError

    from .models import Cohort
    try:
        row = Cohort.current()
    except DatabaseError:
        return FALLBACK
    if row is None:
        return FALLBACK
    return Dates(row.name, row.applications_open, row.applications_close,
                 row.notify_from, row.notify_to)


def _span(start, end):
    """A date range with whatever the two ends share said only once.

    "1 August – 30 September 2026" when the months differ, "14 – 25 September
    2026" when they don't. Matches the strings the schedule band shipped with.
    """
    left = str(start.day)
    if (start.year, start.month) != (end.year, end.month):
        left += f" {start:%B}"
    if start.year != end.year:
        left += f" {start.year}"
    return f"{left} – {end.day} {end:%B} {end.year}"


def key_dates(dates=None):
    """The (label, when) pairs the schedule band lists above the timeline."""
    d = dates or current()
    return [
        ("Applications open", _span(d.applications_open, d.applications_close)),
        ("Admission notifications", _span(d.notify_from, d.notify_to)),
    ]


def window_progress(today=None, dates=None):
    """How far through the application window we are.

    Returns a state of "upcoming" before the window opens, so the meter can say
    "opens in N days" rather than drawing a 0% bar that looks like failure.
    `elapsed`/`total` count days inclusive of both ends - day one is 1/42, not
    0/42, which is what someone reading "day 4 of 42" expects.
    """
    d = dates or current()
    today = today or dt.date.today()
    total = (d.applications_close - d.applications_open).days + 1
    if today < d.applications_open:
        return {"state": "upcoming", "total": total, "elapsed": 0,
                "remaining": total, "pct": 0,
                "days_until_open": (d.applications_open - today).days}
    if today > d.applications_close:
        return {"state": "closed", "total": total, "elapsed": total,
                "remaining": 0, "pct": 100,
                "days_since_close": (today - d.applications_close).days}
    elapsed = (today - d.applications_open).days + 1
    return {"state": "open", "total": total, "elapsed": elapsed,
            "remaining": total - elapsed,
            "pct": round(elapsed / total * 100)}
