"""Two suppliers (m00nshots + Loot Paglu): the bot buys from whichever is cheaper in ₹, respects a
forced preference, the ₹ price cap and stock, and falls back when one supplier fails."""
import uuid

import database as dbm
import lootpaglu_service as lp
import moonshots_service as ms
import suppliers


def _product(db, ms_id=42, lp_id="Paglu_1", source="supplier", **kw):
    slug = f"two-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Dual {slug}", slug=slug, base_price=500, margin_percent=0, reseller_margin_percent=0,
                    source=source, supplier_product_id=ms_id, lootpaglu_service_id=lp_id, **kw)
    db.add(p); db.commit(); db.refresh(p)
    return p


def _mock(monkeypatch, *, ms_price_usd=None, ms_stock=10, lp_price=None, lp_stock=10, ms_ready=True, lp_ready=True,
          ms_error=None, lp_error=None):
    """usd_to_inr in tests' settings defaults to 83 -> $1 = ₹83."""
    calls = {"orders": []}
    monkeypatch.setattr(ms, "is_ready", lambda: ms_ready)
    monkeypatch.setattr(lp, "is_ready", lambda: lp_ready)

    def ms_summary(pid, rate, max_age=60):
        if ms_error:
            return {"error": ms_error, "code": "err"}
        return {"name": "MS Gemini", "price": ms_price_usd, "currency": "USD", "price_inr": round(ms_price_usd * rate, 2),
                "stock": ms_stock, "in_stock": ms_stock > 0, "error": None}

    def lp_summary(sid, rate=0, max_age=60):
        if lp_error:
            return {"error": lp_error, "code": "err"}
        return {"name": "LP Gemini", "price": lp_price, "currency": "INR", "price_inr": lp_price,
                "stock": lp_stock, "in_stock": lp_stock > 0, "error": None}

    monkeypatch.setattr(ms, "product_summary", ms_summary)
    monkeypatch.setattr(lp, "product_summary", lp_summary)

    def ms_order(pid, qty=1):
        calls["orders"].append(("moonshots", pid, qty))
        return {"order_code": "ORD-MS", "credentials": [f"ms{i}-{uuid.uuid4().hex[:6]}@x:pw" for i in range(qty)]}

    def lp_order(sid, qty=1):
        calls["orders"].append(("lootpaglu", sid, qty))
        return {"order_code": "api_lp_1", "credentials": [f"LP-CODE-{i}-{uuid.uuid4().hex[:6]}" for i in range(qty)]}

    monkeypatch.setattr(ms, "place_order", ms_order)
    monkeypatch.setattr(lp, "place_order", lp_order)
    return calls


# ---- choosing --------------------------------------------------------------------------------

def test_cheapest_in_inr_wins_lootpaglu(db, monkeypatch):
    p = _product(db)
    calls = _mock(monkeypatch, ms_price_usd=1.0, lp_price=50.0)         # $1 = ₹83 vs ₹50 -> Loot Paglu
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["bought"] == 1 and res["supplier"] == "lootpaglu" and res["unit_price_inr"] == 50.0
    assert calls["orders"] == [("lootpaglu", "Paglu_1", 1)]
    row = db.query(dbm.InviteLink).filter_by(product_id=p.id).first()
    assert row.source == "lootpaglu" and row.link_or_key.startswith("LP-CODE-0") and "Loot Paglu" in row.notes
    assert "cheapest" in res["reason"]


def test_cheapest_in_inr_wins_moonshots(db, monkeypatch):
    p = _product(db)
    calls = _mock(monkeypatch, ms_price_usd=0.5, lp_price=60.0)         # ₹41.5 vs ₹60 -> m00nshots
    res = dbm.replenish_supplier_stock(db, p, 2)
    assert res["supplier"] == "moonshots" and res["bought"] == 2 and calls["orders"] == [("moonshots", 42, 2)]


def test_forced_preference_beats_price(db, monkeypatch):
    p = _product(db, supplier_preference="lootpaglu")
    calls = _mock(monkeypatch, ms_price_usd=0.1, lp_price=90.0)         # m00nshots far cheaper, but forced LP
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["supplier"] == "lootpaglu" and "forced" in res["reason"] and calls["orders"][0][0] == "lootpaglu"


