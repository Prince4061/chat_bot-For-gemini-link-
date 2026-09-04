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

# The single DEFINITIVE signal: a USED Google/Gemini link ends up on this host.
# A FRESH link stays on one.google.com or bounces to accounts.google.com (login) —
# both are normal. We deliberately do NOT scan page text, because Google's login/consent
# pages contain generic phrases ("not available", etc.) that caused fresh links to be
# wrongly flagged as used.
_GOOGLE_USED_HOST = "serviceactivation.google.com"


def is_checkable(url: str) -> bool:
    """True only for links whose freshness we know how to verify (currently Google One / Gemini)."""
    u = (url or "").lower()
    return u.startswith("http") and ("one.google.com" in u or "serviceactivation.google.com" in u
                                     or "families.google.com" in u)


def check_link_freshness(url: str) -> str:
    """
    Returns "fresh" | "used" | "unknown".
    Conservative on purpose: a link is "used" ONLY if it (originally or after redirects)
    lands on the used-activation host. Any ambiguity or network error is "unknown", which
    the caller hands out normally — we never block a sale on a fresh/uncertain link.
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

    # Check the final URL and the whole redirect chain for the used host.
    urls = [(resp.url or "").lower()] + [(r.url or "").lower() for r in resp.history]
    if any(_GOOGLE_USED_HOST in u for u in urls):
        return "used"

    # Reachable Google page that did NOT bounce to the used host -> fresh.
    final_url = (resp.url or "").lower()
    if "google.com" in final_url and resp.status_code < 400:
        return "fresh"
    return "unknown"
