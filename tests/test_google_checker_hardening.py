"""Pre-deploy hardening of the Google link checker: SSRF allow-list, honest verification
reporting, per-link checks for multi-link claims, HTTP fallback, NULL setting, safe errors."""
import uuid

import pytest

import database as dbm
import google_checker as gcm
import link_checker


def _google_product(db, n_links=3, base_price=1):
    slug = f"gh-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"GeminiH {slug}", slug=slug, base_price=base_price, margin_percent=0, reseller_margin_percent=0)
    db.add(p); db.commit()
    links = [f"https://one.google.com/activate-plan/subscription/new/H{i}{uuid.uuid4().hex[:6]}" for i in range(n_links)]
    for l in links:
        db.add(dbm.InviteLink(product_id=p.id, link_or_key=l))
    db.commit()
    return p, links


# ---- SSRF: the server-side browser only opens Google activation links -------------------------

def test_is_allowed_url_is_strict():
    assert gcm.is_allowed_url("https://one.google.com/activate-plan/subscription/new/AQCpiIx")
    assert gcm.is_allowed_url("https://serviceactivation.google.com/subscription/new/AQCpiIx")
    assert gcm.is_allowed_url("https://families.google.com/x")
    for bad in ("http://one.google.com/x",                      # plain http
                "https://evil.com/one.google.com",
                "https://one.google.com.evil.io/x",             # suffix trick
                "https://x.com/?u=one.google.com",
                "http://127.0.0.1:6379/", "http://169.254.169.254/latest/meta-data/",
                "file:///etc/passwd", "one.google.com/x", ""):
        assert not gcm.is_allowed_url(bad), bad
    assert not link_checker.is_checkable("https://one.google.com.evil.io/x")
    assert link_checker.is_checkable("https://serviceactivation.google.com/subscription/new/AQCpiIx")


def test_check_link_refuses_disallowed_url_without_touching_browser(monkeypatch):
    monkeypatch.setattr(gcm, "playwright_installed", lambda: True)
    monkeypatch.setattr(gcm, "session_present", lambda: True)
    monkeypatch.setattr(gcm, "_run_browser_check", lambda u: (_ for _ in ()).throw(AssertionError("browser launched!")))
    r = gcm.check_link("http://127.0.0.1:1/latest/meta-data/", force=True, probe=True)
    assert r.status == "unknown" and "not opened" in r.reason


def test_test_endpoint_rejects_non_google_urls(client, admin_headers):
    for bad in ("http://127.0.0.1:1/", "https://evil.com/x", "https://one.google.com.evil.io/x", ""):
        res = client.post("/api/admin/google-checker/test", json={"url": bad}, headers=admin_headers)
        assert res.status_code == 400, bad


# ---- errors never leak the product (link URLs / tokens) --------------------------------------

def test_safe_reason_redacts_urls_tokens_and_call_log():
    exc = TimeoutError("Page.goto: Timeout 20000ms exceeded at https://one.google.com/activate-plan/subscription/new/"
                       "AQCpiIHZabcdefghijklmnopqrstuvwxyz0123\nCall log:\n  - navigating to \"https://one.google.com/...\"")
    r = gcm._safe_reason(exc)
    assert "<url>" in r and "AQCpiI" not in r and "one.google.com" not in r
    assert "\n" not in r and len(r) <= 200 and r.startswith("TimeoutError:")
    assert "<token>" in gcm._safe_reason(Exception("bad token AQCpiIF1pM97abcdefghijklmnop here"))


# ---- session import hygiene ------------------------------------------------------------------

def test_cookie_domain_must_be_google_com():
    for dom in ("google.evil.com", "notgoogle.io", "googleusercontent.com", ".google.com.evil.io"):
        with pytest.raises(ValueError):
            gcm._normalize_cookies([{"name": "SID", "value": "x", "domain": dom, "path": "/"}])
    ok = gcm._normalize_cookies([{"name": "SID", "value": "x", "domain": ".google.com", "path": "/"},
                                 {"name": "junk", "value": "y", "domain": "google.evil.com", "path": "/"}])
    assert [c["name"] for c in ok] == ["SID"]


# ---- NULL setting after upgrade means ENABLED (what the UI shows) ----------------------------

def test_null_google_checker_enabled_means_enabled(db):
    st = dbm.get_settings(db)
    try:
        st.google_checker_enabled = None; db.commit()
        assert gcm.enabled_in_settings() is True
        assert st.to_dict()["google_checker_enabled"] is True
        st.google_checker_enabled = False; db.commit()
        assert gcm.enabled_in_settings() is False
        # init_db's backfill turns NULL into true
        st.google_checker_enabled = None; db.commit()
        dbm._backfill_google_checker_enabled(db)
        db.expire_all()
        assert dbm.get_settings(db).google_checker_enabled is True
    finally:
        dbm.get_settings(db).google_checker_enabled = True; db.commit()