def test_out_of_stock_supplier_is_skipped(db, monkeypatch):
    p = _product(db)
    calls = _mock(monkeypatch, ms_price_usd=1.0, ms_stock=5, lp_price=40.0, lp_stock=0)   # LP cheaper but empty
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["supplier"] == "moonshots" and calls["orders"][0][0] == "moonshots"


def test_failing_supplier_falls_back_to_the_other(db, monkeypatch):
    p = _product(db)
    calls = _mock(monkeypatch, ms_price_usd=1.0, lp_price=40.0, lp_error="Loot Paglu returned HTTP 503")
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["supplier"] == "moonshots" and res["bought"] == 1 and calls["orders"][0][0] == "moonshots"


def test_inr_price_cap_blocks_both(db, monkeypatch):
    p = _product(db, max_buy_price_inr=30.0)
    calls = _mock(monkeypatch, ms_price_usd=1.0, lp_price=45.0)
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["bought"] == 0 and "above cap" in res["error"] and calls["orders"] == []


def test_legacy_usd_cap_still_honoured(db, monkeypatch):
    p = _product(db, lp_id=None, supplier_max_price=0.4)                 # $0.4 ≈ ₹33 cap
    _mock(monkeypatch, ms_price_usd=1.0)
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["bought"] == 0 and "above cap" in res["error"]


def test_partial_stock_buys_what_exists(db, monkeypatch):
    p = _product(db, ms_id=None)                                         # Loot Paglu only
    calls = _mock(monkeypatch, lp_price=40.0, lp_stock=1, ms_ready=False)
    res = dbm.replenish_supplier_stock(db, p, 3)
    assert res["bought"] == 1 and calls["orders"] == [("lootpaglu", "Paglu_1", 1)]


def test_legacy_source_moonshots_only_uses_moonshots(db, monkeypatch):
    p = _product(db, source="moonshots")                                 # old rows before migration
    calls = _mock(monkeypatch, ms_price_usd=2.0, lp_price=10.0)          # LP cheaper but not allowed
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["supplier"] == "moonshots" and calls["orders"][0][0] == "moonshots"


def test_nothing_ready_means_no_purchase_and_out_of_stock(db, fresh_reseller, monkeypatch):
    p = _product(db)
    _mock(monkeypatch, ms_ready=False, lp_ready=False)
    before = db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 1, db)
    assert res["success"] is False and res["error"] == "OUT_OF_STOCK"
    assert db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance == before


# ---- end to end through a reseller claim --------------------------------------------------------

def test_reseller_claim_buys_from_cheapest_and_delivers(db, fresh_reseller, monkeypatch):
    p = _product(db)
    p.base_price = 1; db.commit()
    _mock(monkeypatch, ms_price_usd=1.0, lp_price=20.0)
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 2, db)
    assert res["success"] and len(res["links"]) == 2 and all(l.startswith("LP-CODE-") for l in res["links"])
    assert res["supplier_autobuy"]["supplier"] == "lootpaglu"


# ---- migration + admin surfaces -------------------------------------------------------------------

def test_migration_moves_legacy_rows_to_generic_supplier_and_inr_cap(db):
    p = _product(db, source="moonshots", lp_id=None, supplier_max_price=2.0)
    dbm._migrate_supplier_fields(db)
    db.expire_all()
    p = db.query(dbm.Product).get(p.id)
    rate = float(dbm.get_settings(db).usd_to_inr_rate or 83.0)
    assert p.source == "supplier" and p.supplier_max_price is None and p.max_buy_price_inr == round(2.0 * rate, 2)


def test_mapped_endpoint_shows_quotes_and_choice(client, admin_headers, db, monkeypatch):
    p = _product(db)
    _mock(monkeypatch, ms_price_usd=1.0, lp_price=50.0)
    r = client.get("/api/admin/suppliers/mapped?fresh=1", headers=admin_headers).get_json()
    item = r["items"][str(p.id)]
    assert item["chosen"] == "lootpaglu" and len(item["quotes"]) == 2
    lpq = next(q for q in item["quotes"] if q["supplier"] == "lootpaglu")
    assert lpq["chosen"] is True and lpq["price_inr"] == 50.0 and "cheapest" in item["reason"]


