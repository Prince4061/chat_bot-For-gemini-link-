"""Admin authentication, session scoping, reseller lockout and validation."""
import database as dbm


def test_admin_endpoints_require_token(client, admin_headers):
    assert client.get("/api/admin/metrics").status_code == 401
    assert client.get("/api/admin/metrics", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.get("/api/admin/metrics", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/metrics", headers={"Authorization": f"Bearer {admin_headers['X-Admin-Token']}"}).status_code == 200


def test_admin_login(client, admin_headers):
    assert client.post("/api/admin/login", json={"token": "nope"}).status_code == 401
    assert client.post("/api/admin/login", json={"token": admin_headers["X-Admin-Token"]}).get_json()["ok"] is True


def test_settings_never_leak_secrets(client, admin_headers, db):
    s = dbm.get_settings(db)
    s.openai_api_key = "sk-secret-value-123456789"
    s.evolution_api_key = "EVOKEY1234567890"
    db.commit()
    data = client.get("/api/admin/settings", headers=admin_headers).get_json()
    assert data["openai_api_key"].startswith("••••") and "sk-secret" not in data["openai_api_key"]
    assert data["evolution_api_key"].startswith("••••")

    # Echoing the masked value back must not overwrite the stored secret.
    client.post("/api/admin/settings", json={"openai_api_key": data["openai_api_key"], "business_name": "X"}, headers=admin_headers)
    db.expire_all()
    assert dbm.get_settings(db).openai_api_key == "sk-secret-value-123456789"

    # Clean up so later tests keep using the rule engine (empty key -> no LLM calls).
    client.post("/api/admin/settings", json={"openai_api_key": ""}, headers=admin_headers)
    db.expire_all()
    assert dbm.get_settings(db).openai_api_key is None


def test_chat_sessions_are_scoped_per_client(client, client_headers):
    other = {"X-Client-Id": "web_pytest_client_002"}
    r = client.post("/api/chat", json={"session_id": "chat_scope_1", "message": "hi"}, headers=client_headers)
    assert r.status_code == 200
    mine = [s["id"] for s in client.get("/api/chat/sessions", headers=client_headers).get_json()]
    theirs = [s["id"] for s in client.get("/api/chat/sessions", headers=other).get_json()]
    assert "chat_scope_1" in mine and "chat_scope_1" not in theirs
    assert client.get("/api/chat/history/chat_scope_1", headers=other).status_code == 403
    assert client.post("/api/chat", json={"session_id": "chat_scope_1", "message": "hi"}, headers=other).status_code == 403
    assert client.get("/api/chat/sessions").get_json() == []  # no client id -> nothing


def test_reseller_lockout_after_failed_attempts(db, fresh_reseller):
    for _ in range(2):
        ok, _, msg = dbm.verify_reseller_auth(fresh_reseller.phone, "0000", db=db)
        assert not ok and "attempt" in msg
    ok, _, msg = dbm.verify_reseller_auth(fresh_reseller.phone, "0000", db=db)
    assert not ok and "locked" in msg.lower()
    # Even the correct code is refused while locked.
    ok, _, msg = dbm.verify_reseller_auth(fresh_reseller.phone, "4321", db=db)
    assert not ok and "locked" in msg.lower()


def test_correct_code_resets_failed_attempts(db, fresh_reseller):
    dbm.verify_reseller_auth(fresh_reseller.phone, "0000", db=db)
    ok, reseller, _ = dbm.verify_reseller_auth(fresh_reseller.phone, "4321", db=db)
    assert ok and reseller.failed_attempts == 0


def test_reseller_validation(client, admin_headers, fresh_product):
    assert client.post("/api/admin/resellers", json={"phone": "123", "secret_code": "1234"}, headers=admin_headers).status_code == 400
    assert client.post("/api/admin/resellers", json={"phone": "9000000001", "secret_code": "12"}, headers=admin_headers).status_code == 400
    # Money wallet with currency
    assert client.post("/api/admin/resellers", json={"name": "A", "phone": "9000000001", "secret_code": "1234", "currency": "EUR"}, headers=admin_headers).status_code == 400
    r = client.post("/api/admin/resellers", json={"name": "A", "phone": "9000000001", "secret_code": "1234", "wallet_balance": 250.5, "currency": "INR"}, headers=admin_headers)
    assert r.status_code == 201
    body = r.get_json()
    assert body["wallet_balance"] == 250.5 and body["currency"] == "INR" and body["wallet_display"] == "₹250.50"
    assert client.post("/api/admin/resellers", json={"name": "B", "phone": "9000000001", "secret_code": "1234"}, headers=admin_headers).status_code == 409
    rid = body["id"]
    # deducting more than the balance is rejected; top-up works; ledger records it
    assert client.post(f"/api/admin/resellers/{rid}/wallet", json={"amount": -999}, headers=admin_headers).status_code == 400
    ok = client.post(f"/api/admin/resellers/{rid}/wallet", json={"amount": 749.5, "note": "UPI UTR 1"}, headers=admin_headers).get_json()
    assert ok["new_balance"] == 1000.0 and ok["balance_display"] == "₹1,000.00"
    ledger = client.get(f"/api/admin/resellers/{rid}/transactions", headers=admin_headers).get_json()
    assert [t["amount"] for t in ledger] == [749.5, 250.5] and ledger[0]["reference_note"] == "UPI UTR 1"
    # currency can be switched by the admin
    assert client.put(f"/api/admin/resellers/{rid}", json={"currency": "USD"}, headers=admin_headers).get_json()["currency"] == "USD"


def test_bulk_upload_skips_duplicates(client, admin_headers, fresh_product):
    body = {"product_id": fresh_product.id, "links_text": "https://example.com/new1\nhttps://example.com/new1\n" + f"https://example.com/{fresh_product.slug}/0"}
    r = client.post("/api/admin/inventory/bulk-upload", json=body, headers=admin_headers).get_json()
    assert r["added_count"] == 1 and r["skipped_duplicates"] == 2


def test_claimed_links_can_be_deleted(client, admin_headers, db, fresh_product):
    # Admin is allowed to delete a claimed link (they own their data).
    ok, link, _ = dbm.claim_single_use_link(fresh_product.id, "customer", "x", None, db=db)
    assert ok
    link_id = link.id  # capture before the row is deleted
    assert client.delete(f"/api/admin/inventory/{link_id}", headers=admin_headers).status_code == 200
    db.expire_all()
    assert db.query(dbm.InviteLink).filter_by(id=link_id).first() is None


def test_webhook_secret_enforced(client, monkeypatch):
    import app as app_module
    from config import Config
    monkeypatch.setattr(Config, "EVOLUTION_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr(app_module, "send_whatsapp_message", lambda **kw: {"success": True})
    payload = {"event": "messages.upsert", "data": {"key": {"remoteJid": "919876500000@s.whatsapp.net", "fromMe": False, "id": "X1"}, "message": {"conversation": "hi"}}}
    assert client.post("/api/webhook/evolution", json=payload).status_code == 401
    assert client.post("/api/webhook/evolution?token=hook-secret", json=payload).status_code == 202
    assert client.post("/api/webhook/evolution?token=hook-secret", json=payload).get_json()["status"] == "duplicate"
