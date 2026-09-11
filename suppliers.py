"""
Multi-supplier auto-buy orchestrator.

A local product can be mapped to one or more suppliers (m00nshots product id, Loot Paglu service
id). When stock is short at claim/fulfil time, we fetch a FRESH live quote from every mapped
supplier, convert to INR, drop anything over the admin's price cap or out of stock, and buy from
the CHEAPEST (or the admin's forced preference). The purchased codes become normal single-use
stock rows, so the existing atomic wallet + delivery flow is reused unchanged.

Never raises into the sale path: any supplier failure -> bought=0 -> normal out-of-stock handling,
no wallet charge.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from config import Config

logger = logging.getLogger(__name__)

SUPPLIER_ORDER = ("moonshots", "lootpaglu")          # tie-break order when prices are equal
LABELS = {"moonshots": "m00nshots", "lootpaglu": "Loot Paglu"}
PREFERENCES = ("cheapest", "moonshots", "lootpaglu")


def _mods() -> Dict[str, Any]:
    import moonshots_service as ms
    import lootpaglu_service as lp
    return {"moonshots": ms, "lootpaglu": lp}


def refs_for(product) -> Dict[str, Any]:
    """supplier -> reference id, honouring a legacy per-supplier `source` ('moonshots'/'lootpaglu')."""
    out: Dict[str, Any] = {}
    if getattr(product, "supplier_product_id", None):
        out["moonshots"] = int(product.supplier_product_id)
    sid = str(getattr(product, "lootpaglu_service_id", None) or "").strip()
    if sid:
        out["lootpaglu"] = sid
    src = (getattr(product, "source", "stock") or "stock")
    if src in ("moonshots", "lootpaglu"):
        out = {k: v for k, v in out.items() if k == src}
    return out


def is_supplier_backed(product) -> bool:
    return (getattr(product, "source", "stock") or "stock") != "stock" and bool(refs_for(product))


def any_ready(product=None) -> bool:
    mods = _mods()
    names = refs_for(product).keys() if product is not None else SUPPLIER_ORDER
    return any(mods[n].is_ready() for n in names)


def price_cap_inr(product, usd_to_inr: float) -> Optional[float]:
    """Admin ceiling in INR. Legacy `supplier_max_price` was a USD cap for m00nshots -> convert."""
    cap = getattr(product, "max_buy_price_inr", None)
    if cap is not None:
        return float(cap)
    legacy = getattr(product, "supplier_max_price", None)
    if legacy is not None:
        return float(legacy) * float(usd_to_inr or 0)
    return None


def quotes_for(product, usd_to_inr: float, fresh: bool = False) -> List[Dict[str, Any]]:
    """One live quote per mapped supplier (errors are per-quote, never raised)."""
    mods = _mods()
    quotes: List[Dict[str, Any]] = []
    for name, ref in refs_for(product).items():
        mod = mods[name]
        q: Dict[str, Any] = {"supplier": name, "label": LABELS[name], "ref": ref, "ready": bool(mod.is_ready()),
                             "name": None, "price": None, "currency": None, "price_inr": None,
                             "stock": 0, "in_stock": False, "error": None}
        if not q["ready"]:
            q["error"] = "disabled or no API key"
            quotes.append(q)
            continue
        try:
            summ = mod.product_summary(ref, usd_to_inr, max_age=0 if fresh else 60)
        except Exception as exc:  # noqa: BLE001
            summ = {"error": type(exc).__name__}
        for k in ("name", "price", "currency", "price_inr", "stock", "in_stock", "error", "code"):
            if k in summ:
                q[k] = summ[k]
        quotes.append(q)
    return quotes


def choose(quotes: List[Dict[str, Any]], needed: int, preference: str = "cheapest",
           cap_inr: Optional[float] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    """Pick the supplier to buy from. Returns (quote|None, reason)."""
    needed = max(1, int(needed or 1))
    usable = [q for q in quotes if q.get("ready") and not q.get("error") and q.get("price_inr") is not None]
    if not usable:
        errs = "; ".join(f"{q['label']}: {q.get('error')}" for q in quotes if q.get("error")) or "no supplier mapped"
        return None, errs
    if preference in ("moonshots", "lootpaglu"):
        forced = [q for q in usable if q["supplier"] == preference]
        if not forced:
            return None, f"{LABELS[preference]} unavailable (forced preference)"
        usable = forced
    if cap_inr is not None:
        under = [q for q in usable if float(q["price_inr"]) <= cap_inr]
        if not under:
            cheapest = min(usable, key=lambda q: float(q["price_inr"]))
            return None, f"supplier price ₹{float(cheapest['price_inr']):.2f} above cap ₹{cap_inr:.2f}"
        usable = under
    enough = [q for q in usable if int(q.get("stock") or 0) >= needed]
    pool = enough or [q for q in usable if int(q.get("stock") or 0) >= 1]
    if not pool:
        return None, "out of stock at every mapped supplier"
    best = min(pool, key=lambda q: (float(q["price_inr"]), SUPPLIER_ORDER.index(q["supplier"])))
    others = [q for q in usable if q is not best]
    if preference in ("moonshots", "lootpaglu"):
        why = f"forced {best['label']}"
    elif others:
        why = "cheapest: " + " vs ".join(f"{q['label']} ₹{float(q['price_inr']):.2f}" for q in [best] + others)
    else:
        why = f"only {best['label']} mapped"
    if not enough:
        why += f" (only {best.get('stock')} in stock, wanted {needed})"
    return best, why


def quotes_with_choice(product, usd_to_inr: float, needed: int = 1, fresh: bool = False) -> Dict[str, Any]:
    """For the admin UI: every quote + which one the bot would buy from right now, and why."""
    quotes = quotes_for(product, usd_to_inr, fresh=fresh)
    cap = price_cap_inr(product, usd_to_inr)
    best, reason = choose(quotes, needed, getattr(product, "supplier_preference", None) or "cheapest", cap)
    for q in quotes:
        q["chosen"] = bool(best is not None and q is best)
    return {"quotes": quotes, "chosen": best["supplier"] if best else None, "reason": reason, "cap_inr": cap,
            "preference": getattr(product, "supplier_preference", None) or "cheapest"}


def buy(supplier: str, ref: Any, quantity: int) -> Dict[str, Any]:
    """Place ONE order at a supplier. Returns {"order_code", "credentials": [...], "unit_price"?}."""
    return _mods()[supplier].place_order(ref, int(quantity))


def replenish(db, product, needed: int) -> Dict[str, Any]:
    """
    If local available stock < needed for a supplier-backed product, buy the shortfall from the
    best supplier and insert the codes as available stock. Commits on its own. Never raises.
    """
    from database import InviteLink, get_settings
    result: Dict[str, Any] = {"bought": 0, "order_code": None, "error": None, "supplier": None,
                              "unit_price_inr": None, "reason": None}
    if not is_supplier_backed(product):
        return result
    if not any_ready(product):
        result["error"] = "supplier disabled or no API key"
        return result
    available = product.get_available_stock_count(db)
    shortfall = int(needed) - int(available)
    if shortfall <= 0:
        return result
    shortfall = min(shortfall, Config.MOONSHOTS_MAX_AUTOBUY_QTY)
    try:
        rate = float(get_settings(db).usd_to_inr_rate or 83.0)
        quotes = quotes_for(product, rate, fresh=True)          # re-read price/stock right before spending
        best, reason = choose(quotes, shortfall, getattr(product, "supplier_preference", None) or "cheapest",
                              price_cap_inr(product, rate))
        result["reason"] = reason
        if best is None:
            result["error"] = reason
            logger.warning("Auto-buy skipped for %s: %s", product.slug, reason)
            return result
        qty = min(shortfall, max(1, int(best.get("stock") or shortfall)))
        order = buy(best["supplier"], best["ref"], qty)
        creds = order.get("credentials") or []
        if not creds:
            result["error"] = f"{best['label']} returned no credentials"
            logger.error("Auto-buy for %s at %s returned 0 credentials (order %s)", product.slug, best["supplier"], order.get("order_code"))
            return result
        code = order.get("order_code")
        for cred in creds:
            db.add(InviteLink(product_id=product.id, link_or_key=str(cred), status="available",
                              source=best["supplier"], notes=f"{best['label']} {code} @₹{float(best['price_inr']):.2f}"))
        db.commit()
        result.update(bought=len(creds), order_code=code, supplier=best["supplier"],
                      unit_price_inr=float(best["price_inr"]))
        logger.info("Auto-bought %d x %s from %s (order %s) - %s", len(creds), product.slug, best["supplier"], code, reason)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        msg = getattr(exc, "message", str(exc))
        result["error"] = msg
        logger.exception("replenish failed for %s: %s", product.slug, msg)
    return result


def status_all() -> Dict[str, Any]:
    mods = _mods()
    return {name: mods[name].status_dict() for name in SUPPLIER_ORDER}
