"""Cohort 5 dates, held as real dates.

Two places need the application period: the public schedule band on /embark/ and
/embark/apply/, and the "window" meter on the staff dashboard. It used to exist
only as the display string "1 August – 11 September 2026", which a dashboard
cannot do arithmetic on. Keeping the dates here and *deriving* the strings means
the band and the meter can never disagree about when applications close.

Rewritten each cohort — one edit here moves the public page and the dashboard.
"""
import datetime as dt

NAME = "Cohort 5"

APPLICATIONS_OPEN = dt.date(2026, 8, 1)
APPLICATIONS_CLOSE = dt.date(2026, 9, 11)
NOTIFY_FROM = dt.date(2026, 9, 14)
NOTIFY_TO = dt.date(2026, 9, 25)


def _span(start, end):
    """A date range with whatever the two ends share said only once.

    "1 August – 11 September 2026" when the months differ, "14 – 25 September
    2026" when they don't. Matches the strings the schedule band shipped with.
    """
    left = str(start.day)
    if (start.year, start.month) != (end.year, end.month):
        left += f" {start:%B}"
    if start.year != end.year:
        left += f" {start.year}"
    return f"{left} – {end.day} {end:%B} {end.year}"


def key_dates():
    """The (label, when) pairs the schedule band lists above the timeline."""
    return [
        ("Applications open", _span(APPLICATIONS_OPEN, APPLICATIONS_CLOSE)),
        ("Admission notifications", _span(NOTIFY_FROM, NOTIFY_TO)),
    ]


def window_progress(today=None):
    """How far through the application window we are.

    Returns None outside the window entirely (before it opens), so the meter can
    say "opens in N days" rather than drawing a 0% bar that looks like failure.
    `elapsed`/`total` count days inclusive of both ends — day one is 1/42, not
    0/42, which is what someone reading "day 4 of 42" expects.
    """
    today = today or dt.date.today()
    total = (APPLICATIONS_CLOSE - APPLICATIONS_OPEN).days + 1
    if today < APPLICATIONS_OPEN:
        return {"state": "upcoming", "total": total, "elapsed": 0,
                "remaining": total, "pct": 0,
                "days_until_open": (APPLICATIONS_OPEN - today).days}
    if today > APPLICATIONS_CLOSE:
        return {"state": "closed", "total": total, "elapsed": total,
                "remaining": 0, "pct": 100,
                "days_since_close": (today - APPLICATIONS_CLOSE).days}
    elapsed = (today - APPLICATIONS_OPEN).days + 1
    return {"state": "open", "total": total, "elapsed": elapsed,
            "remaining": total - elapsed,
            "pct": round(elapsed / total * 100)}