def test_quote_endpoint_single_supplier(client, admin_headers, monkeypatch):
    _mock(monkeypatch, lp_price=77.0)
    r = client.get("/api/admin/suppliers/quote?supplier=lootpaglu&ref=Paglu_9", headers=admin_headers).get_json()
    assert r["success"] and r["data"]["price_inr"] == 77.0 and r["data"]["label"] == "Loot Paglu"
    assert client.get("/api/admin/suppliers/quote?supplier=nope&ref=1", headers=admin_headers).status_code == 400


def test_lootpaglu_normalises_products_and_masks_key(monkeypatch):
    monkeypatch.setattr(lp, "api_key", lambda: "LootPaglu_secretsecret9999")
    monkeypatch.setattr(lp, "_request", lambda m, path, **k: {"status": "success", "services": [
        {"service_id": "Paglu_1", "name": "Gemini 18 Months Pro", "available_stock": 39,
         "requires_shein_verification": False, "prices": {"upiPrice": 50.0, "cryptoPrice": 0.5}}]})
    lp._LIST_CACHE["ts"] = 0.0
    items = lp.list_products(max_age=0)
    assert items[0]["id"] == "Paglu_1" and items[0]["price"] == 50.0 and items[0]["stock"] == 39 and items[0]["in_stock"]
    assert lp.get_product("Paglu_1")["name"] == "Gemini 18 Months Pro"
    assert lp.mask_key().endswith("9999") and "secret" not in lp.mask_key()


def test_lootpaglu_order_parses_codes(monkeypatch):
    monkeypatch.setattr(lp, "_request", lambda m, path, **k: {"status": "success", "success": True, "order_id": "api_1",
                                                              "total_cost": 100.0, "new_balance": 900.0, "products": ["C1", "C2"]})
    o = lp.place_order("Paglu_1", 2)
    assert o["order_code"] == "api_1" and o["credentials"] == ["C1", "C2"] and o["unit_price"] == 50.0


def test_settings_accept_lootpaglu_key_and_toggle(client, admin_headers):
    s = client.post("/api/admin/settings", json={"lootpaglu_enabled": True, "lootpaglu_api_key": "LootPaglu_testkey1234"}, headers=admin_headers).get_json()
    assert s["lootpaglu_enabled"] is True and s["lootpaglu_api_key"].endswith("1234") and "testkey" not in s["lootpaglu_api_key"]
    client.post("/api/admin/settings", json={"lootpaglu_enabled": False, "lootpaglu_api_key": ""}, headers=admin_headers)


# ---- the WhatsApp screenshot bug: ₹0 quote + no fallback ------------------------------------------

def test_zero_price_quote_is_never_chosen(db, monkeypatch):
    p = _product(db)
    calls = _mock(monkeypatch, ms_price_usd=0.42, lp_price=0.0)          # Loot Paglu shows ₹0 (missing price)
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["supplier"] == "moonshots" and res["bought"] == 1 and calls["orders"][0][0] == "moonshots"
    lpq = next(q for q in res["quotes"] if q["supplier"] == "lootpaglu")
    assert "price unavailable" in lpq["error"]


def test_only_supplier_with_zero_price_means_no_purchase(db, monkeypatch):
    p = _product(db, ms_id=None)
    calls = _mock(monkeypatch, lp_price=0.0, ms_ready=False)
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["bought"] == 0 and "price unavailable" in res["error"] and calls["orders"] == []


def test_purchase_failure_falls_back_to_next_supplier(db, monkeypatch):
    p = _product(db)
    calls = _mock(monkeypatch, ms_price_usd=1.0, lp_price=20.0)          # LP cheapest...
    monkeypatch.setattr(lp, "place_order", lambda sid, qty=1: (_ for _ in ()).throw(lp.LootPagluError("Insufficient INR wallet balance", "insufficient_balance", 400)))
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["bought"] == 1 and res["supplier"] == "moonshots"          # ...but its order fails -> m00nshots
    assert "fell back after" in res["reason"] and "Insufficient INR wallet balance" in res["reason"]
    assert calls["orders"] == [("moonshots", 42, 1)]


