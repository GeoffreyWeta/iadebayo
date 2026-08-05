"""What the staff dashboard shows, computed from the submission tables.

Nothing here touches the request. Every function takes a queryset or a date
window and returns plain dicts, which is what makes the numbers testable without
going through a view, and what lets the template stay declarative — it renders
geometry it is handed rather than doing arithmetic in `{% %}`.

Two deliberate choices worth knowing about:

  * **Chart geometry is computed here, in Python, and rendered as inline SVG.**
    The dashboard therefore draws with JavaScript blocked, same as the rest of
    this site (see the header of site.js). staff.js only adds hover read-out.

  * **Percentages are of the answered rows, not of all rows.** Every applicant
    field except name/email/phone/city/country/business is blank-able, because
    the 2025 form was shorter and those applications still have to be readable.
    A "62% female" that silently counted 40 blank genders as male would be a lie,
    so each breakdown carries its own `answered` count and says so.
"""
import datetime as dt
from collections import Counter

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from submissions.models import (ContactMessage, EmbarkApplication,
                                FacultyApplication, NewsletterSubscriber,
                                PartnershipInquiry, VolunteerApplication)

from . import cohort

# The submission tables the "enquiries" tiles and the pipeline list cover, in the
# order the dashboard shows them. Kept as data so adding a seventh form is one
# line here rather than an edit in three templates.
FORM_SOURCES = [
    ("applications", "Embark applications", EmbarkApplication, "core:apply"),
    ("faculty", "Faculty & mentors", FacultyApplication, "core:join_faculty"),
    ("volunteers", "Volunteers", VolunteerApplication, "core:volunteer"),
    ("partners", "Partnership inquiries", PartnershipInquiry, "core:partner"),
    ("contact", "Contact messages", ContactMessage, "core:contact"),
    ("newsletter", "Newsletter sign-ups", NewsletterSubscriber, None),
]

# Selectable windows. `days=None` means "everything", which is the honest default
# for a foundation whose first cohort predates the dashboard.
RANGES = {
    "30": ("Last 30 days", 30),
    "90": ("Last 90 days", 90),
    "cohort": ("This application window", None),
    "all": ("All time", None),
}
DEFAULT_RANGE = "cohort"


# --------------------------------------------------------------- window helpers
def resolve_range(key, today=None):
    """Turn a `?range=` value into (key, label, start_date, end_date).

    `start`/`end` are dates or None for open-ended. An unknown key falls back to
    the default rather than 400-ing: this is a querystring a staffer can edit in
    the address bar, and a typo should not be an error page.
    """
    today = today or timezone.localdate()
    if key not in RANGES:
        key = DEFAULT_RANGE
    label, days = RANGES[key][0], RANGES[key][1]
    if key == "cohort":
        return key, label, cohort.APPLICATIONS_OPEN, cohort.APPLICATIONS_CLOSE
    if days:
        return key, label, today - dt.timedelta(days=days - 1), today
    return key, label, None, None


def in_window(qs, start, end):
    """Filter on created_at using dates, inclusive at both ends.

    `__date__gte`/`__lte` rather than a datetime range so the boundary means the
    whole local day. With USE_TZ on, comparing a naive date against a stored
    UTC datetime is what quietly drops the last day of every window.
    """
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    return qs


# ------------------------------------------------------------------ breakdowns
def breakdown(qs, field, choices=None, limit=None, blank_ok=False):
    """Counts per value of `field`, biggest first.

    `choices` maps stored codes to the labels the applicant actually saw; values
    with no entry pass through as themselves (free-typed countries, legacy
    sectors). `limit` folds the tail into a single "Other" row rather than
    inventing more colours for it — the dashboard draws these as one-hue bars, so
    a long tail costs legibility, not palette slots.
    """
    labels = dict(choices or [])
    rows = Counter()
    answered = 0
    for value in qs.values_list(field, flat=True):
        value = (value or "").strip() if isinstance(value, str) else value
        if not value and not blank_ok:
            continue
        answered += 1
        rows[labels.get(value, value or "Not said")] += 1

    ordered = sorted(rows.items(), key=lambda kv: (-kv[1], str(kv[0]).lower()))
    if limit and len(ordered) > limit:
        head, tail = ordered[:limit], ordered[limit:]
        ordered = head + [("Other", sum(n for _, n in tail))]
    return _as_bars(ordered, answered)


