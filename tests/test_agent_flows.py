"""End-to-end conversation flows through the rule engine and session-aware tools."""
import json

import database as dbm
from agent_context import SessionContext, set_session_context, reset_session_context
import agent_tools


def _chat(client, headers, sid, msg):
    r = client.post("/api/chat", json={"session_id": sid, "message": msg}, headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["message"]


def test_customer_flow_order_then_utr_delivers_link(client, client_headers, db, fresh_product):
    sid = f"chat_cust_{fresh_product.slug}"
    reply = _chat(client, client_headers, sid, f"mujhe {fresh_product.name} chahiye")
    assert "ORD-" in reply and "₹150.00" in reply
    order = dbm.get_pending_order_for_session(db, sid)
    assert order is not None and order.product_id == fresh_product.id

    reply = _chat(client, client_headers, sid, "paid, utr 555566667777")
    assert "Single-Use Invite Link" in reply and f"https://example.com/{fresh_product.slug}/" in reply
    db.expire_all()
    order = db.query(dbm.CustomerOrder).filter(dbm.CustomerOrder.id == order.id).first()
    assert order.status == "delivered" and order.payment_ref == "555566667777"


def test_utr_without_pending_order_in_this_session_is_not_fulfilled(client, client_headers, db, fresh_product):
    other_sid = f"chat_other_{fresh_product.slug}"
    _chat(client, client_headers, other_sid, fresh_product.name)  # pending order in another session
    reply = _chat(client, client_headers, "chat_lonely_session", "111122223333")
    assert "couldn't find an unpaid order" in reply
    assert dbm.get_pending_order_for_session(db, other_sid).status == "pending_payment"


def test_reseller_flow_verify_then_claim_without_repeating_code(client, client_headers, db, fresh_product, fresh_reseller):
    sid = f"chat_res_{fresh_reseller.phone}"
    reply = _chat(client, client_headers, sid, f"{fresh_reseller.phone} 4321")
    assert "verified" in reply.lower()
    reply = _chat(client, client_headers, sid, f"{fresh_product.name} ki link do")
    assert "Claimed & Burned" in reply
    db.expire_all()
    assert db.query(dbm.Reseller).get(fresh_reseller.id).credits_balance == 4


def test_tools_remember_verified_reseller(db, fresh_product, fresh_reseller):
    sid = f"tool_sess_{fresh_reseller.phone}"
    db.add(dbm.ChatSessionRecord(id=sid, platform="web"))
    db.commit()
    token = set_session_context(SessionContext(session_id=sid))
    try:
        res = json.loads(agent_tools.verify_reseller_credentials.invoke({"phone": fresh_reseller.phone, "secret_code": "4321"}))
        assert res["authenticated"] is True
        # No phone / code passed: the tool must use the session's verified reseller.
        claim = json.loads(agent_tools.claim_reseller_product_link.invoke({"product_name": fresh_product.slug, "quantity": 1}))
        assert claim["success"], claim
        bal = json.loads(agent_tools.check_reseller_credits.invoke({}))
        assert bal["credits_balance"] == 4
        json.loads(agent_tools.logout_reseller_session.invoke({}))
        claim2 = json.loads(agent_tools.claim_reseller_product_link.invoke({"product_name": fresh_product.slug}))
        assert claim2["error"] == "AUTH_REQUIRED"
    finally:
        reset_session_context(token)


def test_order_tools_are_session_scoped(db, fresh_product):
    sid_a, sid_b = f"tool_a_{fresh_product.slug}", f"tool_b_{fresh_product.slug}"
    db.add_all([dbm.ChatSessionRecord(id=sid_a), dbm.ChatSessionRecord(id=sid_b)])
    db.commit()

    token = set_session_context(SessionContext(session_id=sid_a))
    try:
        created = json.loads(agent_tools.create_customer_order.invoke({"product_name": fresh_product.slug}))
        assert created["status"] == "order_created"
        again = json.loads(agent_tools.create_customer_order.invoke({"product_name": fresh_product.slug}))
        assert again["order_id"] == created["order_id"], "same intent must reuse the pending order"
    finally:
        reset_session_context(token)

    token = set_session_context(SessionContext(session_id=sid_b))
    try:
        res = json.loads(agent_tools.confirm_customer_payment_and_deliver.invoke({"payment_ref": "999988887777", "order_id": created["order_id"]}))
        assert res["status"] == "error", "another session must not be able to fulfil this order"
    finally:
        reset_session_context(token)

    token = set_session_context(SessionContext(session_id=sid_a))
    try:
        res = json.loads(agent_tools.confirm_customer_payment_and_deliver.invoke({"payment_ref": "999988887777"}))
        assert res["status"] == "success" and res["single_use_invite_link"].startswith("https://example.com/")
        status = json.loads(agent_tools.get_order_status.invoke({}))
        assert status["order"]["status"] == "delivered"
    finally:
        reset_session_context(token)


def test_catalog_tool_reports_live_margin(db, fresh_product):
    fresh_product.margin_percent = 100.0
    db.commit()
    data = json.loads(agent_tools.get_product_pricing.invoke({"product_name_or_slug": fresh_product.slug}))
    assert data["customer_selling_price_inr"] == 200.0