def test_all_purchases_fail_reports_every_attempt(db, fresh_reseller, monkeypatch):
    p = _product(db)
    _mock(monkeypatch, ms_price_usd=1.0, lp_price=20.0)
    monkeypatch.setattr(lp, "place_order", lambda sid, qty=1: (_ for _ in ()).throw(lp.LootPagluError("Insufficient INR wallet balance", "insufficient_balance", 400)))
    monkeypatch.setattr(ms, "place_order", lambda pid, qty=1: (_ for _ in ()).throw(ms.MoonshotsError("insufficient balance", "insufficient_balance", 402)))
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 1, db)
    assert res["success"] is False and res["error"] == "OUT_OF_STOCK"
    why = res["supplier_autobuy"]["error"]
    assert "every supplier failed" in why and "Loot Paglu" in why and "m00nshots" in why


def test_bot_tester_sees_auto_buy_chip(db, fresh_reseller, monkeypatch):
    from agent_core import run_deep_agent_chat
    p = _product(db); p.base_price = 1; db.commit()
    _mock(monkeypatch, ms_price_usd=0.5, lp_price=0.0)
    out = run_deep_agent_chat(f"wa_ab_{fresh_reseller.phone}", f"{p.name.lower()} link do", platform="whatsapp",
                              owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    chip = next(t for t in out["metadata"]["tool_calls"] if t["tool"] == "auto_buy")
    assert chip["ok"] and chip["detail"].startswith("moonshots x1")


def test_lootpaglu_price_key_drift_is_tolerated():
    n = lp._normalise_service({"service_id": "Paglu_2", "name": "X", "available_stock": "5", "prices": {"upi_price": "45"}})
    assert n["price"] == 45.0 and n["stock"] == 5 and n["price_known"]
    z = lp._normalise_service({"service_id": "Paglu_3", "name": "Y", "available_stock": 9, "prices": {"upiPrice": 0}})
    assert z["price"] == 0.0 and z["price_known"] is False


# ---- "ek aur" repeat, admin alert, dry run ---------------------------------------------------------

def test_ek_aur_claims_the_same_product_again_without_llm(db, fresh_reseller, monkeypatch):
    import agent_core
    from langchain_core.messages import AIMessage

    class _Hallucinating:   # an LLM that would repeat "stock nahi" from history
        def invoke(self, payload):
            return {"messages": [AIMessage(content="abhi stock mein nahi hai")], "todos": []}

    monkeypatch.setattr(agent_core, "get_deep_agent", lambda: _Hallucinating())
    p = _product(db); p.base_price = 1; db.commit()
    _mock(monkeypatch, ms_price_usd=0.5, lp_price=0.0)
    kw = dict(platform="whatsapp", owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    sid = f"wa_rep_{fresh_reseller.phone}"
    first = agent_core.run_deep_agent_chat(sid, f"{p.name.lower()} link do", **kw)     # named product -> tool path
    # (fake LLM never calls tools, so force the first claim through the rule engine)
    if "@x:pw" not in first["message"]:
        monkeypatch.setattr(agent_core, "get_deep_agent", lambda: None)
        first = agent_core.run_deep_agent_chat(sid, f"{p.name.lower()} link do", **kw)
        monkeypatch.setattr(agent_core, "get_deep_agent", lambda: _Hallucinating())
    assert "@x:pw" in first["message"]
    second = agent_core.run_deep_agent_chat(sid, "Ek aur", **kw)
    assert "@x:pw" in second["message"] and "stock mein nahi" not in second["message"]
    assert any(t["tool"] == "claim_reseller_product_link" and "repeat" in t["detail"] for t in second["metadata"]["tool_calls"])
    third = agent_core.run_deep_agent_chat(sid, "2 aur", **kw)
    assert third["message"].count("@x:pw") == 2


def test_ek_aur_without_prior_claim_is_not_a_claim(db, fresh_reseller, monkeypatch):
    import agent_core
    r = dbm.Reseller(name="Fresh Two", phone="7" + str(uuid.uuid4().int)[:9], secret_code="1111", currency="INR")
    db.add(r); db.commit()
    assert agent_core._repeat_claim_target(db, r, "ek aur") is None


def test_admin_is_alerted_on_whatsapp_when_autobuy_fails(db, monkeypatch):
    import evolution_service
    sent = []
    monkeypatch.setattr(evolution_service, "send_whatsapp_message", lambda remote_jid, message_text, **k: sent.append((remote_jid, message_text)) or {})
    st = dbm.get_settings(db); st.admin_contact_number = "98765 43210"; db.commit()
    suppliers._ALERTS.clear()
    p = _product(db)
    _mock(monkeypatch, ms_price_usd=1.0, lp_price=20.0)
    monkeypatch.setattr(lp, "place_order", lambda sid, qty=1: (_ for _ in ()).throw(lp.LootPagluError("Insufficient INR wallet balance", "insufficient_balance", 400)))
    monkeypatch.setattr(ms, "place_order", lambda pid, qty=1: (_ for _ in ()).throw(ms.MoonshotsError("insufficient balance", "insufficient_balance", 402)))
    res = dbm.replenish_supplier_stock(db, p, 1)
    import time
    for _ in range(50):
        if sent:
            break
        time.sleep(0.02)
    assert res["bought"] == 0 and sent and sent[0][0] == "919876543210"
    assert "Auto-buy FAILED" in sent[0][1] and "Insufficient INR wallet balance" in sent[0][1]
    # rate-limited: a second failure right away does not spam
    dbm.replenish_supplier_stock(db, p, 1); time.sleep(0.1)
    assert len(sent) == 1
    st.admin_contact_number = ""; db.commit()


def test_dry_run_explains_verdict(client, admin_headers, db, monkeypatch):
    p = _product(db)
    _mock(monkeypatch, ms_price_usd=0.5, lp_price=0.0)
    monkeypatch.setattr(ms, "status_dict", lambda: {"balance": 2.37, "currency": "USD", "enabled": True, "has_key": True, "error": None})
    monkeypatch.setattr(lp, "status_dict", lambda: {"balance": 10.0, "currency": "INR", "enabled": True, "has_key": True, "error": None})
    d = client.get(f"/api/admin/suppliers/dry-run/{p.id}", headers=admin_headers).get_json()
    assert d["ok"] and d["chosen"] == "moonshots" and d["verdict"].startswith("✅") and "m00nshots" in d["verdict"]
    # cheapest supplier but empty wallet -> explains balance
    monkeypatch.setattr(ms, "status_dict", lambda: {"balance": 0.1, "currency": "USD", "enabled": True, "has_key": True, "error": None})
    d2 = client.get(f"/api/admin/suppliers/dry-run/{p.id}", headers=admin_headers).get_json()
    assert not d2["ok"] and "balance kam" in d2["verdict"]
    # local-stock product -> auto-buy OFF
    slug = f"loc-{uuid.uuid4().hex[:6]}"
    q = dbm.Product(name=f"Local {slug}", slug=slug, base_price=1, margin_percent=0, reseller_margin_percent=0)
    db.add(q); db.commit()
    d3 = client.get(f"/api/admin/suppliers/dry-run/{q.id}", headers=admin_headers).get_json()
    assert not d3["supplier_backed"] and "auto-buy OFF" in d3["verdict"]


# ---- duplicate guard: the "same expired link 3 times, charged 3 times" bug ---------------------------

def test_supplier_duplicate_link_is_never_stocked_and_next_supplier_is_tried(db, monkeypatch):
    p = _product(db)
    calls = _mock(monkeypatch, ms_price_usd=1.0, lp_price=20.0)              # LP cheapest
    # LP keeps returning the SAME link every order; we already delivered it once.
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="https://serviceactivation.google.com/subscription/new/SAME",
                          status="claimed", claimed_by_type="reseller", claimed_by_id="9999999999")); db.commit()
    monkeypatch.setattr(lp, "place_order", lambda sid, qty=1: (calls["orders"].append(("lootpaglu", sid, qty)) or
                        {"order_code": "api_dup", "credentials": ["https://serviceactivation.google.com/subscription/new/SAME"]}))
    res = dbm.replenish_supplier_stock(db, p, 1)
    assert res["supplier"] == "moonshots" and res["bought"] == 1             # fell through to m00nshots
    assert "DUPLICATE" in res["reason"]
    assert db.query(dbm.InviteLink).filter_by(link_or_key="https://serviceactivation.google.com/subscription/new/SAME").count() == 1


