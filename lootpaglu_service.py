"""
Supplier integration #2: Loot Paglu (https://lootpaglu.in, header `X-API-Key`).

Prices are in INR (`prices.upiPrice`) so no currency conversion is needed. Products are
identified by a string `service_id` (e.g. "Paglu_1"). There is no per-product endpoint, so the
whole list is fetched and cached briefly. Rate limit is 3 req/s per IP -> client-side throttle.

Same safety rules as moonshots_service: OFF by default, key from Settings (or LOOTPAGLU_API_KEY),
never logged / never sent to the browser (masked tail only).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import Config

logger = logging.getLogger(__name__)

NAME = "lootpaglu"
LABEL = "Loot Paglu"
CURRENCY = "INR"


class LootPagluError(Exception):
    def __init__(self, message: str, code: str = "error", status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def _settings_value(attr: str) -> Optional[Any]:
    try:
        from database import get_db, get_settings
        db = get_db()
        try:
            return getattr(get_settings(db), attr, None)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        return None


def api_key() -> str:
    return (_settings_value("lootpaglu_api_key") or Config.LOOTPAGLU_API_KEY or "").strip()


def base_url() -> str:
    return (Config.LOOTPAGLU_API_URL or "https://lootpaglu.in").rstrip("/")


def enabled_in_settings() -> bool:
    return bool(_settings_value("lootpaglu_enabled"))


def is_ready() -> bool:
    return enabled_in_settings() and bool(api_key())


def mask_key(value: Optional[str] = None) -> Optional[str]:
    v = (value if value is not None else api_key()) or ""
    return ("••••" + v[-4:]) if len(v) > 4 else ("••••" if v else None)


# 3 requests/second per IP at the supplier -> never send faster than ~2.5/s from this process.
_THROTTLE_LOCK = threading.Lock()
_LAST_CALL = {"ts": 0.0}
_MIN_GAP = 0.4


def _throttle() -> None:
    with _THROTTLE_LOCK:
        wait = _MIN_GAP - (time.time() - _LAST_CALL["ts"])
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL["ts"] = time.time()


def _request(method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
             json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = api_key()
    if not key:
        raise LootPagluError("Loot Paglu API key not configured (Admin -> Settings -> Loot Paglu).", "no_key")
    _throttle()
    try:
        resp = requests.request(
            method, f"{base_url()}{path}",
            headers={"X-API-Key": key, "Accept": "application/json", "Content-Type": "application/json"},
            params=params, json=json_body, timeout=Config.LOOTPAGLU_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise LootPagluError(f"Could not reach Loot Paglu ({type(exc).__name__}).", "network") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not resp.ok or (isinstance(body, dict) and body.get("error")):
        msg = (body.get("error") if isinstance(body, dict) else None) or f"Loot Paglu returned HTTP {resp.status_code}."
        code = {401: "unauthorized", 429: "rate_limited", 503: "paused", 404: "not_found"}.get(resp.status_code, f"http_{resp.status_code}")
        if "balance" in str(msg).lower():
            code = "insufficient_balance"
        elif "stock" in str(msg).lower():
            code = "out_of_stock"
        raise LootPagluError(str(msg)[:300], code, resp.status_code)
    return body if isinstance(body, dict) else {}


# --- read-only ---------------------------------------------------------------------------------

def get_balance() -> Dict[str, Any]:
    d = _request("GET", "/api/v1/me")
    return {"balance": float(d.get("wallet_inr", 0) or 0), "currency": CURRENCY,
            "balance_crypto": float(d.get("wallet_crypto", 0) or 0), "total_spent": d.get("total_spent")}


_LIST_CACHE: Dict[str, Any] = {"ts": 0.0, "items": []}
LIST_CACHE_SECONDS = 60


def list_products(max_age: int = LIST_CACHE_SECONDS) -> List[Dict[str, Any]]:
    """All services, normalised to the same shape the admin UI uses for m00nshots:
    {id, name, price (INR), currency, stock, in_stock, requires_verification}."""
    if _LIST_CACHE["items"] and time.time() - _LIST_CACHE["ts"] < max_age:
        return _LIST_CACHE["items"]
    raw = _request("GET", "/api/v1/products").get("services", []) or []
    items = []
    for svc in raw:
        items.append(_normalise_service(svc))
    # Price missing in the list (₹0)? Use what we actually PAID last time for that service (order
    # history, currency inr) - authoritative and never 0.
    if any(not it["price_known"] for it in items):
        hist = _order_history_unit_prices()
        for it in items:
            if not it["price_known"]:
                paid = hist.get(_norm_name(it["name"]))
                if paid and paid > 0:
                    it.update(price=paid, price_known=True, price_source="order_history", raw_keys=[])
    _LIST_CACHE.update(ts=time.time(), items=items)
    return items


def _norm_name(name: Any) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


_HIST_CACHE: Dict[str, Any] = {"ts": 0.0, "prices": {}}
HIST_CACHE_SECONDS = 600


def _order_history_unit_prices(max_age: int = HIST_CACHE_SECONDS) -> Dict[str, float]:
    """service name -> latest INR unit price we paid (amount / quantity), from /api/v1/orders."""
    if _HIST_CACHE["prices"] and time.time() - _HIST_CACHE["ts"] < max_age:
        return _HIST_CACHE["prices"]
    prices: Dict[str, float] = {}
    try:
        d = _request("GET", "/api/v1/orders", params={"page": 1, "limit": 100})
        for o in d.get("orders", []) or []:                      # newest first per the docs sample
            cur = str(o.get("currency") or "inr").lower()
            if cur not in ("inr", "upi", ""):
                continue
            name = _norm_name(o.get("service"))
            qty = int(_num(o.get("quantity")) or 1) or 1
            amt = _num(o.get("amount", o.get("total_cost")))
            if name and amt > 0 and name not in prices:
                prices[name] = round(amt / qty, 2)
    except Exception as exc:  # noqa: BLE001
        logger.info("Loot Paglu order history unavailable for price fallback: %s", type(exc).__name__)
    _HIST_CACHE.update(ts=time.time(), prices=prices)
    return prices


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("₹", "").replace("Rs", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _first_price(d: Dict[str, Any], keys) -> float:
    for k in keys:
        if k in d and _num(d.get(k)) > 0:
            return _num(d.get(k))
    return 0.0


_SKIP_TOKENS = ("crypto", "usd", "usdt", "btc", "eth", "stock", "qty", "quantity", "min", "max", "discount", "old",
                "original", "mrp", "warranty", "days", "id", "count", "sold", "total", "limit", "commission", "fee")
_INR_TOKENS = ("upi", "inr", "rupee", "rs")
_PRICE_TOKENS = ("price", "amount", "rate", "cost", "selling", "sale")


def _find_inr_price(obj: Any) -> Tuple[float, str]:
    """Walk the whole service object and return (value, key_path) of the most plausible INR price:
    keys mentioning upi/inr win; then generic price/amount/rate/cost; crypto/usd/stock-ish keys are
    skipped; a sibling `currency` field is honoured. Returns (0.0, '') when nothing > 0 is found."""
    best: Tuple[int, float, str] = (99, 0.0, "")

    def visit(node: Any, path: str, sibling_currency: str):
        nonlocal best
        if isinstance(node, dict):
            cur = str(node.get("currency") or node.get("curr") or sibling_currency or "").lower()
            for k, v in node.items():
                visit(v, f"{path}.{k}" if path else str(k), cur)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                visit(v, f"{path}[{i}]", sibling_currency)
        else:
            val = _num(node)
            if val <= 0:
                return
            key_l = path.lower()
            leaf = key_l.rsplit(".", 1)[-1]
            if any(t in leaf for t in _SKIP_TOKENS) or "crypto" in key_l:
                return
            if sibling_currency and any(t in sibling_currency for t in ("usd", "usdt", "btc", "crypto", "eth")):
                return
            if any(t in key_l for t in _INR_TOKENS) or (sibling_currency and "inr" in sibling_currency):
                pri = 0
            elif any(t in leaf for t in _PRICE_TOKENS):
                pri = 1
            else:
                return
            if pri < best[0]:
                best = (pri, val, path)

    visit(obj, "", "")
    return best[1], best[2]


def _key_paths(obj: Any, prefix: str = "", limit: int = 30) -> List[str]:
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                out.extend(_key_paths(v, path, limit))
            else:
                out.append(f"{path}={str(v)[:20]}")
            if len(out) >= limit:
                break
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            out.extend(_key_paths(v, f"{prefix}[{i}]", limit))
    return out[:limit]


def _normalise_service(svc: Dict[str, Any]) -> Dict[str, Any]:
    """Tolerant of key drift: the docs say prices.upiPrice, but a 0/missing value must NEVER look
    like a ₹0 bargain — it becomes price=0 which the orchestrator treats as 'price unavailable'."""
    prices = svc.get("prices") or svc.get("pricing") or svc.get("price") or {}
    if not isinstance(prices, dict):
        prices = {}
    price = _first_price(prices, ("upiPrice", "upi_price", "inr", "INR", "price_inr", "price")) \
        or _first_price(svc, ("upiPrice", "upi_price", "price_inr", "price", "inr_price"))
    price_source = "prices.upiPrice" if price > 0 else ""
    if price <= 0:
        price, price_source = _find_inr_price(svc)          # any shape: nested, list, odd names
    crypto = _first_price(prices, ("cryptoPrice", "crypto_price", "usd", "USD")) or _first_price(svc, ("cryptoPrice",))
    try:
        stock = int(_num(svc.get("available_stock", svc.get("stock", 0))))
    except (TypeError, ValueError):
        stock = 0
    return {
        "id": str(svc.get("service_id") or svc.get("id") or ""),
        "name": svc.get("name"),
        "price": price,
        "price_crypto": crypto,
        "currency": CURRENCY,
        "stock": stock, "in_stock": stock > 0,
        "requires_verification": bool(svc.get("requires_shein_verification")),
        "price_known": price > 0,
        "price_source": price_source,
        # when no price could be found, show the real field names so the admin can tell us
        "raw_keys": [] if price > 0 else _key_paths(svc),
    }


def raw_products() -> List[Dict[str, Any]]:
    """Untouched supplier payload (admin debug: see the real field names when a price shows 0)."""
    return _request("GET", "/api/v1/products").get("services", []) or []


def get_product(service_id: str, max_age: int = LIST_CACHE_SECONDS) -> Dict[str, Any]:
    sid = str(service_id or "").strip()
    for it in list_products(max_age=max_age):
        if it["id"] == sid:
            return it
    raise LootPagluError(f"Service '{sid}' not found at Loot Paglu", "not_found", 404)


def product_summary(service_id: str, usd_to_inr: float = 0.0, max_age: int = LIST_CACHE_SECONDS) -> Dict[str, Any]:
    """Compact live view (same keys as moonshots_service.product_summary; prices already INR)."""
    try:
        d = get_product(service_id, max_age=max_age)
        out = {"supplier": NAME, "ref": d["id"], "name": d["name"], "icon": "", "category": "",
               "price": d["price"], "currency": CURRENCY, "price_inr": round(d["price"], 2),
               "stock": d["stock"], "in_stock": d["in_stock"], "error": None}
        if not d.get("price_known", d["price"] > 0):
            out["error"] = "price unavailable at supplier (₹0 / missing) - not safe to auto-buy"
            out["code"] = "no_price"
        return out
    except LootPagluError as exc:
        return {"supplier": NAME, "ref": str(service_id), "error": exc.message, "code": exc.code}
    except Exception as exc:  # noqa: BLE001
        return {"supplier": NAME, "ref": str(service_id), "error": type(exc).__name__, "code": "error"}


# --- the purchase --------------------------------------------------------------------------------

def place_order(service_id: str, quantity: int = 1) -> Dict[str, Any]:
    """Buy `quantity` of a service with the INR wallet. Returns {"order_code", "credentials": [...], ...}.
    Not idempotent — call exactly once per intended buy."""
    d = _request("POST", "/api/v1/order", json_body={"service_id": str(service_id), "quantity": int(quantity), "currency": "inr"})
    if not d.get("success", d.get("status") == "success"):
        raise LootPagluError(str(d.get("message") or d.get("error") or "Order failed")[:300], "order_failed")
    creds = [str(c) for c in (d.get("products") or []) if str(c).strip()]
    out = {"order_code": d.get("order_id"), "credentials": creds, "unit_price": None,
           "total": d.get("total_cost", d.get("amountDeducted")), "remaining_balance": d.get("new_balance"),
           "currency": CURRENCY}
    if creds and out["total"] is not None:
        out["unit_price"] = round(float(out["total"]) / len(creds), 2)
        try:                                                      # remember the real ₹ price for this service
            for it in _LIST_CACHE.get("items") or []:
                if it["id"] == str(service_id):
                    _HIST_CACHE["prices"][_norm_name(it["name"])] = out["unit_price"]
                    _HIST_CACHE["ts"] = time.time()
        except Exception:  # noqa: BLE001
            pass
    _LIST_CACHE["ts"] = 0.0   # stock changed
    logger.info("Loot Paglu order %s: bought %s x %s, %d code(s), balance left %s",
                out["order_code"], quantity, service_id, len(creds), out["remaining_balance"])
    return out


def status_dict() -> Dict[str, Any]:
    out: Dict[str, Any] = {"supplier": NAME, "label": LABEL, "enabled": enabled_in_settings(), "has_key": bool(api_key()),
                           "key_mask": mask_key(), "base_url": base_url(), "ready": is_ready(),
                           "balance": None, "currency": CURRENCY, "error": None}
    if out["has_key"]:
        try:
            bal = get_balance()
            out["balance"] = bal["balance"]
            out["balance_crypto"] = bal.get("balance_crypto")
        except LootPagluError as exc:
            out["error"] = exc.message
    return out
