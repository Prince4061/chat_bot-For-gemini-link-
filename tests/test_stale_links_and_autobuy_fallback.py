"""Two live bugs: (1) after a WhatsApp 'clear chat' the LLM re-sent an OLD link from history;
(2) once manually uploaded links were burned, the LLM saw available_stock 0 and never auto-bought."""
import uuid

from langchain_core.messages import AIMessage

import agent_core
import database as dbm
import moonshots_service as ms
import lootpaglu_service as lp


def _gemini(db, stock_links=1, supplier=True):
    slug = f"st-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"GeminiS {slug}", slug=slug, base_price=1, margin_percent=0, reseller_margin_percent=0,
                    source="supplier" if supplier else "stock", supplier_product_id=42 if supplier else None)
    db.add(p); db.commit()
    for i in range(stock_links):
        db.add(dbm.InviteLink(product_id=p.id, link_or_key=f"https://serviceactivation.google.com/subscription/new/MAN{uuid.uuid4().hex}"))
    db.commit(); db.refresh(p)
    return p


def _wa(fresh_reseller):
    return dict(platform="whatsapp", owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)


def _mock_ms(monkeypatch):
    monkeypatch.setattr(ms, "is_ready", lambda: True)
    monkeypatch.setattr(lp, "is_ready", lambda: False)
    monkeypatch.setattr(ms, "product_summary", lambda pid, rate, max_age=60: {"name": "MS Gemini", "price": 0.5, "currency": "USD",
                                                                              "price_inr": 41.5, "stock": 50, "in_stock": True, "error": None})
    monkeypatch.setattr(ms, "place_order", lambda pid, qty=1: {"order_code": "ORD-A", "credentials":
                        [f"https://serviceactivation.google.com/subscription/new/AUTO{uuid.uuid4().hex}" for _ in range(qty)]})


class _EchoOldLink:
    """An LLM that 'helpfully' repeats the last link it saw in history instead of calling a tool."""
    def __init__(self):
        self.seen = []
    def invoke(self, payload):
        import re
        links = []
        for m in payload["messages"]:
            links += re.findall(r"https?://\S+", str(getattr(m, "content", "")))
        self.seen = links
        if links:
            return {"messages": [AIMessage(content=f"Yeh raha aapka link: {links[-1]}")], "todos": []}
        return {"messages": [AIMessage(content="Kaunsa product chahiye?")], "todos": []}


# ---- bug 1: old link must never be re-sent -------------------------------------------------------

def test_llm_never_sees_old_links_in_history_and_cannot_resend_them(db, fresh_reseller, monkeypatch):
    _mock_ms(monkeypatch)
    p = _gemini(db, stock_links=1)
    kw = _wa(fresh_reseller); sid = f"wa_st_{fresh_reseller.phone}"
    monkeypatch.setattr(agent_core, "get_deep_agent", lambda: None)
    first = agent_core.run_deep_agent_chat(sid, f"{p.name.lower()} link do", **kw)
    old_link = next(l for l in first["message"].split() if "serviceactivation.google.com" in l).strip("`")
    # user "clears chat" on the phone and chats again; the server history still has the old link
    echo = _EchoOldLink()
    monkeypatch.setattr(agent_core, "get_deep_agent", lambda: echo)
    out = agent_core.run_deep_agent_chat(sid, "thanks bhai, link kaam kar gaya kya?", **kw)   # not a claim
    assert old_link not in out["message"]                     # the LLM was never shown it...
    assert all("serviceactivation" not in l for l in echo.seen)   # ...history was redacted
    # even if a model somehow produced an old link, the outgoing guard strips it
    class _Hard:
        def invoke(self, payload):
            return {"messages": [AIMessage(content=f"Dobara: {old_link}")], "todos": []}
    monkeypatch.setattr(agent_core, "get_deep_agent", lambda: _Hard())
    out2 = agent_core.run_deep_agent_chat(sid, "achha theek hai bhai, baad me baat karte hain", **kw)   # not greeting/claim -> LLM runs
    assert old_link not in out2["message"] and "purani link hata di gayi" in out2["message"]
    assert any(t["tool"] == "stale_link_guard" for t in out2["metadata"]["tool_calls"])


def test_reseller_claim_is_deterministic_even_when_llm_available(db, fresh_reseller, monkeypatch):
    _mock_ms(monkeypatch)
    p = _gemini(db, stock_links=1)
    kw = _wa(fresh_reseller); sid = f"wa_det_{fresh_reseller.phone}"
    monkeypatch.setattr(agent_core, "get_deep_agent", lambda: _EchoOldLink())
    first = agent_core.run_deep_agent_chat(sid, f"{p.name.lower()} link do", **kw)
    l1 = [l for l in first["message"].split() if "serviceactivation" in l][0]
    second = agent_core.run_deep_agent_chat(sid, f"{p.name.lower()} link do", **kw)     # asks again after clearing chat
    l2 = [l for l in second["message"].split() if "serviceactivation" in l][0]
    assert l1 != l2 and "AUTO" in l2                          # a NEW link (auto-bought), not the old one
    assert second["metadata"]["engine"] != "deep_agent"
    db.expire_all()
    assert db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance == 500.0 - 2   # charged once per link


# ---- bug 2: manual stock burned -> auto-buy must kick in -----------------------------------------

def test_manual_stock_first_then_auto_buy(db, fresh_reseller, monkeypatch):
    _mock_ms(monkeypatch)
    p = _gemini(db, stock_links=1)                            # one manually uploaded link
    kw = _wa(fresh_reseller); sid = f"wa_fb_{fresh_reseller.phone}"
    monkeypatch.setattr(agent_core, "get_deep_agent", lambda: None)
    a = agent_core.run_deep_agent_chat(sid, f"{p.name.lower()} link do", **kw)
    assert "/new/MAN" in a["message"]                         # local stock used first
    b = agent_core.run_deep_agent_chat(sid, "ek aur", **kw)
    assert "/new/AUTO" in b["message"]                        # then bought from the supplier
    assert any(t["tool"] == "auto_buy" and t["ok"] for t in b["metadata"]["tool_calls"])


def test_llm_tools_report_auto_buy_products_as_available(db, monkeypatch):
    from agent_tools import get_product_pricing, get_live_product_catalog
    import json
    _mock_ms(monkeypatch)
    p = _gemini(db, stock_links=0)
    d = json.loads(get_product_pricing.invoke({"product_name_or_slug": p.slug}))
    assert d["in_stock"] is True and d["available_stock"] == 0 and d["auto_buy"] is True and "AUTO-BUY" in d["stock_note"]
    c = json.loads(get_live_product_catalog.invoke({"user_role": "reseller", "search": p.slug}))
    item = next(i for i in c["products"] if i["id"] == p.id) if "products" in c else next(i for i in c.get("catalog", []) if i["id"] == p.id)
    assert item["in_stock"] is True and item["auto_buy"] is True