def multi_breakdown(qs, field, choices):
    """Counts for a comma-separated multi-select (the growth blockers).

    `answered` counts *people*, not ticks, so the bar percentages read as "share
    of applicants who named this" — which is the only reading that makes sense
    when one applicant can tick four boxes. The total will exceed 100%; the
    template says so under the chart.
    """
    labels = dict(choices)
    rows = Counter()
    answered = 0
    for raw in qs.values_list(field, flat=True):
        codes = [c for c in (raw or "").split(",") if c.strip()]
        if not codes:
            continue
        answered += 1
        for code in codes:
            rows[labels.get(code.strip(), code.strip())] += 1
    return _as_bars(sorted(rows.items(), key=lambda kv: -kv[1]), answered)


def _as_bars(pairs, answered):
    """Shared shape for every bar list: value, share, and bar width.

    `width` is scaled to the biggest row rather than to the total, because these
    charts answer "which is largest" — scaling to the total leaves every bar a
    stub whenever the field has a long tail. `pct` stays the true share so the
    printed number and the bar length are answering different questions on
    purpose, and the template labels both.
    """
    top = max((n for _, n in pairs), default=0)
    return {
        "rows": [{
            "label": label,
            "value": n,
            "pct": round(n / answered * 100) if answered else 0,
            "width": round(n / top * 100, 1) if top else 0,
        } for label, n in pairs],
        "answered": answered,
        "total": sum(n for _, n in pairs),
    }


def bucketed_business_age(qs, today=None):
    """Business age in bands. Ordered, so the dashboard draws it as one ramp.

    `year_established` is a year, not a date, so the arithmetic is deliberately
    coarse. Years in the future (a typo, or someone entering 2027) and absurdly
    old ones are dropped rather than shown as a negative age.
    """
    year = (today or timezone.localdate()).year
    bands = [("Under 1 year", 0, 0), ("1–2 years", 1, 2), ("3–5 years", 3, 5),
             ("6–10 years", 6, 10), ("Over 10 years", 11, 200)]
    rows = Counter()
    answered = 0
    for established in qs.values_list("year_established", flat=True):
        if not established or not (1900 < established <= year):
            continue
        age = year - established
        answered += 1
        for label, low, high in bands:
            if low <= age <= high:
                rows[label] += 1
                break
    # Band order, not count order: these are ordinal, and sorting them by size
    # would throw away the shape the reader is here to see.
    ordered = [(label, rows.get(label, 0)) for label, _, _ in bands]
    return _as_bars(ordered, answered)


# ------------------------------------------------------------------- timeseries
def daily_counts(qs, start, end):
    """One row per day in [start, end], zero-filled.

    Zero-filling is the point: a gap in a dict of "days that had applications"
    draws as a straight line between two peaks and hides the quiet days
    completely. Days with no applications are information.
    """
    # TruncDate applies the active timezone, so a submission at 00:30 Lagos time
    # lands on the right local day rather than the previous UTC one.
    counted = {
        row["day"]: row["n"] for row in
        qs.annotate(day=TruncDate("created_at")).values("day").annotate(n=Count("id"))
    }
    # `day` comes back as a date on SQLite and can be a datetime elsewhere.
    counted = {(d.date() if isinstance(d, dt.datetime) else d): n
               for d, n in counted.items() if d}
    days, cursor = [], start
    while cursor <= end:
        days.append({"date": cursor, "value": counted.get(cursor, 0)})
        cursor += dt.timedelta(days=1)
    return days


