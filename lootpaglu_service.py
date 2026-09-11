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
from typing import Any, Dict, List, Optional

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
        stock = int(svc.get("available_stock") or 0)
        items.append({
            "id": str(svc.get("service_id") or ""),
            "name": svc.get("name"),
            "price": float(((svc.get("prices") or {}).get("upiPrice")) or 0),
            "price_crypto": float(((svc.get("prices") or {}).get("cryptoPrice")) or 0),
            "currency": CURRENCY,
            "stock": stock, "in_stock": stock > 0,
            "requires_verification": bool(svc.get("requires_shein_verification")),
        })
    _LIST_CACHE.update(ts=time.time(), items=items)
    return items


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
        return {"supplier": NAME, "ref": d["id"], "name": d["name"], "icon": "", "category": "",
                "price": d["price"], "currency": CURRENCY, "price_inr": round(d["price"], 2),
                "stock": d["stock"], "in_stock": d["in_stock"], "error": None}
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