def test_all_suppliers_duplicate_means_no_stock_and_no_charge(db, fresh_reseller, monkeypatch):
    p = _product(db, lp_id=None); p.base_price = 1; db.commit()
    _mock(monkeypatch, ms_price_usd=1.0, lp_ready=False)
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="DUP-TOKEN", status="claimed")); db.commit()
    monkeypatch.setattr(ms, "place_order", lambda pid, qty=1: {"order_code": "ORD-D", "credentials": ["DUP-TOKEN"]})
    before = db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 1, db)
    assert res["success"] is False and res["error"] == "OUT_OF_STOCK"
    assert "DUPLICATE" in res["supplier_autobuy"]["error"]
    assert db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance == before      # not charged


def test_partial_duplicates_keep_only_new_links(db, monkeypatch):
    p = _product(db, lp_id=None)
    _mock(monkeypatch, ms_price_usd=1.0, lp_ready=False)
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="OLD-1", status="claimed")); db.commit()
    monkeypatch.setattr(ms, "place_order", lambda pid, qty=1: {"order_code": "ORD-P", "credentials": ["OLD-1", "NEW-2", "NEW-2"]})
    res = dbm.replenish_supplier_stock(db, p, 2)
    assert res["bought"] == 1 and res["duplicates"] == 1
    assert p.get_available_stock_count(db) == 1


