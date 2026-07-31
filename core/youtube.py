"""Turning pasted YouTube links into things a page can actually use.

Whoever fills in the admin pastes whatever the YouTube share button gave them,
which is any of:

    https://youtu.be/ID                      share button, desktop
    https://youtu.be/ID?si=xxxx&t=30         share button, with tracking + start
    https://www.youtube.com/watch?v=ID       address bar
    https://youtube.com/shorts/ID            share button on a Short
    https://www.youtube.com/embed/ID         already an embed

All of them reduce to an eleven-character video id, so parse the id once and
build the URLs we need from it. The previous per-model implementations pattern
matched on the URL text instead and silently passed Shorts links straight
through, so the iframe pointed at the watch page — which YouTube refuses to
frame, leaving a blank box on the page.
"""
from urllib.parse import parse_qs, urlparse

# youtube-nocookie serves the same player without writing a tracking cookie
# until the visitor actually presses play.
EMBED_BASE = "https://www.youtube-nocookie.com/embed/"
THUMB_BASE = "https://i.ytimg.com/vi/"


def video_id(url):
    """The video id from any YouTube URL shape, or "" if it isn't one."""
    if not url:
        return ""
    parts = urlparse(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.strip("/")

    if host in ("youtu.be", "youtube-nocookie.be"):
        return path.split("/")[0]
    if host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        if path.startswith(("shorts/", "embed/", "live/", "v/")):
            return path.split("/", 1)[1].split("/")[0]
        found = parse_qs(parts.query).get("v")
        if found:
            return found[0]
    return ""


def is_short(url):
    """True for a /shorts/ link — the one shape we know is filmed vertically."""
    if not url:
        return False
    return "/shorts/" in urlparse(url.strip()).path


def embed_url(url, *, autoplay=False, mute=False):
    """A privacy-friendly embed URL, or "" when the link can't be parsed.

    Returning "" rather than the original matters: an unparseable link should
    render nothing at all, not an iframe pointing at a page that will refuse
    to load inside one.
    """
    vid = video_id(url)
    if not vid:
        return ""
    params = ["rel=0", "playsinline=1"]           # no unrelated-video grid at the end
    if autoplay:
        params.append("autoplay=1")
    if mute or autoplay:                          # browsers block unmuted autoplay
        params.append("mute=1")
    return f"{EMBED_BASE}{vid}?{'&'.join(params)}"


def thumbnail_url(url):
    """Poster frame for the click-to-play facade."""
    vid = video_id(url)
    return f"{THUMB_BASE}{vid}/hqdefault.jpg" if vid else ""


def watch_url(url):
    """Canonical watch link, for the 'open on YouTube' fallback."""
    vid = video_id(url)
    return f"https://www.youtube.com/watch?v={vid}" if vid else ""
