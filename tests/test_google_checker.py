"""Logged-in Google link checker: page classification, session import, admin API, integration."""
import json
import google_checker as gcm
import link_checker


# ---- classification (pure, no browser) -------------------------------------------------

def test_classify_used_english_and_hindi():
    assert gcm.classify_page("The subscription link has already been used to activate the subscription of an eligible Google Account. Explore Google One",
                             "https://one.google.com/activate-plan/x").status == "used"
    assert gcm.classify_page("सदस्यता लिंक पहले ही इस्तेमाल किया जा चुका है", "https://one.google.com/activate-plan/x").status == "used"


def test_classify_expired_fresh_ineligible_unknown():
    assert gcm.classify_page("The subscription link has expired. Return to Partner", "https://one.google.com/a").status == "expired"
    assert gcm.classify_page("Google One AI Premium 2 TB Plan details ... Activate plan", "https://one.google.com/activate-plan/a").status == "fresh"
    assert gcm.classify_page("प्लान की जानकारी ... प्लान चालू करें", "https://one.google.com/activate-plan/a").status == "fresh"
    # Activate button detected by the DOM even if the text scan missed it
    assert gcm.classify_page("Plan details 2 TB", "https://one.google.com/activate-plan/a", has_activate_button=True).status == "fresh"
    # Account can't take the offer -> NOT a used link
    assert gcm.classify_page("You're not eligible for this offer", "https://one.google.com/activate-plan/a").status == "ineligible"
    assert gcm.classify_page("Something completely different", "https://one.google.com/activate-plan/a").status == "unknown"


def test_classify_detects_dead_session():
    assert gcm.classify_page("Sign in - Google Accounts ... Email or phone", "https://accounts.google.com/v3/signin/identifier?continue=x").status == "logged_out"


# ---- session import ------------------------------------------------------------------------