def test_pre_existing_duplicate_rows_are_never_delivered(db, fresh_reseller, monkeypatch):
    """Rows stocked before this fix: two rows with the same text - the second must never go out."""
    slug = f"dupl-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Dupl {slug}", slug=slug, base_price=1, margin_percent=0, reseller_margin_percent=0)
    db.add(p); db.commit()
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="https://serviceactivation.google.com/subscription/new/TWICE", status="claimed"))
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="https://serviceactivation.google.com/subscription/new/TWICE"))   # stocked again
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="https://serviceactivation.google.com/subscription/new/FRESHONE"))
    db.commit()
    import link_checker
    monkeypatch.setattr(link_checker, "check_link_freshness_detail", lambda u, allow_browser=True: ("unknown", "http"))
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 1, db)
    assert res["success"] and res["links"] == ["https://serviceactivation.google.com/subscription/new/FRESHONE"]
    parked = db.query(dbm.InviteLink).filter_by(link_or_key="https://serviceactivation.google.com/subscription/new/TWICE", status="used").first()
    assert parked and parked.health == "duplicate"


def test_duplicate_deliveries_report(client, admin_headers, db):
    slug = f"rep-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Rep {slug}", slug=slug, base_price=1, margin_percent=0, reseller_margin_percent=0)
    db.add(p); db.commit()
    tok = f"https://serviceactivation.google.com/subscription/new/{uuid.uuid4().hex}"
    for who in ("9111111111", "9111111111", "9222222222"):
        db.add(dbm.InviteLink(product_id=p.id, link_or_key=tok, status="claimed", claimed_by_type="reseller",
                              claimed_by_id=who, claimed_at=dbm.utcnow()))
    db.commit()
    r = client.get("/api/admin/inventory/duplicates", headers=admin_headers).get_json()
    item = next(i for i in r["items"] if i["product"] == p.name)
    assert item["times_delivered"] == 3 and item["deliveries"][0]["first"] is True
    assert [d["claimed_by_id"] for d in item["deliveries"][1:]] == ["9111111111", "9222222222"]   # refund these


