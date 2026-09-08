"""
Google One / Gemini activation-link checker using a LOGGED-IN headless browser.

Why a browser: without a Google login the activation page only shows "Sign in", identical
for fresh and used links (verified). Logged in, Google's own page states the truth:
  USED    -> "The subscription link has already been used ..." / "पहले ही इस्तेमाल किया जा चुका है"
  EXPIRED -> "The subscription link has expired" / "समयसीमा खत्म"
  FRESH   -> plan details + an "Activate plan" / "प्लान चालू करें" button
Viewing the page does NOT redeem the offer — redemption is the Activate click, which this
module NEVER performs (it only navigates and reads text).

Setup (owner does this once):
  1. Create a throwaway Google account that has NO Google One / Gemini plan (else fresh links
     may show an "ineligible" page) — never use the main business Gmail.
  2. On a PC with a screen:  python google_checker.py login
     -> a Chrome window opens, sign in to that account, press Enter -> google_session.json
  3. Admin panel -> Settings -> Google Link Checker -> paste/upload google_session.json.
  On the VPS: pip install playwright && python3 -m playwright install --with-deps chromium

Safety rails:
  * Only https URLs on Google's activation hosts are ever opened (no SSRF via the admin Test box).
  * Conservative: anything unclear is "unknown" (the link is still handed out); a dead session
    is reported as "logged_out" so the admin can reconnect.
  * Error text never contains link URLs/tokens (they are the product); session files are 0600.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from config import Config
from link_checker import _GOOGLE_HOSTS as ALLOWED_HOSTS

logger = logging.getLogger(__name__)

CHECKER_DIR = Path(getattr(Config, "GOOGLE_CHECKER_DIR", Config.AGENT_WORKSPACE_DIR / "google_checker"))
PROFILE_DIR = CHECKER_DIR / "profile"                 # persistent Chromium user-data-dir
STATE_FILE = CHECKER_DIR / "google_session.json"      # storage_state (cookies) uploaded by admin
IMPORT_MARK = PROFILE_DIR / ".session_imported"       # which session file was already loaded
LAST_SHOT = CHECKER_DIR / "last_check.png"
STATUS_FILE = CHECKER_DIR / "status.json"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_BROWSER_LOCK = threading.Lock()
# Two hourly budgets: live sales ("sale") and admin Test/Verify ("probe"), so a curious admin
# can never starve real claims of verification.
_RATE: Dict[str, Dict[str, Any]] = {"sale": {"window_start": 0.0, "count": 0},
                                    "probe": {"window_start": 0.0, "count": 0}}
_CACHE: Dict[str, Any] = {}   # url -> (status, ts)
# Circuit breaker: after a dead session / browser error, don't launch Chrome on every claim.
_DOWN: Dict[str, Any] = {"until": 0.0, "status": None, "reason": None}
# Cached "is Chromium really installed" probe (pip package alone proves nothing).
_BROWSER_OK: Dict[str, Any] = {"ts": 0.0, "ok": False, "path": ""}
LOGIN_COOKIES = ("SID", "__Secure-1PSID", "__Secure-3PSID", "SAPISID")


def _mark_down(status: str, reason: str) -> None:
    _DOWN.update({"until": time.time() + Config.GOOGLE_CHECKER_DOWN_COOLDOWN_SECONDS, "status": status, "reason": reason})


def _down_result() -> Optional["CheckResult"]:
    left = _DOWN["until"] - time.time()
    if left > 0 and _DOWN["status"]:
        return CheckResult(_DOWN["status"], f"{_DOWN['reason']} (retry in {int(left)}s)")
    return None


def is_allowed_url(url: str) -> bool:
    """Only https links on Google's activation hosts may be opened by the server-side browser."""
    try:
        p = urlparse((url or "").strip())
    except ValueError:
        return False
    return p.scheme == "https" and (p.hostname or "").lower() in ALLOWED_HOSTS


