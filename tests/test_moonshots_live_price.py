"""Live supplier price in the Products tab: cached lookups + batch endpoint for mapped products."""
import uuid

import database as dbm
import moonshots_service as ms


def _mapped_product(db, sid):
    slug = f"lp-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Live {slug}", slug=slug, base_price=100, margin_percent=0, reseller_margin_percent=0,
                    source="moonshots", supplier_product_id=sid)
    db.add(p); db.commit(); db.refresh(p)
    return p


def test_product_summary_converts_to_inr_and_caches(monkeypatch):
    calls = []
    monkeypatch.setattr(ms, "get_product", lambda pid: (calls.append(pid), {"id": pid, "name": "Gemini 1M", "icon": "⚡",
                                                                             "price": 3.6, "currency": "USD", "stock": 25, "in_stock": True})[1])
    ms._PRODUCT_CACHE.clear()
    a = ms.product_summary(42, usd_to_inr=83.0)
    assert a["name"] == "Gemini 1M" and a["price"] == 3.6 and a["price_inr"] == 298.8 and a["stock"] == 25 and a["error"] is None
    b = ms.product_summary(42, usd_to_inr=83.0)              # served from cache
    assert b == a and calls == [42]
    ms.product_summary(42, usd_to_inr=83.0, max_age=0)       # forced refresh hits the API again
    assert calls == [42, 42]


def test_product_summary_reports_error_per_item(monkeypatch):
    monkeypatch.setattr(ms, "get_product", lambda pid: (_ for _ in ()).throw(ms.MoonshotsError("Product not found", "not_found", 404)))
    ms._PRODUCT_CACHE.clear()
    s = ms.product_summary(999, 83.0)
    assert s["error"] == "Product not found" and s["code"] == "not_found"


def test_mapped_endpoint_returns_live_info_per_local_product(client, admin_headers, db, monkeypatch):
    p1 = _mapped_product(db, 42)
    p2 = _mapped_product(db, 42)          # shares the supplier id -> one API call
    p3 = _mapped_product(db, 7)
    calls = []
    monkeypatch.setattr(ms, "api_key", lambda: "mk_test")
    monkeypatch.setattr(ms, "get_product", lambda pid: (calls.append(pid), {"id": pid, "name": f"P{pid}", "price": 2.0, "stock": 3, "in_stock": True})[1])
    ms._PRODUCT_CACHE.clear()
    r = client.get("/api/admin/moonshots/mapped?fresh=1", headers=admin_headers)
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert items[str(p1.id)]["name"] == "P42" and items[str(p2.id)]["name"] == "P42" and items[str(p3.id)]["name"] == "P7"
    assert items[str(p1.id)]["price_inr"] == round(2.0 * float(dbm.get_settings(db).usd_to_inr_rate or 83.0), 2)
    assert sorted(calls) == [7, 42]        # de-duplicated across local products


def test_mapped_endpoint_without_key_explains_instead_of_failing(client, admin_headers, db, monkeypatch):
    p = _mapped_product(db, 5)
    monkeypatch.setattr(ms, "api_key", lambda: "")
    r = client.get("/api/admin/moonshots/mapped", headers=admin_headers)
    assert r.status_code == 200
    assert "API key" in r.get_json()["items"][str(p.id)]["error"]


def test_single_product_endpoint(client, admin_headers, monkeypatch):
    monkeypatch.setattr(ms, "get_product", lambda pid: {"id": pid, "name": "Netflix", "price": 1.25, "stock": 0, "in_stock": False})
    ms._PRODUCT_CACHE.clear()
    r = client.get("/api/admin/moonshots/products/11?fresh=1", headers=admin_headers)
    d = r.get_json()
    assert r.status_code == 200 and d["success"] and d["data"]["name"] == "Netflix" and d["data"]["in_stock"] is False