# ---- honest verification reporting ---------------------------------------------------------

def test_non_google_product_gets_no_verification_note(db, fresh_reseller, monkeypatch):
    from agent_core import run_deep_agent_chat
    slug = f"off-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"OfficeH {slug}", slug=slug, base_price=1, margin_percent=0, reseller_margin_percent=0)
    db.add(p); db.commit()
    db.add(dbm.InviteLink(product_id=p.id, link_or_key=f"OFFICE365-KEY-{uuid.uuid4().hex[:8]}")); db.commit()
    monkeypatch.setattr(gcm, "is_ready", lambda: True)       # checker connected...
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: pytest.fail("browser used for a non-Google key"))
    out = run_deep_agent_chat(f"wa_h_{fresh_reseller.phone}", f"{p.name} ki link do",
                              platform="whatsapp", owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    assert "OFFICE365-KEY" in out["message"]
    assert "verify" not in out["message"].lower()             # ...but nothing was checked, so say nothing
    assert not any(t["tool"] == "link_check" for t in out["metadata"]["tool_calls"])


def test_multi_link_claim_verifies_every_delivered_link(db, fresh_reseller, monkeypatch):
    p, links = _google_product(db, n_links=3)
    seen = []
    monkeypatch.setattr(gcm, "is_ready", lambda: True)
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: (seen.append(u), gcm.CheckResult("fresh", "ok"))[1])
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 2, db)
    assert res["success"] and res["links"] == links[:2]
    assert seen == links[:2]                                   # each delivered link was opened, the 3rd was not
    v = res["link_verification"]
    assert v["method"] == "browser" and v["verified_fresh"] is True and v["links_health"] == ["fresh", "fresh"]


def test_verified_fresh_requires_a_browser_verdict_on_each_link(db, fresh_reseller, monkeypatch):
    p, links = _google_product(db, n_links=2)
    # Pretend the 2nd link already carries a stale HTTP-era health='fresh' in the DB.
    db.query(dbm.InviteLink).filter_by(link_or_key=links[1]).update({"health": "fresh"}); db.commit()
    monkeypatch.setattr(gcm, "is_ready", lambda: True)
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False:
                        gcm.CheckResult("fresh", "ok") if u == links[0] else gcm.CheckResult("busy", "busy"))
    monkeypatch.setattr(link_checker, "_http_probe", lambda u: "unknown")
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 2, db)
    assert res["success"] and res["links"] == links
    v = res["link_verification"]
    assert v["method"] == "browser" and v["verified_fresh"] is False and v["links_health"] == ["fresh", "unknown"]


def test_ensure_fresh_stock_respects_time_budget(db, monkeypatch):
    p, links = _google_product(db, n_links=2)
    monkeypatch.setattr(link_checker, "check_link_freshness_detail",
                        lambda u, allow_browser=True: pytest.fail("checked after the budget ran out"))
    res = dbm.ensure_fresh_stock(db, p.id, count=2, budget_seconds=0)   # budget already spent
    assert res["checked"] == 0 and res["method"] == "none" and len(res["passed_ids"]) == 2


# ---- HTTP fallback + admin bulk recheck ------------------------------------------------------

def test_http_fallback_only_when_browser_inconclusive(monkeypatch):
    url = "https://one.google.com/activate-plan/subscription/new/FALLBACK1"
    calls = []
    monkeypatch.setattr(gcm, "is_ready", lambda: True)
    monkeypatch.setattr(link_checker, "_http_probe", lambda u: (calls.append(u), "used")[1])
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult("busy", "busy"))
    assert link_checker.check_link_freshness_detail(url) == ("used", "browser-fallback") and calls == [url]
    calls.clear()
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult("fresh", "ok"))
    assert link_checker.check_link_freshness_detail(url) == ("fresh", "browser") and calls == []
    # allow_browser=False never touches the browser
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: pytest.fail("browser used"))
    assert link_checker.check_link_freshness_detail(url, allow_browser=False) == ("used", "http")


