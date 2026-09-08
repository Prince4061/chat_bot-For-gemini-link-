"""Lazy freshness check: used links are skipped, marked, and a fresh one is handed out."""
import database as dbm
import link_checker


def _make_google_product(db):
    import uuid
    slug = f"gem-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Gemini {slug}", slug=slug, base_price=100, margin_percent=0, credit_cost=1)
    db.add(p); db.commit()
    # First two are "used", third is "fresh" — all look like Google links so they are checkable.
    for i in range(3):
        db.add(dbm.InviteLink(product_id=p.id, link_or_key=f"https://one.google.com/activate-plan/subscription/new/TOK{i}"))
    db.commit(); db.refresh(p)
    return p


def test_ensure_fresh_stock_marks_used_and_keeps_fresh(db, monkeypatch):
    p = _make_google_product(db)
    links = db.query(dbm.InviteLink).filter_by(product_id=p.id).order_by(dbm.InviteLink.id).all()
    used_tokens = {links[0].link_or_key, links[1].link_or_key}

    monkeypatch.setattr(link_checker, "is_checkable", lambda u: True)
    monkeypatch.setattr(link_checker, "check_link_freshness_detail",
                        lambda u, allow_browser=True: ("used" if u in used_tokens else "fresh", "http"))

    res = dbm.ensure_fresh_stock(db, p.id)
    assert res["marked_used"] == 2
    db.expire_all()
    rows = {l.id: l for l in db.query(dbm.InviteLink).filter_by(product_id=p.id).all()}
    assert rows[links[0].id].status == "used" and rows[links[0].id].health == "used"
    assert rows[links[1].id].status == "used"
    assert rows[links[2].id].status == "available" and rows[links[2].id].health == "fresh"
    assert p.get_available_stock_count(db) == 1  # only the fresh one remains claimable


def test_customer_fulfillment_delivers_fresh_link(db, monkeypatch):
    p = _make_google_product(db)
    links = db.query(dbm.InviteLink).filter_by(product_id=p.id).order_by(dbm.InviteLink.id).all()
    fresh_link = links[2].link_or_key
    monkeypatch.setattr(link_checker, "is_checkable", lambda u: True)
    monkeypatch.setattr(link_checker, "check_link_freshness_detail",
                        lambda u, allow_browser=True: ("fresh" if u == fresh_link else "used", "http"))

    order = dbm.CustomerOrder(id=dbm.generate_order_id(db), product_id=p.id, unit_price=100, total_amount=100, session_id="s_fresh")
    db.add(order); db.commit()
    res = dbm.fulfill_order(order, "778899001122", db)  # unique UTR (tests share one DB)
    assert res["success"] and res["link"] == fresh_link  # never a used one


def test_non_checkable_links_are_left_untouched(db, monkeypatch):
    import uuid
    slug = f"key-{uuid.uuid4().hex[:6]}"
    p = dbm.Product(name=f"Office {slug}", slug=slug, base_price=100, margin_percent=0, credit_cost=1)
    db.add(p); db.commit()
    db.add(dbm.InviteLink(product_id=p.id, link_or_key="OFFICE365-KEY-ABC-123")); db.commit()
    # Real is_checkable returns False for non-Google keys -> no network, no change.
    res = dbm.ensure_fresh_stock(db, p.id)
    assert res["checked"] == 0 and res["marked_used"] == 0
    assert p.get_available_stock_count(db) == 1
