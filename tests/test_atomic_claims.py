"""Concurrency + transactional guarantees of link burning and credit deduction."""
import threading

import database as dbm


def test_concurrent_claims_never_hand_out_the_same_link(db, fresh_product):
    """2x more claimers than links: exactly `stock` succeed and every link is unique."""
    stock = fresh_product.get_available_stock_count(db)
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(stock * 2)

    def worker(i):
        session = dbm.get_db()
        try:
            barrier.wait()
            ok, link, _ = dbm.claim_single_use_link(fresh_product.id, "customer", f"user{i}", f"ORD-T{i}", db=session)
            with lock:
                results.append(link.link_or_key if ok else None)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(stock * 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    won = [r for r in results if r]
    assert len(won) == stock
    assert len(set(won)) == stock, "a link was handed to two claimers"
    assert fresh_product.get_available_stock_count(db) == 0


def test_reseller_claim_deducts_credits_and_logs(db, fresh_product, fresh_reseller):
    res = dbm.process_reseller_claim_for(fresh_reseller, fresh_product, 2, db)
    assert res["success"], res
    assert len(res["links"]) == 2
    assert res["remaining_credits"] == 3
    db.refresh(fresh_reseller)
    assert fresh_reseller.credits_balance == 3
    txns = db.query(dbm.CreditTransaction).filter(dbm.CreditTransaction.reseller_id == fresh_reseller.id).all()
    assert len(txns) == 2 and all(t.amount == -1 for t in txns)


def test_out_of_stock_rolls_back_credit_deduction(db, fresh_product, fresh_reseller):
    res = dbm.process_reseller_claim_for(fresh_reseller, fresh_product, 4, db)  # only 3 in stock
    assert not res["success"] and res["error"] == "OUT_OF_STOCK"
    db.refresh(fresh_reseller)
    assert fresh_reseller.credits_balance == 5, "credits must not be lost when stock runs out"
    assert fresh_product.get_available_stock_count(db) == 3


def test_insufficient_credits_blocks_claim(db, fresh_product, fresh_reseller):
    fresh_reseller.credits_balance = 1
    db.commit()
    res = dbm.process_reseller_claim_for(fresh_reseller, fresh_product, 2, db)
    assert not res["success"] and res["error"] == "INSUFFICIENT_CREDITS"
    assert fresh_product.get_available_stock_count(db) == 3


def test_quantity_bounds(db, fresh_product, fresh_reseller):
    assert dbm.process_reseller_claim_for(fresh_reseller, fresh_product, 0, db)["error"] == "INVALID_QUANTITY"
    assert dbm.process_reseller_claim_for(fresh_reseller, fresh_product, 999, db)["error"] == "INVALID_QUANTITY"


def test_fulfill_order_is_idempotent_and_rejects_reused_utr(db, fresh_product):
    o1 = dbm.CustomerOrder(id=dbm.generate_order_id(db), product_id=fresh_product.id, unit_price=150, total_amount=150, session_id="s1")
    o2 = dbm.CustomerOrder(id=dbm.generate_order_id(db), product_id=fresh_product.id, unit_price=150, total_amount=150, session_id="s2")
    db.add_all([o1, o2])
    db.commit()

    first = dbm.fulfill_order(o1, "123456789012", db)
    assert first["success"] and not first["already_delivered"]
    again = dbm.fulfill_order(o1, "123456789012", db)
    assert again["success"] and again["already_delivered"] and again["link"] == first["link"]
    assert fresh_product.get_available_stock_count(db) == 2, "retry must not burn a second link"

    reused = dbm.fulfill_order(o2, "123456789012", db)
    assert not reused["success"] and reused["error"] == "PAYMENT_REF_REUSED"