def rolling_mean(series, window=7):
    """Trailing mean over `window` days, for the smoothed line on the area chart.

    Trailing rather than centred: a centred mean would need future days and so
    would stop short of today, which reads as the chart being broken.
    """
    out, run = [], []
    for point in series:
        run.append(point["value"])
        if len(run) > window:
            run.pop(0)
        out.append(sum(run) / len(run))
    return out


# ------------------------------------------------------------------ SVG geometry
class Plot:
    """Geometry for the applications-over-time chart.

    Rendered once into a viewBox and scaled *uniformly* to the column, so the
    axis text never stretches. The aspect (720×300, a shade wider than 2:1) is
    chosen so the same drawing is still tall enough to read on a phone; staff.css
    compensates the label size in user units at narrow widths, since a uniformly
    scaled SVG shrinks its own text along with everything else.
    """
    W, H = 720, 300
    PAD_L, PAD_R, PAD_T, PAD_B = 40, 10, 16, 30

    def __init__(self, series, mean=None):
        self.series = series
        self.mean = mean or []
        self.n = len(series)
        self.peak = max([p["value"] for p in series] + [1])
        self.top = self._nice_ceiling(self.peak)

    @staticmethod
    def _nice_ceiling(peak):
        """A round number at or above the peak, so gridline labels are readable.

        1/2/5 × a power of ten — the same ladder every axis library uses, because
        a y-axis topping out at "37" gives the reader nothing to measure against.
        """
        if peak <= 4:
            return 4
        for magnitude in (1, 10, 100, 1000, 10000):
            for step in (1, 2, 2.5, 5, 10):
                candidate = step * magnitude
                if candidate >= peak:
                    return int(candidate)
        return peak

    @property
    def plot_w(self):
        return self.W - self.PAD_L - self.PAD_R

    @property
    def plot_h(self):
        return self.H - self.PAD_T - self.PAD_B

    def x(self, i):
        if self.n <= 1:
            return self.PAD_L + self.plot_w / 2
        return self.PAD_L + i * self.plot_w / (self.n - 1)

    def y(self, value):
        return self.PAD_T + self.plot_h * (1 - value / self.top)

    def _path(self, values):
        return " ".join(
            f"{'M' if i == 0 else 'L'}{self.x(i):.1f},{self.y(v):.1f}"
            for i, v in enumerate(values))

    def line(self):
        return self._path([p["value"] for p in self.series])

    def mean_line(self):
        return self._path(self.mean) if self.mean else ""

    def area(self):
        if not self.n:
            return ""
        base = self.y(0)
        return (f"{self.line()} L{self.x(self.n - 1):.1f},{base:.1f} "
                f"L{self.x(0):.1f},{base:.1f} Z")

    def gridlines(self):
        """Four horizontal rules including zero, labelled with whole numbers."""
        steps = 4
        return [{"y": round(self.y(self.top * i / steps), 1),
                 "label": int(self.top * i / steps)}
                for i in range(steps + 1)]

    def xticks(self, count=5):
        """Date labels at the ends and evenly between, never overlapping.

        Fewer points than slots means every point gets a label; more means we
        sample, and the last tick is always the final day so the chart's right
        edge is dated.
        """
        if not self.n:
            return []
        if self.n <= count:
            picks = range(self.n)
        else:
            picks = {round(i * (self.n - 1) / (count - 1)) for i in range(count)}
            picks = sorted(picks)
        # f-string, not strftime("%-d"): the no-pad day flag is a glibc
        # extension and raises ValueError on Windows.
        return [{"x": round(self.x(i), 1),
                 "label": f"{self.series[i]['date'].day} {self.series[i]['date']:%b}",
                 "anchor": "start" if i == 0 else ("end" if i == self.n - 1 else "middle")}
                for i in picks]

    def hotspots(self):
        """One hover target per day, plus the dot the crosshair snaps to.

        `band` is the full-height rectangle staff.js listens on: a 3px dot is an
        unhittable target with a mouse and impossible with a thumb, so the
        target is the column, not the mark.
        """
        half = (self.plot_w / max(self.n - 1, 1)) / 2 if self.n > 1 else self.plot_w / 2
        out = []
        for i, point in enumerate(self.series):
            centre = self.x(i)
            left = max(self.PAD_L, centre - half)
            right = min(self.W - self.PAD_R, centre + half)
            out.append({
                "x": round(centre, 1),
                "y": round(self.y(point["value"]), 1),
                "band_x": round(left, 1),
                "band_w": round(right - left, 1),
                "value": point["value"],
                "date": point["date"],
            })
        return out