def test_normalize_cookie_editor_export_and_storage_state():
    editor_export = [
        {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/", "expirationDate": 1.9e9, "sameSite": "no_restriction", "secure": True, "httpOnly": False},
        {"name": "__Secure-1PSID", "value": "def", "domain": ".google.com", "path": "/", "sameSite": "lax", "secure": True, "httpOnly": True},
        {"name": "other", "value": "x", "domain": ".example.com", "path": "/"},   # dropped: not Google
    ]
    cookies = gcm._normalize_cookies(editor_export)
    assert [c["name"] for c in cookies] == ["SID", "__Secure-1PSID"]
    assert cookies[0]["sameSite"] == "None" and cookies[0]["expires"] == 1.9e9
    assert cookies[1]["sameSite"] == "Lax" and cookies[1]["expires"] == -1
    # Playwright storage_state form works too
    assert len(gcm._normalize_cookies({"cookies": editor_export, "origins": []})) == 2


def test_normalize_rejects_sessions_without_login_cookies():
    import pytest
    with pytest.raises(ValueError):
        gcm._normalize_cookies([{"name": "NID", "value": "x", "domain": ".google.com", "path": "/"}])


# ---- admin API -------------------------------------------------------------------------------

def test_status_endpoint_and_session_roundtrip(client, admin_headers, tmp_path, monkeypatch):
    # Isolate the checker directory for this test.
    monkeypatch.setattr(gcm, "CHECKER_DIR", tmp_path)
    monkeypatch.setattr(gcm, "STATE_FILE", tmp_path / "google_session.json")
    monkeypatch.setattr(gcm, "PROFILE_DIR", tmp_path / "profile")
    monkeypatch.setattr(gcm, "IMPORT_MARK", tmp_path / "profile" / ".session_imported")
    monkeypatch.setattr(gcm, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(gcm, "playwright_installed", lambda: False)   # no browser in CI

    st = client.get("/api/admin/google-checker/status", headers=admin_headers).get_json()
    assert st["session_present"] is False and st["ready"] is False

    bad = client.post("/api/admin/google-checker/session", json={"session": "not json"}, headers=admin_headers)
    assert bad.status_code == 400

    good = client.post("/api/admin/google-checker/session",
                       json={"session": {"cookies": [{"name": "SID", "value": "v", "domain": ".google.com", "path": "/"}], "origins": []}},
                       headers=admin_headers)
    assert good.status_code == 200 and good.get_json()["saved"]["cookies"] == 1
    assert (tmp_path / "google_session.json").exists()
    assert client.get("/api/admin/google-checker/status", headers=admin_headers).get_json()["session_present"] is True

    assert client.delete("/api/admin/google-checker/session", headers=admin_headers).get_json()["success"]
    assert not (tmp_path / "google_session.json").exists()


def test_settings_toggle_persists(client, admin_headers, db):
    import database as dbm
    client.post("/api/admin/settings", json={"google_checker_enabled": False}, headers=admin_headers)
    db.expire_all()
    assert dbm.get_settings(db).google_checker_enabled is False
    client.post("/api/admin/settings", json={"google_checker_enabled": True}, headers=admin_headers)


# ---- circuit breaker -------------------------------------------------------------------------

def test_cooldown_after_dead_session_skips_browser(monkeypatch):
    monkeypatch.setattr(gcm, "playwright_installed", lambda: True)
    monkeypatch.setattr(gcm, "session_present", lambda: True)
    monkeypatch.setattr(gcm, "enabled_in_settings", lambda: True)
    gcm._mark_down("logged_out", "session expired")
    try:
        r = gcm.check_link("https://one.google.com/activate-plan/subscription/new/X")   # must NOT launch Chrome
        assert r.status == "logged_out" and "retry in" in r.reason
        # An admin-triggered forced check bypasses the cooldown (would launch the browser) — skipped here.
    finally:
        gcm._DOWN["until"] = 0.0


# ---- bot tells the buyer whether the link was live-verified ----------------------------------

def test_reply_mentions_google_live_verification(db, fresh_reseller, monkeypatch):
    import database as dbm, uuid
    from agent_core import run_deep_agent_chat
    slug = f"gemv-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"GeminiV {slug}", slug=slug, base_price=100, margin_percent=0, reseller_margin_percent=0)
    db.add(p); db.commit()
    db.add(dbm.InviteLink(product_id=p.id, link_or_key=f"https://one.google.com/activate-plan/subscription/new/{uuid.uuid4().hex}"))
    db.commit()
    monkeypatch.setattr(gcm, "is_ready", lambda: True)
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult("fresh", "activate button"))
    kw = dict(platform="whatsapp", owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    out = run_deep_agent_chat(f"wa_v_{fresh_reseller.phone}", f"{p.name} ki link do", **kw)
    assert "live verify" in out["message"] and "fresh hai" in out["message"]
    assert any(t["tool"] == "link_check" and t["ok"] for t in out["metadata"]["tool_calls"])

    # Dead session -> link still delivered, but the reply says it was NOT verified.
    db.add(dbm.InviteLink(product_id=p.id, link_or_key=f"https://one.google.com/activate-plan/subscription/new/{uuid.uuid4().hex}"))
    db.commit()
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult("logged_out", "expired"))
    monkeypatch.setattr(link_checker, "_http_probe", lambda u: "unknown")   # no network in tests
    out2 = run_deep_agent_chat(f"wa_v_{fresh_reseller.phone}", f"{p.name} ki link do", **kw)
    assert "verify nahi ho paayi" in out2["message"] and "one.google.com" in out2["message"]


# ---- integration with link_checker / stock ---------------------------------------------------

def test_link_checker_uses_browser_verdict_when_ready(monkeypatch):
    url = "https://one.google.com/activate-plan/subscription/new/TOKEN?g1_landing_page=5"
    monkeypatch.setattr(gcm, "is_ready", lambda: True)
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult("used", "Google says used"))
    assert link_checker.check_link_freshness(url) == "used"
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult("expired", "expired"))
    assert link_checker.check_link_freshness(url) == "used"
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult("fresh", "activate button"))
    assert link_checker.check_link_freshness(url) == "fresh"
    # Dead session / ineligible / unknown / busy must never block a sale -> falls back to the HTTP probe
    monkeypatch.setattr(link_checker, "_http_probe", lambda u: "unknown")   # no network in tests
    for st in ("logged_out", "ineligible", "unknown", "error", "busy", "rate_limited", "disabled"):
        monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False, st=st: gcm.CheckResult(st, st))
        assert link_checker.check_link_freshness(url) == "unknown"
    # ...and the HTTP probe's own 404/410 verdict still counts when the browser was inconclusive
    monkeypatch.setattr(link_checker, "_http_probe", lambda u: "used")
    assert link_checker.check_link_freshness_detail(url) == ("used", "browser-fallback")


def test_reseller_gets_next_fresh_link_when_browser_says_used(db, fresh_reseller, monkeypatch):
    """End-to-end: first two Gemini links are 'used' per the browser, the third is fresh."""
    import database as dbm, uuid
    slug = f"gem-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Gemini {slug}", slug=slug, base_price=100, margin_percent=0, reseller_margin_percent=0)
    db.add(p); db.commit()
    links = [f"https://one.google.com/activate-plan/subscription/new/T{i}{uuid.uuid4().hex[:4]}" for i in range(3)]
    for l in links:
        db.add(dbm.InviteLink(product_id=p.id, link_or_key=l))
    db.commit()
    verdict = {links[0]: "used", links[1]: "expired", links[2]: "fresh"}
    monkeypatch.setattr(gcm, "is_ready", lambda: True)
    monkeypatch.setattr(gcm, "check_link", lambda u, force=False, probe=False: gcm.CheckResult(verdict[u], "mock"))

    res = dbm.process_reseller_claim_for(fresh_reseller, p, 1, db)
    assert res["success"] and res["links"] == [links[2]]
    db.expire_all()
    statuses = {l.link_or_key: l.status for l in db.query(dbm.InviteLink).filter_by(product_id=p.id).all()}
    assert statuses[links[0]] == "used" and statuses[links[1]] == "used" and statuses[links[2]] == "claimed"
