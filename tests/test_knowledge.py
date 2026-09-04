"""Admin-trained FAQ: matching, CRUD, and use in the rule-engine reply."""
import database as dbm


def test_match_knowledge_by_keywords(db):
    e = dbm.KnowledgeEntry(question="Delivery kitni der me?", answer="Payment ke turant baad, 1 min me.",
                           keywords="delivery, kitni der, kab milega", priority=5)
    db.add(e); db.commit()
    assert dbm.match_knowledge(db, "bhai delivery kitni der me hogi").id == e.id
    assert dbm.match_knowledge(db, "mera link kab milega").id == e.id
    assert dbm.match_knowledge(db, "gemini ka rate kya hai") is None  # unrelated


def test_inactive_entry_not_matched(db):
    e = dbm.KnowledgeEntry(question="Refund policy?", answer="No refund.", keywords="refund", is_active=False)
    db.add(e); db.commit()
    assert dbm.match_knowledge(db, "refund milega kya") is None


def test_rule_engine_uses_trained_answer(db):
    from agent_core import run_deep_agent_chat
    db.add(dbm.KnowledgeEntry(question="Kya aap safe ho?", answer="Haan, 100% trusted seller, 5000+ orders.",
                              keywords="safe, trusted, genuine, scam", priority=10))
    db.commit()
    out = run_deep_agent_chat("chat_kb_1", "bhai ye safe hai ya scam?")
    assert "trusted" in out["message"].lower()


def test_knowledge_crud_endpoints(client, admin_headers):
    r = client.post("/api/admin/knowledge",
                    json={"question": "Payment kaise?", "answer": "UPI se.", "keywords": "payment, kaise pay"},
                    headers=admin_headers)
    assert r.status_code == 201
    eid = r.get_json()["id"]
    assert any(k["id"] == eid for k in client.get("/api/admin/knowledge", headers=admin_headers).get_json())
    # test endpoint
    t = client.post("/api/admin/knowledge/test", json={"question": "payment kaise karu"}, headers=admin_headers).get_json()
    assert t["matched"] and t["entry"]["id"] == eid
    # update + delete
    assert client.put(f"/api/admin/knowledge/{eid}", json={"answer": "Sirf UPI."}, headers=admin_headers).status_code == 200
    assert client.delete(f"/api/admin/knowledge/{eid}", headers=admin_headers).status_code == 200


def test_agent_instructions_saved_via_settings(client, admin_headers, db):
    client.post("/api/admin/settings", json={"agent_instructions": "Always be polite. Refund in 24h."}, headers=admin_headers)
    db.expire_all()
    assert "Refund in 24h" in dbm.get_settings(db).agent_instructions
