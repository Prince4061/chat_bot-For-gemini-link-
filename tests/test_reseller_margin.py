"""Two margins over one base cost: customer margin % and reseller margin %."""
import database as dbm


def test_reseller_price_follows_reseller_margin(db):
    import uuid
    p = dbm.Product(name=f"Dual {uuid.uuid4().hex[:6]}", slug=f"dual-{uuid.uuid4().hex[:6]}",
                    base_price=200.0, margin_percent=50.0, reseller_margin_percent=10.0)
    db.add(p); db.commit()
    assert p.get_customer_price() == 300.0      # base + 50%
    assert p.get_reseller_price() == 220.0      # base + 10%  (different slider)
    d = p.to_dict()
    assert d["reseller_margin_percent"] == 10.0 and d["reseller_price"] == 220.0


def test_margin_endpoint_saves_both_sliders(client, admin_headers, db):
    import uuid
    p = dbm.Product(name=f"Both {uuid.uuid4().hex[:6]}", slug=f"both-{uuid.uuid4().hex[:6]}", base_price=100.0, margin_percent=0.0)
    db.add(p); db.commit()
    r = client.post(f"/api/admin/products/{p.id}/margin",
                    json={"margin_percent": 40, "reseller_margin_percent": 15}, headers=admin_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body["new_live_customer_price"] == 140.0 and body["new_live_reseller_price"] == 115.0
    db.expire_all()
    fresh = db.query(dbm.Product).get(p.id)
    assert fresh.margin_percent == 40.0 and fresh.reseller_margin_percent == 15.0

    # Validation: reseller margin must be a sane percentage.
    assert client.post(f"/api/admin/products/{p.id}/margin",
                       json={"margin_percent": 40, "reseller_margin_percent": -5}, headers=admin_headers).status_code == 400


def test_create_product_with_reseller_margin_and_bot_quotes_both(client, admin_headers, db, fresh_reseller):
    import uuid
    from agent_core import run_deep_agent_chat
    name = f"Twin {uuid.uuid4().hex[:6]}"
    r = client.post("/api/admin/products", json={"name": name, "base_price": 100, "margin_percent": 30,
                                                 "reseller_margin_percent": 5}, headers=admin_headers)
    assert r.status_code == 201 and r.get_json()["reseller_price"] == 105.0 and r.get_json()["customer_price"] == 130.0
    pid = r.get_json()["id"]
    db.add(dbm.InviteLink(product_id=pid, link_or_key=f"https://example.com/{name}/1")); db.commit()

    # Customer (web) is quoted the customer price...
    cust = run_deep_agent_chat("chat_twin_c", f"{name} ka price kya hai")["message"]
    assert "₹130.00" in cust
    # ...the reseller (WhatsApp, auto-verified) is charged the reseller price from the wallet.
    kw = dict(platform="whatsapp", owner_id=f"wa:{fresh_reseller.phone}", customer_phone=fresh_reseller.phone)
    claim = run_deep_agent_chat(f"wa_twin_{fresh_reseller.phone}", f"{name} ki link do", **kw)["message"]
    assert "₹105.00" in claim and "₹395.00" in claim          # ₹500 wallet - ₹105


def test_legacy_explicit_reseller_price_is_converted_to_margin(db):
    import uuid
    p = dbm.Product(name=f"Legacy {uuid.uuid4().hex[:6]}", slug=f"legacy-{uuid.uuid4().hex[:6]}",
                    base_price=200.0, margin_percent=0.0, reseller_price=250.0)
    db.add(p); db.commit()
    dbm._migrate_reseller_price_to_margin(db)
    db.refresh(p)
    assert p.reseller_price is None and p.reseller_margin_percent == 25.0
    assert p.get_reseller_price() == 250.0                      # same price, now margin-driven
