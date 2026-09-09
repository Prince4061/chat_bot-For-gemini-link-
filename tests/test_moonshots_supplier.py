"""Supplier auto-buy (m00nshots): on-demand stock top-up feeds the normal claim/deliver flow."""
import uuid

import pytest

import database as dbm
import moonshots_service as ms


def _supplier_product(db, supplier_pid=42, max_price=None, base_price=1):
    slug = f"sup-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Gemini Auto {slug}", slug=slug, base_price=base_price,
                    margin_percent=0, reseller_margin_percent=0,
                    source="moonshots", supplier_product_id=supplier_pid, supplier_max_price=max_price)
    db.add(p); db.commit(); db.refresh(p)
    return p


class _FakeOrder(dict):
    pass


def _mock_supplier(monkeypatch, *, ready=True, creds=None, price=1.0, raise_error=None):
    monkeypatch.setattr(ms, "is_ready", lambda: ready)
    calls = {"orders": [], "get_product": 0}

    def fake_get_product(pid):
        calls["get_product"] += 1
        return {"id": pid, "price": price, "stock": 999, "in_stock": True}

    def fake_place_order(pid, qty=1):
        if raise_error:
            raise raise_error
        made = [f"acct{i}@x.com:pw{uuid.uuid4().hex[:5]}" for i in range(qty)] if creds is None else creds[:qty]
        calls["orders"].append((pid, qty, made))
        return {"order_code": f"ORD-{uuid.uuid4().hex[:6]}", "credentials": made, "remaining_balance": 10.0}

    monkeypatch.setattr(ms, "get_product", fake_get_product)
    monkeypatch.setattr(ms, "place_order", fake_place_order)
    return calls


# ---- replenish primitive --------------------------------------------------------------------

def test_replenish_buys_only_the_shortfall(db, monkeypatch):
    p = _supplier_product(db)
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="pre@x.com:existing")); db.commit()  # 1 in stock
    calls = _mock_supplier(monkeypatch)
    res = dbm.replenish_supplier_stock(db, p, needed=3)          # have 1, need 3 -> buy 2
    assert res["bought"] == 2 and res["error"] is None
    assert calls["orders"][0][1] == 2
    assert p.get_available_stock_count(db) == 3
    rows = db.query(dbm.InviteLink).filter_by(product_id=p.id, source="moonshots").all()
    assert len(rows) == 2 and all(r.status == "available" for r in rows)


def test_replenish_noop_when_enough_stock(db, monkeypatch):
    p = _supplier_product(db)
    for _ in range(3):
        db.add(dbm.InviteLink(product_id=p.id, link_or_key=f"s@x:{uuid.uuid4().hex[:4]}"))
    db.commit()
    calls = _mock_supplier(monkeypatch)
    res = dbm.replenish_supplier_stock(db, p, needed=2)
    assert res["bought"] == 0 and calls["orders"] == []


def test_replenish_skipped_for_stock_products(db, monkeypatch):
    slug = f"loc-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Local {slug}", slug=slug, base_price=1, margin_percent=0, reseller_margin_percent=0)
    db.add(p); db.commit()
    _mock_supplier(monkeypatch)
    assert dbm.replenish_supplier_stock(db, p, needed=5)["bought"] == 0


def test_replenish_respects_price_cap(db, monkeypatch):
    p = _supplier_product(db, max_price=2.0)
    calls = _mock_supplier(monkeypatch, price=5.0)              # supplier dearer than the cap
    res = dbm.replenish_supplier_stock(db, p, needed=1)
    assert res["bought"] == 0 and "above cap" in res["error"] and calls["orders"] == []


def test_replenish_clamps_to_max_autobuy(db, monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "MOONSHOTS_MAX_AUTOBUY_QTY", 3)
    p = _supplier_product(db)
    calls = _mock_supplier(monkeypatch)
    dbm.replenish_supplier_stock(db, p, needed=50)
    assert calls["orders"][0][1] == 3


def test_replenish_swallows_supplier_error(db, monkeypatch):
    p = _supplier_product(db)
    _mock_supplier(monkeypatch, raise_error=ms.MoonshotsError("insufficient balance", "insufficient_balance", 402))
    res = dbm.replenish_supplier_stock(db, p, needed=1)         # must NOT raise
    assert res["bought"] == 0 and "insufficient balance" in res["error"]
    assert p.get_available_stock_count(db) == 0


def test_replenish_disabled_supplier(db, monkeypatch):
    p = _supplier_product(db)
    _mock_supplier(monkeypatch, ready=False)
    res = dbm.replenish_supplier_stock(db, p, needed=1)
    assert res["bought"] == 0 and "disabled" in res["error"]


# ---- end-to-end through the real claim / fulfil paths ---------------------------------------

def test_reseller_claim_autobuys_and_delivers(db, fresh_reseller, monkeypatch):
    p = _supplier_product(db, base_price=1)          # 0 local stock
    calls = _mock_supplier(monkeypatch)
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 2, db)
    assert res["success"] is True
    assert len(res["links"]) == 2 and all("@x.com:" in l for l in res["links"])
    assert res["supplier_autobuy"]["bought"] == 2
    # the two delivered links are burned; nothing left over from a qty-2 buy
    assert p.get_available_stock_count(db) == 0
    assert calls["orders"][0][1] == 2


def test_reseller_claim_out_of_stock_when_supplier_fails_no_charge(db, fresh_reseller, monkeypatch):
    p = _supplier_product(db)
    _mock_supplier(monkeypatch, raise_error=ms.MoonshotsError("provider error", "provider", 502))
    before = db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance
    res = dbm.process_reseller_claim_for(fresh_reseller, p, 1, db)
    assert res["success"] is False and res["error"] == "OUT_OF_STOCK"
    assert db.query(dbm.Reseller).get(fresh_reseller.id).wallet_balance == before   # wallet untouched


def test_customer_order_autobuys_and_delivers(db, monkeypatch):
    p = _supplier_product(db)
    _mock_supplier(monkeypatch, creds=["buyer@x.com:secretpw"])
    order = dbm.CustomerOrder(id=dbm.generate_order_id(db), product_id=p.id,
                              unit_price=1, total_amount=1, session_id="s_ms")
    db.add(order); db.commit()
    res = dbm.fulfill_order(order, "111222333444", db)
    assert res["success"] is True and res["link"] == "buyer@x.com:secretpw"


# ---- key hygiene ----------------------------------------------------------------------------

def test_api_key_never_exposed_in_status(db, monkeypatch):
    monkeypatch.setattr(ms, "api_key", lambda: "mk_supersecretvalue1234")
    monkeypatch.setattr(ms, "get_balance", lambda: {"balance": 5.0, "currency": "USD"})
    st = ms.status_dict()
    assert st["has_key"] is True and st["balance"] == 5.0
    assert "supersecret" not in str(st) and st["key_mask"].endswith("1234")


def test_settings_masks_moonshots_key(db):
    s = dbm.get_settings(db)
    s.moonshots_api_key = "mk_abcdef123456"; db.commit()
    d = s.to_dict()
    assert d["moonshots_api_key"].endswith("3456") and "abcdef" not in d["moonshots_api_key"]
    assert d["has_moonshots_key"] is True
    s.moonshots_api_key = None; db.commit()
