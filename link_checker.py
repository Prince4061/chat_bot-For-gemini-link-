"""
Link freshness checker.

Some invite links (notably Google One / Gemini) are fresh when added but get consumed
later. A USED Google link redirects to `serviceactivation.google.com`, while a FRESH one
stays on `one.google.com/activate-plan`. We check this lazily — only when a user actually
asks for a link — so the bot never hands out a used link.

Return values: "fresh" | "used" | "unknown".
Only URLs we know how to verify are "checkable"; everything else is left untouched.
"""
import logging
import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 8
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Hosts/patterns that mean a Google/Gemini link is FRESH vs USED.
_GOOGLE_FRESH_MARKERS = ("one.google.com/activate-plan", "one.google.com/about")
_GOOGLE_USED_HOST = "serviceactivation.google.com"

# Substrings in page text that indicate a consumed/invalid invite (best-effort).
_USED_TEXT_MARKERS = (
    "already been used", "no longer valid", "has expired", "already redeemed",
    "link is invalid", "already claimed", "not available",
)


def is_checkable(url: str) -> bool:
    """True only for links whose freshness we know how to verify (currently Google One / Gemini)."""
    u = (url or "").lower()
    return u.startswith("http") and ("one.google.com" in u or "serviceactivation.google.com" in u
                                     or "families.google.com" in u)


def check_link_freshness(url: str) -> str:
    """
    Returns "fresh" | "used" | "unknown".
    Network errors return "unknown" so we never block a sale on a transient failure.
    """
    if not is_checkable(url):
        return "unknown"

    # A link that is ALREADY the used-activation host is definitely used.
    if _GOOGLE_USED_HOST in url.lower():
        return "used"

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        logger.warning("Link check failed (%s): %s", url[:60], exc)
        return "unknown"

    final_url = (resp.url or "").lower()
    body = ""
    try:
        body = resp.text[:20000].lower()
    except Exception:  # noqa: BLE001
        body = ""

    if _GOOGLE_USED_HOST in final_url:
        return "used"
    if any(m in body for m in _USED_TEXT_MARKERS):
        return "used"
    if any(m in final_url for m in _GOOGLE_FRESH_MARKERS):
        return "fresh"
    # Reachable Google page that didn't bounce to the used host — treat as fresh.
    if "google.com" in final_url and resp.status_code < 400:
        return "fresh"
    return "unknown"