def sparkline(values, w=104, h=28):
    """Tiny trend line for a stat tile. No axes, no labels — shape only.

    A flat series still has to draw *something*, so a single-value or all-equal
    series is pinned to the vertical middle rather than dividing by a zero range.
    """
    if not values:
        return {"line": "", "area": "", "last": None}
    low, high = min(values), max(values)
    span = (high - low) or 1
    step = w / max(len(values) - 1, 1)

    def point(i, v):
        y = h - 2 - (h - 4) * ((v - low) / span if high != low else 0.5)
        return i * step, y

    coords = [point(i, v) for i, v in enumerate(values)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}"
                    for i, (x, y) in enumerate(coords))
    area = f"{line} L{coords[-1][0]:.1f},{h} L0,{h} Z"
    return {"line": line, "area": area, "w": w, "h": h,
            "last": {"x": round(coords[-1][0], 1), "y": round(coords[-1][1], 1)}}


def heat_grid(series):
    """The daily series as week-columns × weekday-rows, for the calendar heatmap.

    Level 0–4 indexes the one-hue ramp in staff.css. Levels are cut on the
    series' own peak, so a quiet cohort still shows contrast instead of one flat
    block — the legend states the top of the scale so nobody reads the shading
    as an absolute.
    """
    if not series:
        return {"weeks": [], "peak": 0}
    peak = max(p["value"] for p in series) or 1
    weeks, current = [], [None] * 7
    for point in series:
        weekday = point["date"].weekday()          # Monday = 0
        level = 0 if not point["value"] else min(4, 1 + int(
            (point["value"] - 1) / peak * 3.999))
        current[weekday] = {**point, "level": level}
        if weekday == 6:
            weeks.append(current)
            current = [None] * 7
    if any(current):
        weeks.append(current)
    return {"weeks": weeks, "peak": peak,
            "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}


# ------------------------------------------------------------------- the payload
def dashboard(range_key=None, today=None):
    """Everything the analytics template renders, in one dict."""
    today = today or timezone.localdate()
    key, label, start, end = resolve_range(range_key, today)
    # An "all time" or future-ending window still plots up to today — drawing a
    # flat tail out to 11 September would read as forty days of zero applications.
    plot_end = min(end, today) if end else today

    apps_all = EmbarkApplication.objects.all()
    apps = in_window(apps_all, start, end)

    first = apps_all.order_by("created_at").values_list("created_at", flat=True).first()
    plot_start = start or (timezone.localtime(first).date() if first else today)
    plot_start = min(plot_start, plot_end)

    series = daily_counts(in_window(apps_all, plot_start, plot_end), plot_start, plot_end)
    plot = Plot(series, rolling_mean(series))

    return {
        "range": {"key": key, "label": label, "start": start, "end": end,
                  "options": [{"key": k, "label": v[0]} for k, v in RANGES.items()]},
        "today": today,
        "plot_from": plot_start,
        "plot_to": plot_end,
        "cohort_name": cohort.NAME,
        "window": cohort.window_progress(today),
        "tiles": _tiles(apps, start, end, plot_start, plot_end, today),
        "plot": plot,
        "series": series,
        "heat": heat_grid(series),
        "funnel": _funnel(apps),
        "countries": breakdown(apps, "country", limit=8),
        "sectors": breakdown(apps, "business_sector",
                             EmbarkApplication.SECTOR_CHOICES, limit=8),
        "referrals": breakdown(apps, "heard_about", EmbarkApplication.REFERRAL_CHOICES),
        "blockers": multi_breakdown(apps, "growth_limits",
                                    EmbarkApplication.GROWTH_LIMIT_CHOICES),
        "status": breakdown(apps, "applicant_status", EmbarkApplication.STATUS_CHOICES),
        "gender": breakdown(apps, "gender", EmbarkApplication.GENDER_CHOICES),
        "devices": breakdown(apps, "device", EmbarkApplication.DEVICE_CHOICES),
        "internet": _internet(apps),
        "business_age": bucketed_business_age(apps, today),
        "consent": _rate(apps, media_consent=True),
        "recent": apps.order_by("-created_at")[:8],
    }


def _tiles(apps, start, end, plot_start, plot_end, today):
    """The KPI row: a number, a comparison, and a shape for each source.

    The comparison is against the *previous window of the same length*, which is
    the only honest one — "up 12 on last month" means nothing if last month was
    measured over a different number of days. An open-ended window has nothing to
    compare against and says so by omitting the delta.
    """
    span = (end - start).days + 1 if start and end else None
    prev = None
    if span:
        prev = (start - dt.timedelta(days=span), start - dt.timedelta(days=1))

    tiles = []
    for key, label, model, _url in FORM_SOURCES:
        qs = model.objects.all()
        current = in_window(qs, start, end).count()
        delta = None
        if prev:
            was = in_window(qs, *prev).count()
            delta = {"value": current - was, "was": was}
        spark = daily_counts(in_window(qs, plot_start, plot_end), plot_start, plot_end)
        tiles.append({
            "key": key, "label": label, "value": current, "delta": delta,
            "total": qs.count(),
            "spark": sparkline([p["value"] for p in spark]),
        })
    return tiles


def _funnel(apps):
    """Application → reviewable → reviewed, as ordered stages.

    "Reviewable" means there is something to watch: a pasted link, or a file from
    before the August 2026 switch to links. An application without either cannot
    be assessed, and the gap between stage one and two is the number staff need
    to see — it is a chase list, not a statistic.
    """
    total = apps.count()
    watchable = apps.exclude(business_video_url="", business_video="").count()
    reviewed = apps.filter(reviewed=True).count()
    stages = [("Applications received", total), ("Video to review", watchable),
              ("Reviewed by the team", reviewed)]
    return [{
        "label": label, "value": n,
        "pct": round(n / total * 100) if total else 0,
        "drop": (stages[i - 1][1] - n) if i else None,
    } for i, (label, n) in enumerate(stages)]


def _internet(apps):
    """Connectivity readiness, on the reserved status scale.

    This one series genuinely means good → bad (an applicant with no reliable
    connection cannot attend a live class), so it wears status tokens rather than
    series colours, each with its own written label — never colour alone.
    """
    order = [("yes", "Reliable", "good"), ("sometimes", "Sometimes", "warning"),
             ("no", "Not reliable", "critical")]
    counts = {row["reliable_internet"]: row["n"] for row in
              apps.values("reliable_internet").annotate(n=Count("id"))}
    answered = sum(n for code, n in counts.items() if code)
    return {"answered": answered, "rows": [{
        "label": label, "status": status, "value": counts.get(code, 0),
        "pct": round(counts.get(code, 0) / answered * 100) if answered else 0,
    } for code, label, status in order]}


def _rate(qs, **filters):
    """A single ratio — drawn as a meter, not a two-slice pie."""
    total = qs.count()
    hit = qs.filter(**filters).count()
    return {"value": hit, "total": total,
            "pct": round(hit / total * 100) if total else 0}
