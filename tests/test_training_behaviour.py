"""AI Training end-to-end: the bot answers exactly as trained — on the rule engine AND before the
LLM — without ever hijacking money/link transactions."""
import uuid

import pytest
from langchain_core.messages import AIMessage

import agent_core
import database as dbm


@pytest.fixture(autouse=True)
def _clean_kb(db):
    """Tests share one DB: park every earlier trained entry so same-keyword entries can't tie."""
    db.query(dbm.KnowledgeEntry).update({"is_active": False}, synchronize_session=False)
    db.commit()
    yield


def _kb(db, q, a, kw="", priority=5):
    e = dbm.KnowledgeEntry(question=q, answer=a, keywords=kw, priority=priority)
    db.add(e); db.commit(); db.refresh(e)
    return e


def _product(db, name=None, stock=2, **kw):
    slug = f"tr-{uuid.uuid4().hex[:6]}"
    name = name or f"Zeta Plan {slug[-4:]}"
    p = dbm.Product(name=name, slug=slug, base_price=1, margin_percent=0, reseller_margin_percent=0, **kw)
    db.add(p); db.commit()
    for i in range(stock):
        db.add(dbm.InviteLink(product_id=p.id, link_or_key=f"ZETA-KEY-{uuid.uuid4().hex[:8]}"))
    db.commit(); db.refresh(p)
    return p


def _chat(msg, sid=None, **kw):
    return agent_core.run_deep_agent_chat(sid or f"tr_{uuid.uuid4().hex[:8]}", msg, **kw)


def _kb_used(out):
    return any(t["tool"] == "knowledge_base" for t in out["metadata"]["tool_calls"])


# ---- trained answers beat the generic flows, but never transactions --------------------------

def test_how_to_question_about_a_product_uses_trained_answer_not_order_flow(db):
    p = _product(db)
    _kb(db, f"{p.name} kaise activate kare?", "Link kholo, Google login karo, Activate dabao.", "kaise activate, activate, activation")
    out = _chat(f"{p.name.lower()} kaise activate kare")
    assert "Activate dabao" in out["message"] and _kb_used(out)
    assert db.query(dbm.CustomerOrder).filter_by(session_id=out["session_id"]).count() == 0   # no order created


def test_price_question_still_shows_live_price_card(db):
    p = _product(db)
    _kb(db, "Price kya hai?", "Prices catalogue me dekho.", "price")          # weak, single word
    out = _chat(f"{p.name.lower()} ka price kya hai")
    assert "Customer price" in out["message"] and not _kb_used(out)


def test_kya_hai_faq_is_not_hijacked_by_catalogue(db):
    _kb(db, "Refund policy?", "Refund sirf tab jab link kaam na kare (24h).", "refund, paisa wapas")
    out = _chat("refund policy kya hai")
    assert "Refund sirf tab" in out["message"] and _kb_used(out)


def test_utr_is_never_intercepted_by_a_trained_answer(db):
    p = _product(db)
    _kb(db, "Payment done?", "Payment ke baad UTR bhejo.", "payment done, paid")
    sid = f"tr_utr_{uuid.uuid4().hex[:6]}"
    _chat(f"buy {p.name.lower()}", sid=sid)                                   # creates the pending order
    ref = str(uuid.uuid4().int)[:12]                                          # unique UTR (shared test DB)
    out = _chat(f"payment done {ref}", sid=sid)
    assert "ZETA-KEY-" in out["message"] and not _kb_used(out)              # link delivered, FAQ ignored