def _is_google_host(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return host == "google.com" or host.endswith(".google.com")


def _safe_reason(exc: BaseException) -> str:
    """Exception text without URLs/tokens (Playwright embeds the full URL in navigation errors)."""
    text = str(exc).strip()
    first = text.splitlines()[0] if text else ""
    first = re.sub(r"https?://\S+", "<url>", first)
    first = re.sub(r"\bAQ[\w-]{20,}", "<token>", first)
    return f"{type(exc).__name__}: {first}"[:200]


def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _write_private(path: Path, text: str) -> None:
    """Write a file readable only by the service user (session cookies = account takeover)."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# --- Google's own page strings (EN + HI) ----------------------------------------------
USED_MARKERS = (
    "already been used to activate", "subscription link has already been used", "already been used",
    "already redeemed", "has already been redeemed",
    "पहले ही इस्तेमाल", "पहले से इस्तेमाल", "पहले ही रिडीम",
)
EXPIRED_MARKERS = (
    "subscription link has expired", "link has expired", "this link has expired", "offer has expired",
    "समयसीमा खत्म", "समय-सीमा खत्म", "अवधि खत्म",
)
# The account itself can't take the offer -> says nothing about the LINK -> unknown, never "used".
INELIGIBLE_MARKERS = (
    "not eligible", "isn't eligible", "is not eligible", "not available in your country",
    "not available in your region", "already have a google one", "already subscribed",
    "already have this plan", "can't be redeemed", "cannot be redeemed", "you already have",
    "इस ऑफ़र के लिए योग्य नहीं", "पहले से ही सदस्यता",
)
ACTIVATE_MARKERS = ("activate plan", "activate", "प्लान चालू करें", "चालू करें", "get plan", "start plan")
LOGIN_URL_MARKERS = ("accounts.google.com", "/servicelogin", "/signin")

VERDICTS = ("fresh", "used", "expired", "ineligible")   # statuses that prove a signed-in page rendered


@dataclass
class CheckResult:
    status: str            # fresh | used | expired | ineligible | logged_out | unknown | error | disabled | busy | rate_limited
    reason: str = ""
    final_url: str = ""
    snippet: str = ""
    screenshot: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "reason": self.reason, "final_url": self.final_url[:200],
                "snippet": self.snippet[:400], "screenshot": self.screenshot}


def classify_page(text: str, final_url: str, has_activate_button: bool = False) -> CheckResult:
    """Pure classification of a rendered activation page (unit-tested; no browser needed)."""
    t = re.sub(r"\s+", " ", (text or "")).lower()
    u = (final_url or "").lower()
    if any(m in u for m in LOGIN_URL_MARKERS) or "sign in - google accounts" in t[:200]:
        return CheckResult("logged_out", "Redirected to Google sign-in - checker session expired", final_url, t[:200])
    if any(m in t for m in USED_MARKERS):
        return CheckResult("used", "Google says the link was already used", final_url, t[:300])
    if any(m in t for m in EXPIRED_MARKERS):
        return CheckResult("expired", "Google says the link has expired", final_url, t[:300])
    if any(m in t for m in INELIGIBLE_MARKERS):
        return CheckResult("ineligible", "Checker account can't take this offer (not the link's fault)", final_url, t[:300])
    if has_activate_button or any(m in t for m in ACTIVATE_MARKERS):
        return CheckResult("fresh", "Activation page with an Activate button is showing", final_url, t[:300])
    return CheckResult("unknown", "Page did not match any known state", final_url, t[:300])


# --- availability / status -------------------------------------------------------------

def playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def browser_available() -> bool:
    """True when Chromium is really installed for Playwright (the pip package alone is not enough).
    Cached: 10 min when OK, 1 min when missing (so it recovers quickly after `playwright install`)."""
    ttl = 600 if _BROWSER_OK["ok"] else 60
    if time.time() - _BROWSER_OK["ts"] < ttl:
        return _BROWSER_OK["ok"]
    if not playwright_installed():
        _BROWSER_OK.update(ts=time.time(), ok=False, path="")
        return False
    ok, path = False, ""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path or ""
            ok = bool(path) and Path(path).exists()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Chromium probe failed: %s", _safe_reason(exc))
    _BROWSER_OK.update(ts=time.time(), ok=ok, path=path)
    return ok


def session_present() -> bool:
    return STATE_FILE.exists() or (PROFILE_DIR.exists() and any(PROFILE_DIR.glob("Default/Cookies*")))


def _read_status() -> Dict[str, Any]:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _write_status(**kw) -> None:
    try:
        _secure_dir(CHECKER_DIR)
        cur = _read_status()
        cur.update(kw)
        STATUS_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def enabled_in_settings() -> bool:
    """Admin toggle. A NULL column (database upgraded before the setting existed) means enabled,
    matching what the Settings page shows."""
    try:
        from database import get_db, get_settings
        db = get_db()
        try:
            val = getattr(get_settings(db), "google_checker_enabled", None)
            return True if val is None else bool(val)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        return True


def is_ready() -> bool:
    """True when the browser checker can actually run: library + Chromium + session + enabled."""
    return playwright_installed() and session_present() and enabled_in_settings() and browser_available()


def not_ready_reason() -> Optional[str]:
    """Why the checker is NOT verifying right now (None when it is). Shown to the admin, never to buyers."""
    if not playwright_installed():
        return "playwright not installed on the server"
    if not browser_available():
        return "Chromium not installed (python3 -m playwright install --with-deps chromium)"
    if not session_present():
        return "no Google session connected (Admin -> Settings -> Google Link Checker)"
    if not enabled_in_settings():
        return "disabled in Settings"
    if _read_status().get("logged_in") is False:
        return "Google session expired - reconnect in Settings"
    down = _down_result()
    if down:
        return f"paused after '{down.status}' ({down.reason})"
    return None


def _hour_count(bucket: str) -> int:
    b = _RATE[bucket]
    return b["count"] if time.time() - b["window_start"] < 3600 else 0


def checker_status() -> Dict[str, Any]:
    st = _read_status()
    installed = playwright_installed()
    return {
        "installed": installed,
        "browser_ok": installed and browser_available(),
        "session_present": session_present(),
        "enabled": enabled_in_settings(),
        "ready": is_ready(),
        "logged_in": st.get("logged_in"),
        "last_check_at": st.get("last_check_at"),
        "last_status": st.get("last_status"),
        "last_error": st.get("last_error"),
        "checks_this_hour": _hour_count("sale"),
        "probe_checks_this_hour": _hour_count("probe"),
        "max_per_hour": Config.GOOGLE_CHECKER_MAX_PER_HOUR,
        "cooldown_seconds_left": max(0, int(_DOWN["until"] - time.time())) if _DOWN["status"] else 0,
        "not_ready_reason": not_ready_reason(),
        "screenshot_available": LAST_SHOT.exists(),
        "dir": str(CHECKER_DIR),
    }


# --- session import -----------------------------------------------------------------------

def _normalize_cookies(raw: Any) -> List[Dict[str, Any]]:
    """Accept Playwright storage_state, a bare cookie array, or Cookie-Editor/EditThisCookie exports.
    Keeps only real google.com cookies and requires a login cookie on google.com itself."""
    if isinstance(raw, dict) and "cookies" in raw:
        raw = raw["cookies"]
    if not isinstance(raw, list):
        raise ValueError("Expected a cookie array or a storage_state object with a 'cookies' list")
    if len(raw) > 500:
        raise ValueError("Too many cookies in the export (max 500)")
    out = []
    for c in raw:
        if not isinstance(c, dict) or not c.get("name") or "value" not in c:
            continue
        domain = str(c.get("domain") or "").strip().lower()
        bare = domain.lstrip(".")
        if not (bare == "google.com" or bare.endswith(".google.com")):
            continue  # only Google cookies are useful (and we don't want anything else)
        same = str(c.get("sameSite", "Lax") or "Lax").capitalize()
        if same not in ("Strict", "Lax", "None"):
            same = "None" if same.lower() in ("no_restriction", "unspecified") else "Lax"
        exp = c.get("expires", c.get("expirationDate", -1))
        try:
            exp = float(exp) if exp not in (None, "") else -1
        except (TypeError, ValueError):
            exp = -1
        out.append({
            "name": str(c["name"])[:200], "value": str(c["value"])[:4096], "domain": domain,
            "path": str(c.get("path") or "/")[:200],
            "expires": exp, "httpOnly": bool(c.get("httpOnly", False)), "secure": bool(c.get("secure", True)),
            "sameSite": same,
        })
    if not any(k["name"] in LOGIN_COOKIES and k["domain"].lstrip(".") == "google.com" for k in out):
        raise ValueError("No Google login cookies found (need SID / __Secure-1PSID etc. on google.com). Export cookies while signed in.")
    return out


def _acquire_browser(timeout: float) -> None:
    if not _BROWSER_LOCK.acquire(timeout=timeout):
        raise RuntimeError("Checker is busy with a link check - try again in a few seconds")


def save_session(raw_json: Any) -> Dict[str, Any]:
    """Store an uploaded session (storage_state or cookie export) and reset the import marker.
    Takes the browser lock so an in-flight check can't overwrite the new file with its old cookies."""
    cookies = _normalize_cookies(raw_json)
    _acquire_browser(60)
    try:
        _secure_dir(CHECKER_DIR)
        _write_private(STATE_FILE, json.dumps({"cookies": cookies, "origins": []}, ensure_ascii=False))
        if IMPORT_MARK.exists():
            IMPORT_MARK.unlink()
        _write_status(logged_in=None, last_error=None, session_saved_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        _CACHE.clear()
        _DOWN["until"] = 0.0   # new session -> try the browser again right away
    finally:
        _BROWSER_LOCK.release()
    return {"cookies": len(cookies)}


def clear_session() -> None:
    import shutil
    _acquire_browser(60)
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        _write_status(logged_in=False, last_error=None)
        _CACHE.clear()
    finally:
        _BROWSER_LOCK.release()


# --- the browser check ----------------------------------------------------------------------

def _rate_ok(bucket: str = "sale") -> bool:
    b = _RATE[bucket]
    limit = Config.GOOGLE_CHECKER_MAX_PER_HOUR if bucket == "sale" else Config.GOOGLE_CHECKER_PROBE_MAX_PER_HOUR
    now = time.time()
    if now - b["window_start"] >= 3600:
        b["window_start"], b["count"] = now, 0
    if b["count"] >= limit:
        return False
    b["count"] += 1
    return True


def check_link(url: str, force: bool = False, probe: bool = False) -> CheckResult:
    """
    Open `url` in the logged-in headless browser and classify the page. Read-only: never clicks.
      force  -> admin-triggered: bypass the cache and the cooldown, wait longer for the browser.
      probe  -> admin Test/Verify: separate hourly budget, never trips the circuit breaker or the cache.
    Results: fresh | used | expired | ineligible | logged_out | unknown | error | disabled | busy | rate_limited.
    """
    if not is_allowed_url(url):
        return CheckResult("unknown", "Not an https Google One / activation URL - not opened")
    if not playwright_installed():
        return CheckResult("disabled", "playwright not installed")
    if not session_present():
        return CheckResult("logged_out", "No Google session connected (Admin -> Settings -> Google Link Checker)")
    if not enabled_in_settings():
        return CheckResult("disabled", "Google checker disabled in settings")
    if not force:
        cached = _CACHE.get(url)
        if cached and time.time() - cached[1] < Config.GOOGLE_CHECKER_CACHE_SECONDS:
            return cached[0]
        down = _down_result()
        if down:
            return down

    wait = Config.GOOGLE_CHECKER_LOCK_WAIT_SECONDS * (6 if force else 1)
    if not _BROWSER_LOCK.acquire(timeout=wait):
        return CheckResult("busy", "Checker busy with another link - handed out unverified")
    try:
        bucket = "probe" if probe else "sale"
        if not _rate_ok(bucket):
            limit = Config.GOOGLE_CHECKER_PROBE_MAX_PER_HOUR if probe else Config.GOOGLE_CHECKER_MAX_PER_HOUR
            return CheckResult("rate_limited", f"Hourly check limit ({limit}/h) reached")
        if not browser_available():
            return CheckResult("disabled", "Chromium not installed on the server (run: python3 -m playwright install --with-deps chromium)")
        result = _run_browser_check(url)
    finally:
        _BROWSER_LOCK.release()

    status_kw: Dict[str, Any] = dict(last_check_at=time.strftime("%Y-%m-%dT%H:%M:%S"), last_status=result.status,
                                     last_error=(result.reason if result.status in ("error", "logged_out") else None))
    # Only a page that clearly rendered a signed-in state proves the session; "unknown" proves nothing.
    if result.status in VERDICTS:
        status_kw["logged_in"] = True
    elif result.status == "logged_out":
        status_kw["logged_in"] = False
    _write_status(**status_kw)
    if probe:
        if result.status in VERDICTS:
            _DOWN["until"] = 0.0          # a good admin probe proves the checker is back
    else:
        if result.status in ("fresh", "used", "expired"):
            _CACHE[url] = (result, time.time())
        if result.status in ("logged_out", "error"):
            _mark_down(result.status, result.reason)   # back off; admin sees it in Settings
        else:
            _DOWN["until"] = 0.0
    logger.info("Google checker: %s... -> %s (%s)", url[:40], result.status, result.reason)
    return result


def _run_browser_check(url: str) -> CheckResult:
    """Launch the persistent profile, open the page read-only and classify it. Caller holds _BROWSER_LOCK."""
    from playwright.sync_api import sync_playwright  # imported lazily: optional dependency

    timeout_ms = int(Config.GOOGLE_CHECKER_TIMEOUT_SECONDS * 1000)
    _secure_dir(CHECKER_DIR)
    _secure_dir(PROFILE_DIR)
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=True,
                user_agent=_UA,
                locale="en-IN",
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"],
            )
            try:
                # First run after an upload: load the uploaded cookies into the profile.
                if STATE_FILE.exists():
                    stamp = str(int(STATE_FILE.stat().st_mtime))
                    if not IMPORT_MARK.exists() or IMPORT_MARK.read_text() != stamp:
                        cookies = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("cookies", [])
                        if cookies:
                            ctx.add_cookies(cookies)
                        IMPORT_MARK.write_text(stamp)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(5000, timeout_ms))
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(1500)  # let the SPA paint the banner
                final_url = page.url
                if not _is_google_host(final_url):
                    # Never read or screenshot a non-Google page, whatever redirected us there.
                    return CheckResult("unknown", "Page left google.com - not classified")
                text = page.inner_text("body", timeout=5000)
                has_btn = False
                try:
                    has_btn = page.locator("button, a, [role=button]").filter(
                        has_text=re.compile(r"activate|चालू करें", re.I)).count() > 0
                except Exception:  # noqa: BLE001
                    pass
                result = classify_page(text, final_url, has_btn)
                if result.status in ("unknown", "ineligible", "logged_out"):
                    try:
                        page.screenshot(path=str(LAST_SHOT), full_page=False, timeout=5000)
                        result.screenshot = str(LAST_SHOT)
                    except Exception:  # noqa: BLE001
                        pass
                # Google rotates session cookies; keep the freshest copy for the next launch.
                try:
                    ctx.storage_state(path=str(STATE_FILE))
                    os.chmod(STATE_FILE, 0o600)
                    IMPORT_MARK.write_text(str(int(STATE_FILE.stat().st_mtime)))
                except Exception:  # noqa: BLE001
                    pass
                return result
            finally:
                ctx.close()
    except Exception as exc:  # noqa: BLE001
        reason = _safe_reason(exc)
        logger.warning("Google checker failed (%s...): %s", url[:40], reason)
        logger.debug("Google checker traceback", exc_info=True)
        return CheckResult("error", reason)


