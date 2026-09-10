"""
Supplier integration: m00nshots "instant store" API (https://instant.m00nshots.store/api/v1).

Lets the bot AUTO-BUY a digital product from the supplier the moment a customer/reseller needs
one and local stock is short. The purchased `credentials` become normal single-use stock rows,
so the whole existing atomic wallet + delivery flow is reused unchanged.

Safety:
  * OFF by default; must be enabled in Settings and mapped per-product by the admin.
  * The API key is read from Settings (admin UI) or MOONSHOTS_API_KEY; it is NEVER logged and
    never returned to the browser (only a masked tail).
  * A per-product price cap (`supplier_max_price`) stops runaway spend if the supplier raises
    the price. Auto-buy quantity is clamped to MOONSHOTS_MAX_AUTOBUY_QTY.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from config import Config

logger = logging.getLogger(__name__)


class MoonshotsError(Exception):
    """A supplier API failure with a safe, human-readable message (never contains the key)."""

    def __init__(self, message: str, code: str = "error", status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def _settings_value(attr: str) -> Optional[str]:
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
    """Admin-UI key wins; else the environment key."""
    return (_settings_value("moonshots_api_key") or Config.MOONSHOTS_API_KEY or "").strip()


def base_url() -> str:
    return (Config.MOONSHOTS_API_URL or "https://instant.m00nshots.store/api/v1").rstrip("/")


def enabled_in_settings() -> bool:
    val = _settings_value("moonshots_enabled")
    return bool(val)


def is_ready() -> bool:
    """True when auto-buy can run: enabled in Settings AND a key is configured."""
    return enabled_in_settings() and bool(api_key())


def mask_key(value: Optional[str] = None) -> Optional[str]:
    v = (value if value is not None else api_key()) or ""
    return ("••••" + v[-4:]) if len(v) > 4 else ("••••" if v else None)


def _request(method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
             json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = api_key()
    if not key:
        raise MoonshotsError("Supplier API key not configured (Admin -> Settings -> m00nshots).", "no_key")
    url = f"{base_url()}{path}"
    try:
        resp = requests.request(
            method, url,
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            params=params, json=json_body,
            timeout=Config.MOONSHOTS_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise MoonshotsError(f"Could not reach the supplier ({type(exc).__name__}).", "network") from exc

    try:
        body = resp.json()
    except ValueError:
        body = {}

    if not resp.ok or not body.get("success", False):
        err = body.get("error") or {}
        code = err.get("code") or f"http_{resp.status_code}"
        msg = err.get("message") or f"Supplier returned HTTP {resp.status_code}."
        # Never let the Authorization header leak through an exception/proxy message.
        raise MoonshotsError(str(msg)[:300], str(code), resp.status_code)
    return body


# --- read-only calls -------------------------------------------------------------------------

def get_balance() -> Dict[str, Any]:
    """{'balance': float, 'currency': str}."""
    data = _request("GET", "/balance").get("data", {})
    return {"balance": float(data.get("balance", 0) or 0), "currency": (data.get("currency") or "USD").upper()}


def get_account() -> Dict[str, Any]:
    return _request("GET", "/me").get("data", {})


def list_products(search: str = "", in_stock: Optional[bool] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if search:
        params["search"] = search
    if in_stock is not None:
        params["in_stock"] = "true" if in_stock else "false"
    return _request("GET", "/products", params=params).get("data", []) or []


def get_product(supplier_product_id: int) -> Dict[str, Any]:
    return _request("GET", f"/products/{int(supplier_product_id)}").get("data", {})


_PRODUCT_CACHE: Dict[int, Dict[str, Any]] = {}   # supplier_product_id -> {"ts": float, "data": {...}}
PRODUCT_CACHE_SECONDS = 60


def get_product_cached(supplier_product_id: int, max_age: int = PRODUCT_CACHE_SECONDS) -> Dict[str, Any]:
    """Supplier product with a short cache so the Products tab can show live prices for many
    mapped products without burning the supplier's 120 req/min budget."""
    import time
    pid = int(supplier_product_id)
    hit = _PRODUCT_CACHE.get(pid)
    if hit and time.time() - hit["ts"] < max_age:
        return hit["data"]
    data = get_product(pid)
    _PRODUCT_CACHE[pid] = {"ts": time.time(), "data": data}
    return data


def product_summary(supplier_product_id: int, usd_to_inr: float, max_age: int = PRODUCT_CACHE_SECONDS) -> Dict[str, Any]:
    """Compact live view for the admin UI: name, $ price, ≈ ₹ price, stock. Errors are per-item."""
    try:
        d = get_product_cached(supplier_product_id, max_age=max_age)
        price = float(d.get("price") or 0)
        return {
            "supplier_product_id": int(supplier_product_id),
            "name": d.get("name"), "icon": d.get("icon"), "category": d.get("category"),
            "price": price, "currency": (d.get("currency") or "USD").upper(),
            "price_inr": round(price * float(usd_to_inr or 0), 2),
            "stock": d.get("stock"), "in_stock": bool(d.get("in_stock", (d.get("stock") or 0) > 0)),
            "min_qty": d.get("min_qty"), "max_qty": d.get("max_qty"), "warranty_days": d.get("warranty_days"),
            "error": None,
        }
    except MoonshotsError as exc:
        return {"supplier_product_id": int(supplier_product_id), "error": exc.message, "code": exc.code}
    except Exception as exc:  # noqa: BLE001
        return {"supplier_product_id": int(supplier_product_id), "error": f"{type(exc).__name__}", "code": "error"}


# --- the purchase ----------------------------------------------------------------------------

def place_order(supplier_product_id: int, quantity: int = 1) -> Dict[str, Any]:
    """
    Buy `quantity` of a supplier product. Returns the order dict incl. `credentials` (list[str]).
    NOTE: the supplier says orders are NOT idempotent — call this exactly once per intended buy.
    """
    body = _request("POST", "/orders", json_body={"product_id": int(supplier_product_id),
                                                   "quantity": int(quantity)})
    data = body.get("data", {})
    creds = [str(c) for c in (data.get("credentials") or []) if str(c).strip()]
    data["credentials"] = creds
    logger.info("m00nshots order %s: bought %s x product %s, %d credential(s), balance left %s",
                data.get("order_code"), quantity, supplier_product_id, len(creds), data.get("remaining_balance"))
    return data


def status_dict() -> Dict[str, Any]:
    """Admin status: enabled/key + live balance (best-effort)."""
    out: Dict[str, Any] = {
        "enabled": enabled_in_settings(),
        "has_key": bool(api_key()),
        "key_mask": mask_key(),
        "base_url": base_url(),
        "ready": is_ready(),
        "balance": None,
        "currency": None,
        "error": None,
    }
    if out["has_key"]:
        try:
            bal = get_balance()
            out["balance"], out["currency"] = bal["balance"], bal["currency"]
        except MoonshotsError as exc:
            out["error"] = exc.message
    return out