def test_verified_reseller_claim_vs_question(db, fresh_reseller):
    p = _product(db)
    _kb(db, "Kaise activate kare?", "Activate steps: login -> Activate.", "kaise activate, activate")
    kw = dict(platform="whatsapp", owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    sid = f"wa_tr_{fresh_reseller.phone}"
    before = db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance
    q = _chat(f"{p.name.lower()} kaise activate kare", sid=sid, **kw)      # a QUESTION -> trained answer
    assert "Activate steps" in q["message"]
    db.expire_all()
    assert db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance == before   # nothing burned/charged
    c = _chat(f"{p.name.lower()} link do", sid=sid, **kw)                  # a CLAIM -> link delivered
    assert "ZETA-KEY-" in c["message"] and not _kb_used(c)


def test_reseller_greeting_beats_custom_greeting_entry(db, fresh_reseller):
    _kb(db, "Greeting", "Namaste ji! Kaise madad karu?", "hi, hello, namaste")
    out = _chat("hi", sid=f"wa_g_{fresh_reseller.phone}", platform="whatsapp",
                owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    assert "balance" in out["message"].lower() and not _kb_used(out)      # wallet fact wins for resellers
    cust = _chat("hi")                                                       # plain web customer -> custom greeting
    assert "Namaste ji" in cust["message"] and _kb_used(cust)


# ---- matching quality ---------------------------------------------------------------------

def test_prefix_and_typo_tolerant_matching(db):
    _kb(db, "Refund?", "Refund rule: 24h.", "refund")
    _kb(db, "Delivery?", "Delivery: 1 minute.", "delivery")
    assert dbm.match_knowledge(db, "refunds ka kya rule hai").answer == "Refund rule: 24h."      # plural / prefix
    assert dbm.match_knowledge(db, "delivry kab hogi").answer == "Delivery: 1 minute."          # typo
    assert dbm.match_knowledge(db, "gemini ka rate kya hai") is None                             # unrelated


def test_phrase_keyword_is_strong_single_word_is_weak(db):
    _kb(db, "Activate?", "A", "kaise activate")
    _kb(db, "Warranty?", "W", "warranty")
    assert dbm.match_knowledge_detail(db, "ye kaise activate hoga")["strong"] is True
    assert dbm.match_knowledge_detail(db, "warranty hai?")["strong"] is False
    assert dbm.match_knowledge_detail(db, "warranty aur guarantee dono?")["strong"] is False


def test_multiline_question_variants_derive_keywords(db):
    _kb(db, "Warranty kitni hai?\nGuarantee milti hai kya?", "30 din warranty.")   # no explicit keywords
    m = dbm.match_knowledge_detail(db, "bhai guarantee milegi?")
    assert m and m["entry"].answer == "30 din warranty." and any("guarantee" in k for k in m["matched"])


def test_placeholders_render_from_live_settings(db):
    st = dbm.get_settings(db)
    st.admin_upi_id = "shop@upi"; st.business_name = "Prince Store"; db.commit()
    _kb(db, "Pay kaise?", "Pay to {upi_id} — {business_name}. Baaki {unknown} same.", "pay kaise")
    out = _chat("pay kaise karu")
    assert "Pay to shop@upi — Prince Store" in out["message"] and "{unknown}" in out["message"]
    # a blank Setting falls back to a neutral word instead of leaving a hole
    st.admin_contact_number = ""; db.commit()
    assert dbm.render_knowledge_answer("Call {admin_contact} ji", st) == "Call admin ji"
    assert dbm.empty_placeholders("Call {admin_contact} / {upi_id}", st) == ["admin_contact"]


# ---- same behaviour with the LLM available -----------------------------------------------------

class _FakeAgent:
    def invoke(self, payload):
        return {"messages": [AIMessage(content="LLM SAYS")], "todos": []}


def test_strong_match_is_answered_before_the_llm_weak_goes_to_llm(db, monkeypatch):
    monkeypatch.setattr(agent_core, "get_deep_agent", lambda: _FakeAgent())
    _kb(db, "Activate?", "TRAINED ACTIVATE ANSWER", "kaise activate")
    _kb(db, "Warranty?", "TRAINED WARRANTY", "warranty")
    strong = _chat("ye kaise activate hoga")
    assert strong["message"] == "TRAINED ACTIVATE ANSWER" and strong["metadata"]["engine"] == "knowledge_base"
    weak = _chat("warranty hai kya")
    assert weak["message"] == "LLM SAYS" and weak["metadata"]["engine"] == "deep_agent"   # LLM has the FAQ in prompt


def test_system_prompt_contains_instructions_and_faq(db):
    st = dbm.get_settings(db)
    st.agent_instructions = "Hamesha 'ji' laga ke baat karo."; db.commit()
    _kb(db, "Office timing?", "10am-8pm", "timing")
    prompt = agent_core.build_full_system_prompt(db)
    assert "Hamesha 'ji' laga ke baat karo." in prompt and "Q: Office timing?" in prompt and "A: 10am-8pm" in prompt
    st.agent_instructions = ""; db.commit()


# ---- admin Test box tells the truth ----------------------------------------------------------------

def test_knowledge_test_endpoint_reports_decision(client, admin_headers, db):
    p = _product(db)
    _kb(db, "Price?", "See catalogue", "price")
    r = client.post("/api/admin/knowledge/test", json={"question": f"{p.name.lower()} ka price kya hai"}, headers=admin_headers).get_json()
    assert r["matched"] and r["decision"] == "kb_fallback" and "product" in r["reason"] and r["matched_keywords"] == ["price"]
    r2 = client.post("/api/admin/knowledge/test", json={"question": "payment done 445566778800"}, headers=admin_headers).get_json()
    assert r2["decision"] in ("builtin", "none")
    _kb(db, "Activate?", "Steps for {business_name}", "kaise activate")
    r3 = client.post("/api/admin/knowledge/test", json={"question": f"{p.name.lower()} kaise activate kare"}, headers=admin_headers).get_json()
    assert r3["decision"] == "kb" and r3["strong"] and "{business_name}" not in r3["rendered_answer"]
    assert r3["engine"] in ("deep_agent", "rule_based_fallback")


# ---- supplier-backed products are sellable in the rule engine ----------------------------------

def test_supplier_product_is_orderable_and_listed_available(db, monkeypatch):
    import moonshots_service as ms
    monkeypatch.setattr(ms, "is_ready", lambda: True)
    p = _product(db, stock=0, source="moonshots", supplier_product_id=42)
    out = _chat(f"buy {p.name.lower()}")
    assert "Order" in out["message"] and "out of stock" not in out["message"].lower()
    cat = _chat(f"{p.name.lower()} price")
    assert "available" in cat["message"].lower()