VERIFY_URL = "https://one.google.com/u/0/storage"   # requires a signed-in account (public home page does not)


def verify_session() -> CheckResult:
    """Open a login-REQUIRED Google One page to confirm the saved session is really signed in.
    (one.google.com's home renders publicly, so it can't be used for this.)"""
    r = check_link(VERIFY_URL, force=True, probe=True)
    if r.status == "logged_out":
        return r
    if any(m in (r.final_url or "").lower() for m in LOGIN_URL_MARKERS):
        _write_status(logged_in=False, last_error="Redirected to sign-in")
        return CheckResult("logged_out", "Redirected to Google sign-in - session not valid", r.final_url, r.snippet)
    if r.status in ("error", "disabled", "busy", "rate_limited") or not r.final_url:
        return r   # inconclusive: the browser did not render a signed-in page, say nothing about the session
    _write_status(logged_in=True, last_error=None)
    return CheckResult("logged_in", "Google session works (storage page opened while signed in)", r.final_url, r.snippet)


# --- CLI: one-time login helper for the owner's PC ------------------------------------------

def _cli_login(out_path: str) -> None:
    from playwright.sync_api import sync_playwright
    local_profile = Path("google_checker_local_profile").resolve()
    print("\nA Chrome window will open. Sign in to the THROWAWAY Google account (no Google One plan).")
    print("When you can see Google One's home page signed in, come back here and press Enter.\n")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(local_profile), headless=False, user_agent=_UA,
                                                   args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://accounts.google.com/ServiceLogin?continue=https://one.google.com/")
        input("Press Enter here AFTER you are signed in... ")
        page.goto("https://one.google.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        if "accounts.google.com" in page.url:
            print("Still on the sign-in page - not logged in. Run again.")
        ctx.storage_state(path=out_path)
        try:
            os.chmod(out_path, 0o600)
        except OSError:
            pass
        ctx.close()
    print(f"\nSaved session -> {out_path}")
    print("Now open Admin -> Settings -> Google Link Checker and upload/paste this file. Keep it private")
    print("(it is git-ignored; never commit it).")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "login":
        _cli_login(sys.argv[2] if len(sys.argv) > 2 else "google_session.json")
    elif cmd == "test" and len(sys.argv) > 2:
        print(json.dumps(check_link(sys.argv[2], force=True, probe=True).as_dict(), ensure_ascii=False, indent=2))
    elif cmd == "verify":
        print(json.dumps(verify_session().as_dict(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(checker_status(), ensure_ascii=False, indent=2))
