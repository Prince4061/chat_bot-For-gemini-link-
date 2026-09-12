"""Large-catalogue regression: matching stays accurate and replies/tools/admin stay bounded."""
import json
import time
import database as dbm


BRANDS = ["Adobe", "Canva", "Notion", "Figma", "Spotify"]
TIERS = ["Pro", "Team", "Premium", "Enterprise"]


def _bulk_products(db, n=2000):
    # Tests share one DB: create the scale catalogue only once, reuse afterwards.
    existing = [r[0] for r in db.query(dbm.Product.id).filter(dbm.Product.category == "ScaleTest").all()]
    if existing:
        return existing
    rows = []
    for i in range(n):
        b, t = BRANDS[i % len(BRANDS)], TIERS[(i // len(BRANDS)) % len(TIERS)]
        rows.append(dbm.Product(name=f"{b} {t} S{i:05d}", slug=f"scale-{b.lower()}-{t.lower()}-s{i:05d}",
                                category="ScaleTest", base_price=100, margin_percent=10))
    db.bulk_save_objects(rows)
    db.commit()
    ids = [r[0] for r in db.query(dbm.Product.id).filter(dbm.Product.category == "ScaleTest").all()]
    db.bulk_save_objects([dbm.InviteLink(product_id=pid, link_or_key=f"K-{pid}", status="available") for pid in ids])
    db.commit()
    return ids


def test_find_product_accurate_and_fast_with_large_catalogue(db):
    _bulk_products(db)
    cases = [
        ("Notion Enterprise S00017 ka price", "scale-notion-enterprise-s00017"),   # exact variant by number
        ("mujhe canva team chahiye", "~canva team"),                              # any Canva Team
        ("gemini ki link do", "~gemini"),                                        # some Gemini (tests share one DB)
        ("xyz nothing here", "NONE"),                                             # must not guess
    ]
    t0 = time.time()
    for text, want in cases:
        p = dbm.find_product(db, text)
        if want == "NONE":
            assert p is None
        elif want.startswith("~"):
            assert p is not None and want[1:] in p.name.lower(), (text, p and p.name)
        else:
            assert p is not None and p.slug == want, (text, p and p.slug)
    assert (time.time() - t0) / len(cases) < 0.5, "matching must stay fast on big catalogues"


def test_catalog_reply_and_tool_are_bounded(db):
    from agent_core import run_deep_agent_chat
    from agent_tools import get_live_product_catalog
    _bulk_products(db)
    reply = run_deep_agent_chat("scale_chat_1", "products dikhao")["message"]
    assert len(reply) < 4000 and reply.count("\n") < 60          # WhatsApp-safe page, not a dump
    assert "aur" in reply and "products hain" in reply            # tells the user how to narrow down

    searched = run_deep_agent_chat("scale_chat_2", "notion products dikhao")["message"]
    assert "matching 'notion'" in searched and "Notion" in searched

    out = json.loads(get_live_product_catalog.invoke({"user_role": "customer"}))
    assert out["shown"] <= 25 and out["total_products"] >= 2000 and out["note"]
    out2 = json.loads(get_live_product_catalog.invoke({"user_role": "customer", "search": "figma premium"}))
    assert out2["shown"] >= 1 and all("Figma" in c["name"] for c in out2["catalog"])


def test_admin_endpoints_stay_fast_with_large_catalogue(client, admin_headers, db):
    _bulk_products(db)
    t0 = time.time()
    m = client.get("/api/admin/metrics", headers=admin_headers)
    assert m.status_code == 200 and len(m.get_json()["low_stock_products"]) <= 25
    p = client.get("/api/admin/products?q=notion&limit=50", headers=admin_headers)
    assert p.status_code == 200 and 0 < len(p.get_json()) <= 50 and all("Notion" in x["name"] for x in p.get_json())
    assert time.time() - t0 < 3.0
