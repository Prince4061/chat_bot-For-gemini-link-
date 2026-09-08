"""
Link freshness checker (Google One / Gemini activation links).

IMPORTANT (learned from real links): both FRESH and USED Gemini links can live on
`serviceactivation.google.com` or `one.google.com/activate-plan/...`, so the host name says
NOTHING about freshness. An unauthenticated server request is usually redirected to the
Google login page for fresh and used links alike, which also cannot tell them apart.

Order of evidence:
  1. The logged-in browser checker (google_checker) when the admin connected a Google session:
     it reads Google's own "already used / expired / Activate plan" page -> authoritative.
  2. Otherwise (or when the browser is inconclusive: busy, rate-limited, dead session, error)
     the conservative HTTP probe below:
       * "used"    -> only on STRONG evidence: HTTP 404/410, or an explicit "already redeemed /
                      expired / invalid" message on a page that is NOT the login page.
       * "fresh"   -> the activation page itself loaded (no login wall) without such a message.
       * "unknown" -> login wall / network error / anything ambiguous. Callers hand these out
                      normally; we never block a sale on uncertainty.

check_link_freshness_detail() returns (health, method), method in browser | browser-fallback | http | none.
"""
import logging
import re
from typing import Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 8
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_GOOGLE_HOSTS = ("one.google.com", "serviceactivation.google.com", "families.google.com")

# Strong, explicit "consumed" wording. Deliberately NOT generic phrases like "not available",
# which appear on Google's login/consent pages and caused false positives before.
_USED_MARKERS = (
    "already been redeemed", "already redeemed", "has already been used", "already been used",
    "this offer has expired", "offer has expired", "this link has expired", "code has already been used",
    "promotion has already been redeemed", "no longer available for redemption",
)


def is_checkable(url: str) -> bool:
    """True only for links we know how to look at (Google One / Gemini family). Exact host match:
    'one.google.com.evil.io' or 'https://x/?u=one.google.com' are NOT checkable."""
    try:
        p = urlparse((url or "").strip())
    except ValueError:
        return False
    return p.scheme in ("http", "https") and (p.hostname or "").lower() in _GOOGLE_HOSTS


def _is_login_wall(final_url: str) -> bool:
    return "accounts.google.com" in final_url or "/signin" in final_url or "servicelogin" in final_url


def _http_probe(url: str) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        logger.warning("Link check failed (%s...): %s", url[:40], type(exc).__name__)
        return "unknown"

    final_url = (resp.url or "").lower()

    # Dead link: Google removed/expired the activation resource.
    if resp.status_code in (404, 410):
        return "used"

    # Behind the login wall we cannot see the offer state -> unknown (not "fresh", not "used").
    if _is_login_wall(final_url):
        return "unknown"

    body = ""
    try:
        body = re.sub(r"\s+", " ", resp.text[:60000].lower())
    except Exception:  # noqa: BLE001
        body = ""
    if any(m in body for m in _USED_MARKERS):
        return "used"

    if resp.status_code < 400 and "google.com" in final_url:
        return "fresh"
    return "unknown"


def check_link_freshness_detail(url: str, allow_browser: bool = True) -> Tuple[str, str]:
    """
    Returns (health, method): health in fresh | used | unknown, method in browser | browser-fallback | http | none.
    Never returns "used" without explicit evidence.
    """
    if not is_checkable(url):
        return "unknown", "none"
    if allow_browser:
        try:
            import google_checker
            if google_checker.is_ready():
                r = google_checker.check_link(url)
                if r.status in ("used", "expired"):
                    return "used", "browser"
                if r.status == "fresh":
                    return "fresh", "browser"
                # logged_out / ineligible / unknown / error / busy / rate_limited -> not a verdict.
                # Fall through to the cheap HTTP probe so 404/410 dead links are still caught.
                logger.info("Browser checker inconclusive for %s...: %s (%s) - HTTP probe next",
                            url[:40], r.status, r.reason)
                # "browser-fallback": the browser was attempted on this link but gave no verdict, so the
                # buyer is told it could not be live-verified (plain "http" = browser never involved).
                return _http_probe(url), "browser-fallback"
        except Exception as exc:  # noqa: BLE001
            logger.warning("google_checker unavailable (%s); falling back to HTTP probe", type(exc).__name__)
    return _http_probe(url), "http"


def check_link_freshness(url: str, allow_browser: bool = True) -> str:
    """See module docstring. Returns "fresh" | "used" | "unknown"."""
    return check_link_freshness_detail(url, allow_browser)[0]
