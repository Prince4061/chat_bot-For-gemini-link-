"""Admin Bot Tester endpoint: real bot turn + debug info, both modes, and session reset."""
import database as dbm


def test_bot_tester_web_customer_flow_with_debug(client, admin_headers, fresh_product):
    r = client.post("/api/admin/bot/test", json={"message": f"mujhe {fresh_product.name} chahiye", "mode": "web"}, headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] and body["session_id"].startswith("test_web_")
    assert "ORD-" in body["reply"]
    assert body["engine"] in ("rule_based", "rule_based_fallback", "deep_agent", "deep_agent_partial")
    assert body["elapsed_ms"] >= 0 and "engine" in body["agent"]
    assert body["session"]["pending_order"]["product"] == fresh_product.name   # session state visible

    # Same session continues: pay -> link delivered, pending order cleared.
    r2 = client.post("/api/admin/bot/test", json={"message": "paid 445566778899", "mode": "web", "session_id": body["session_id"]}, headers=admin_headers)
    b2 = r2.get_json()
    assert "https://example.com/" in b2["reply"] and b2["session"]["pending_order"] is None


def test_bot_tester_whatsapp_mode_auto_verifies_reseller(client, admin_headers, fresh_reseller, fresh_product):
    r = client.post("/api/admin/bot/test", json={"message": "hi", "mode": "whatsapp", "phone": fresh_reseller.phone}, headers=admin_headers)
    body = r.get_json()
    assert body["session_id"].startswith("test_whatsapp_")
    assert body["session"]["reseller"]["name"] == fresh_reseller.name          # identified by number, no code
    assert body["session"]["reseller"]["balance"] == "₹500.00" and body["session"]["reseller"]["currency"] == "INR"
    assert fresh_reseller.name.split()[0] in body["reply"]           # "Hello <first name> sir!"


def test_bot_tester_shows_matched_faq_and_resets(client, admin_headers, db):
    db.add(dbm.KnowledgeEntry(question="Delivery time?", answer="Turant, 1 minute me.", keywords="delivery, kitni der"))
    db.commit()
    r = client.post("/api/admin/bot/test", json={"message": "delivery kitni der me?", "mode": "web"}, headers=admin_headers).get_json()
    assert r["kb_match"]["question"] == "Delivery time?"
    assert any(t["tool"] == "knowledge_base" for t in r["tool_calls"])   # FAQ actually answered
    assert "1 minute" in r["reply"]

    sid = r["session_id"]
    assert client.post("/api/admin/bot/test/reset", json={"session_id": sid}, headers=admin_headers).get_json()["success"]
    assert db.query(dbm.ChatSessionRecord).filter_by(id=sid).first() is None
    # Only tester sessions can be reset through this endpoint.
    assert client.post("/api/admin/bot/test/reset", json={"session_id": "wa_9876543210"}, headers=admin_headers).status_code == 400


def test_bot_tester_validation(client, admin_headers):
    assert client.post("/api/admin/bot/test", json={"message": ""}, headers=admin_headers).status_code == 400
    assert client.post("/api/admin/bot/test", json={"message": "hi", "mode": "whatsapp", "phone": "12"}, headers=admin_headers).status_code == 400
