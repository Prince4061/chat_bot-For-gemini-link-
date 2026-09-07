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
    assert db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance == 400.0   # ₹500 - ₹100


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
        bal = json.loads(agent_tools.check_reseller_balance.invoke({}))
        assert bal["wallet_balance"] == 400.0 and bal["balance_display"] == "₹400.00"
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


def test_whatsapp_registered_number_auto_verifies_reseller(db, fresh_product, fresh_reseller):
    from agent_core import run_deep_agent_chat
    sid = f"wa_{fresh_reseller.phone}"
    # No phone/passcode in the message - identity comes from the WhatsApp sender number.
    out = run_deep_agent_chat(sid, "balance batao", platform="whatsapp",
                              owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    assert out["success"]
    db.expire_all()
    rec = db.query(dbm.ChatSessionRecord).filter_by(id=sid).first()
    assert rec.reseller_id == fresh_reseller.id and rec.user_type == "reseller"
    # And claiming needs no passcode either.
    out2 = run_deep_agent_chat(sid, f"{fresh_product.name} ki link do", platform="whatsapp",
                               owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    assert "Claimed & Burned" in out2["message"] or "link" in out2["message"].lower()


def test_whatsapp_clears_stale_reseller_link_for_unregistered_number(db, fresh_reseller):
    """An unregistered number whose session was previously (wrongly) linked to a reseller
    must be cleared automatically on the next message — no reseller name/balance shown."""
    from agent_core import run_deep_agent_chat
    sid = "wa_5559998888"          # this number is NOT a reseller
    # Simulate the old-bug state: session linked to a real reseller.
    db.add(dbm.ChatSessionRecord(id=sid, platform="whatsapp", customer_phone="5559998888",
                                 reseller_id=fresh_reseller.id, reseller_phone=fresh_reseller.phone,
                                 user_type="reseller"))
    db.commit()
    out = run_deep_agent_chat(sid, "balance batao", platform="whatsapp",
                              owner_id="wa:5559998888", customer_phone="5559998888")
    db.expire_all()
    rec = db.query(dbm.ChatSessionRecord).filter_by(id=sid).first()
    assert rec.reseller_id is None and rec.user_type == "customer"
    assert fresh_reseller.name not in out["message"]


def test_whatsapp_registered_reseller_hi_shows_name_and_balance(db, fresh_product, fresh_reseller):
    """A registered number saying just 'hi' gets 'Hello <name> sir! Aapke paas ₹500 balance hai' — no need to ask."""
    from agent_core import run_deep_agent_chat
    sid = f"wa_hi_{fresh_reseller.phone}"
    out = run_deep_agent_chat(sid, "hi", platform="whatsapp",
                              owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    msg = out["message"]
    assert fresh_reseller.name.split()[0] in msg                      # greeted by first name ("Hello Test sir")
    assert "₹500.00" in msg and "balance" in msg.lower() and "link chahiye" in msg.lower()
    assert "Link prices" in msg and "₹" in msg.split("Link prices", 1)[1]   # per-link reseller prices listed


def test_quantity_parsed_when_number_precedes_product_name(db, fresh_product, fresh_reseller):
    """'2 <product> links do' must mean quantity 2 (₹200), not 1. With ₹500 it succeeds and
    charges for two; with only ₹150 left it is refused instead of silently giving one link."""
    from agent_core import run_deep_agent_chat
    sid = f"wa_qty_{fresh_reseller.phone}"
    kw = dict(platform="whatsapp", owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    out = run_deep_agent_chat(sid, f"2 {fresh_product.name} links do", **kw)["message"]
    assert "× 2" in out and "₹200.00" in out and "₹300.00" in out            # 2 links, ₹500 -> ₹300
    for i in range(3):                                                         # restock so only money can block
        db.add(dbm.InviteLink(product_id=fresh_product.id, link_or_key=f"https://example.com/{fresh_product.slug}/extra{i}"))
    db.commit()
    # Deduct with a STALE in-memory object (still thinks ₹500): the wallet must still be adjusted
    # atomically against the real DB value (₹300), never overwritten from memory.
    res = dbm.adjust_reseller_wallet(db, fresh_reseller, -150)
    assert res["success"] and res["new_balance"] == 150.0                     # ₹300 - ₹150, not ₹500 - ₹150
    out = run_deep_agent_chat(sid, f"2 {fresh_product.name} links do", **kw)["message"]
    assert "failed" in out.lower() and "₹200.00" in out                        # needs ₹200, has ₹150
    db.refresh(fresh_reseller)
    assert fresh_reseller.wallet_balance == 150.0                              # nothing deducted


def test_whatsapp_customer_hi_asks_which_product_and_lists_catalogue(db):
    """Unregistered WhatsApp number = customer: 'hi' -> ask which product + products from admin DB.
    Must NOT ask 'customer ya reseller', and must not mention passcodes."""
    from agent_core import run_deep_agent_chat
    out = run_deep_agent_chat("wa_5550002222", "hi", platform="whatsapp",
                              owner_id="wa:5550002222", customer_phone="5550002222")["message"]
    assert "kaunsa product" in out.lower()
    assert "Gemini Advanced" in out and "₹" in out          # live catalogue from the DB
    assert "Reseller?" not in out and "passcode" not in out.lower()


def test_whatsapp_unregistered_number_gets_contact_guidance(db):
    from agent_core import run_deep_agent_chat
    s = dbm.get_settings(db); s.admin_contact_number = "+919000000123"; db.commit()
    out = run_deep_agent_chat("wa_5550001111", "mujhe reseller credits chahiye", platform="whatsapp",
                              owner_id="wa:5550001111", customer_phone="5550001111")
    assert "+919000000123" in out["message"]
    db.expire_all()
    rec = db.query(dbm.ChatSessionRecord).filter_by(id="wa_5550001111").first()
    assert rec.reseller_id is None  # never auto-verified


def test_catalog_tool_reports_live_margin(db, fresh_product):
    fresh_product.margin_percent = 100.0
    db.commit()
    data = json.loads(agent_tools.get_product_pricing.invoke({"product_name_or_slug": fresh_product.slug}))
    assert data["customer_selling_price_inr"] == 200.0