def test_bulk_recheck_uses_http_probe_for_large_batches(client, admin_headers, db, monkeypatch):
    p_big, _ = _google_product(db, n_links=6)
    p_small, _ = _google_product(db, n_links=2)
    seen = {}
    monkeypatch.setattr(link_checker, "check_link_freshness",
                        lambda u, allow_browser=True: (seen.__setitem__(u, allow_browser), "unknown")[1])
    r = client.post("/api/admin/inventory/recheck", json={"product_id": p_big.id}, headers=admin_headers)
    assert r.status_code == 200 and len(seen) == 6 and not any(seen.values())      # 6 links -> HTTP only
    seen.clear()
    r = client.post("/api/admin/inventory/recheck", json={"product_id": p_small.id}, headers=admin_headers)
    assert r.status_code == 200 and len(seen) == 2 and all(seen.values())          # 2 links -> browser allowed


# ---- verify_session is honest when the browser did not run ----------------------------------

def test_verify_session_inconclusive_when_rate_limited_or_busy(tmp_path, monkeypatch):
    monkeypatch.setattr(gcm, "CHECKER_DIR", tmp_path)
    monkeypatch.setattr(gcm, "STATUS_FILE", tmp_path / "status.json")
    gcm._write_status(logged_in=False)
    for st in ("rate_limited", "busy", "error"):
        monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False, st=st: gcm.CheckResult(st, st))
        r = gcm.verify_session()
        assert r.status == st
        assert gcm._read_status().get("logged_in") is False      # never flipped to True without a rendered page
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult("unknown", "", ""))
    assert gcm.verify_session().status == "unknown"              # no final_url -> inconclusive too


def test_probe_checks_never_trip_the_sale_circuit_breaker(monkeypatch, tmp_path):
    monkeypatch.setattr(gcm, "CHECKER_DIR", tmp_path)
    monkeypatch.setattr(gcm, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(gcm, "playwright_installed", lambda: True)
    monkeypatch.setattr(gcm, "session_present", lambda: True)
    monkeypatch.setattr(gcm, "enabled_in_settings", lambda: True)
    monkeypatch.setattr(gcm, "browser_available", lambda: True)
    monkeypatch.setattr(gcm, "_run_browser_check", lambda u: gcm.CheckResult("error", "boom"))
    gcm._DOWN["until"] = 0.0
    try:
        r = gcm.check_link("https://one.google.com/activate-plan/subscription/new/PROBE1", force=True, probe=True)
        assert r.status == "error" and gcm._down_result() is None          # admin probe: no cooldown
        r = gcm.check_link("https://one.google.com/activate-plan/subscription/new/SALE1")
        assert r.status == "error" and gcm._down_result() is not None      # real sale check: cooldown engaged
    finally:
        gcm._DOWN["until"] = 0.0
        gcm._DOWN["status"] = None


# ---- admin can see WHY a Gemini link went out unverified ------------------------------------

def test_unverified_google_link_records_skipped_reason_for_admin(db, fresh_reseller, monkeypatch):
    from agent_core import run_deep_agent_chat
    p, links = _google_product(db, n_links=1)
    monkeypatch.setattr(gcm, "is_ready", lambda: False)
    monkeypatch.setattr(gcm, "not_ready_reason", lambda: "no Google session connected (test)")
    monkeypatch.setattr(link_checker, "_http_probe", lambda u: "unknown")
    out = run_deep_agent_chat(f"wa_s_{fresh_reseller.phone}", f"{p.name} ki link do",
                              platform="whatsapp", owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    assert links[0] in out["message"] and "verify" not in out["message"].lower()      # buyer: link, no noise
    chips = [t for t in out["metadata"]["tool_calls"] if t["tool"] == "link_check"]
    assert chips and chips[0]["ok"] is False and chips[0]["detail"].startswith("skipped: no Google session")


def test_not_ready_reason_explains_each_blocker(monkeypatch, tmp_path):
    monkeypatch.setattr(gcm, "CHECKER_DIR", tmp_path)
    monkeypatch.setattr(gcm, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(gcm, "playwright_installed", lambda: False)
    assert "playwright" in gcm.not_ready_reason()
    monkeypatch.setattr(gcm, "playwright_installed", lambda: True)
    monkeypatch.setattr(gcm, "browser_available", lambda: False)
    assert "Chromium" in gcm.not_ready_reason()
    monkeypatch.setattr(gcm, "browser_available", lambda: True)
    monkeypatch.setattr(gcm, "session_present", lambda: False)
    assert "session" in gcm.not_ready_reason()
    monkeypatch.setattr(gcm, "session_present", lambda: True)
    monkeypatch.setattr(gcm, "enabled_in_settings", lambda: True)
    gcm._write_status(logged_in=False)
    assert "expired" in gcm.not_ready_reason()
    gcm._write_status(logged_in=True)
    assert gcm.not_ready_reason() is None