def test_lootpaglu_finds_inr_price_in_any_shape():
    shapes = [
        {"service_id": "a", "prices": {"upiPrice": 0, "upi_price_inr": 55}},
        {"service_id": "b", "pricing": {"inr": {"upi": "60"}, "crypto": {"usdt": 0.6}}},
        {"service_id": "c", "prices": [{"currency": "USDT", "price": 0.5}, {"currency": "INR", "price": 65}]},
        {"service_id": "d", "priceINR": 70, "cryptoPrice": 0.7},
        {"service_id": "e", "rate": {"upi": 75}, "available_stock": 9},
    ]
    got = [lp._normalise_service(x)["price"] for x in shapes]
    assert got == [55.0, 60.0, 65.0, 70.0, 75.0]
    none = lp._normalise_service({"service_id": "z", "prices": {"upiPrice": 0, "cryptoPrice": 0.4}, "available_stock": 3})
    assert none["price"] == 0.0 and none["price_known"] is False and any("upiPrice" in k for k in none["raw_keys"])
    # never mistake stock / crypto / ids for a price
    trap = lp._normalise_service({"service_id": "t", "available_stock": 1382, "id": 99, "prices": {"cryptoPrice": 0.9}})
    assert trap["price"] == 0.0


def test_lootpaglu_list_price_zero_falls_back_to_order_history(monkeypatch):
    def fake_request(method, path, **k):
        if path == "/api/v1/products":
            return {"status": "success", "services": [
                {"service_id": "Paglu_1", "name": "Gemini 18 Months Pro 💎", "available_stock": 1382,
                 "prices": {"upiPrice": 0, "cryptoPrice": 0.5}}]}
        if path == "/api/v1/orders":
            return {"success": True, "orders": [
                {"order_id": "api_2", "service": "Gemini 18 Months Pro 💎", "quantity": 2, "amount": 100.0, "currency": "inr", "status": "success"},
                {"order_id": "api_1", "service": "Gemini 18 Months Pro 💎", "quantity": 1, "amount": 55.0, "currency": "inr", "status": "success"}]}
        raise AssertionError(path)
    monkeypatch.setattr(lp, "_request", fake_request)
    lp._LIST_CACHE.update(ts=0.0, items=[]); lp._HIST_CACHE.update(ts=0.0, prices={})
    items = lp.list_products(max_age=0)
    assert items[0]["price"] == 50.0 and items[0]["price_known"] and items[0]["price_source"] == "order_history"
    summ = lp.product_summary("Paglu_1", max_age=0)
    assert summ["error"] is None and summ["price_inr"] == 50.0          # usable for cheapest-supplier choice


def test_failed_autobuy_reason_reaches_buyer_reply_and_product_card(db, fresh_reseller, monkeypatch):
    p = _product(db, lp_id=None); p.base_price = 1; db.commit()
    _mock(monkeypatch, ms_price_usd=1.0, lp_ready=False)
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="ALREADY-GIVEN", status="claimed")); db.commit()
    monkeypatch.setattr(ms, "place_order", lambda pid, qty=1: {"order_code": "ORD-DUP", "credentials": ["ALREADY-GIVEN"]})
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 1, db)
    assert res["success"] is False and "duplicate" in res["message"].lower() and "Admin ko alert" in res["message"]
    db.expire_all()
    last = db.query(dbm.Product).get(p.id).last_autobuy()
    assert last and last["bought"] == 0 and "DUPLICATE" in last["error"] and last["duplicate_order_code"] == "ORD-DUP"
    assert db.query(dbm.Product).get(p.id).to_dict(db)["last_autobuy"]["error"] == last["error"]
    # a later success overwrites it
    monkeypatch.setattr(ms, "place_order", lambda pid, qty=1: {"order_code": "ORD-OK", "credentials": [f"NEW-{uuid.uuid4().hex}"]})
    res2 = dbm.process_reseller_claim_for(fresh_reseller, p, 1, db)
    db.expire_all()
    assert res2["success"] and db.query(dbm.Product).get(p.id).last_autobuy()["bought"] == 1


def test_failure_hint_categories():
    h = dbm.autobuy_failure_hint
    assert "duplicate" in h({"error": "every supplier failed: m00nshots: returned 1 DUPLICATE link(s)"})
    assert "balance kam" in h({"error": "Insufficient INR wallet balance"})
    assert "price nahi" in h({"error": "Loot Paglu: price unavailable at supplier"})
    assert "limit se upar" in h({"error": "supplier price ₹90 above cap ₹50"})
    assert "connect nahi" in h({"error": "supplier disabled or no API key"})
    assert h({}) == "" and h(None) == ""
