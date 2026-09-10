"""
Flask application: public chat API, authenticated admin API, WhatsApp webhook,
and the built React frontend.

Security model
* `/api/admin/*`  - requires `X-Admin-Token` (or `Authorization: Bearer`) == ADMIN_API_KEY.
* `/api/chat/*`   - public, but each browser only sees its own sessions (`X-Client-Id`).
* `/api/webhook/evolution` - optional shared secret; processed asynchronously.
* In-process rate limiting on chat, admin login and webhook.
"""
import os
import io
import re
import json
import hmac
import time
import logging
import threading
from collections import defaultdict, deque, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
from sqlalchemy import func
import qrcode

from config import Config, validate_config, configure_logging

configure_logging()
validate_config()

from database import (  # noqa: E402  (config must load first)
    init_db,
    get_db,
    get_settings,
    utcnow,
    Product,
    InviteLink,
    Reseller,
    CreditTransaction,
    CustomerOrder,
    ChatSessionRecord,
    ChatMessageRecord,
    KnowledgeEntry,
    WalletTransaction,
    fulfill_order,
    normalize_phone,
    is_valid_secret_code,
    adjust_reseller_wallet,
    stock_counts_by_product,
)
from agent_core import run_deep_agent_chat, agent_status, test_llm_connection, invalidate_agent_cache  # noqa: E402
from evolution_service import parse_evolution_webhook_payload, send_whatsapp_message  # noqa: E402

logger = logging.getLogger(__name__)

# =====================================================================
# App setup
# =====================================================================

FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
app = Flask(__name__, static_folder=FRONTEND_DIST, static_url_path="")
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False

if Config.TRUST_PROXY:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

CORS(
    app,
    resources={r"/api/*": {"origins": Config.CORS_ORIGINS}},
    allow_headers=["Content-Type", "X-Admin-Token", "X-Client-Id", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)

with app.app_context():
    init_db()

_webhook_executor = ThreadPoolExecutor(max_workers=Config.WEBHOOK_WORKERS, thread_name_prefix="wa-webhook")


# =====================================================================
# Rate limiting (sliding window, per process)
# =====================================================================

class RateLimiter:
    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < now - window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            if len(self._hits) > 20000:  # keep memory bounded
                for stale in [k for k, v in self._hits.items() if not v or v[-1] < now - window_seconds][:5000]:
                    self._hits.pop(stale, None)
            return True


_limiter = RateLimiter()


def client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip() if Config.TRUST_PROXY else (request.remote_addr or "?")


def rate_limited(limit: int, scope: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not _limiter.allow(f"{scope}:{client_ip()}", limit):
                return jsonify({"error": "Too many requests. Please slow down."}), 429
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# =====================================================================
# Auth helpers
# =====================================================================

def _admin_token_from_request() -> str:
    token = request.headers.get("X-Admin-Token", "")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    return token.strip()


def admin_auth_open() -> bool:
    """True when no ADMIN_API_KEY is configured - the admin dashboard is then open to all."""
    return not Config.ADMIN_API_KEY


def is_admin_request() -> bool:
    """A caller that presented a valid admin token (only meaningful when a key is set)."""
    token = _admin_token_from_request()
    return bool(token) and bool(Config.ADMIN_API_KEY) and hmac.compare_digest(token, Config.ADMIN_API_KEY)


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Open when no key is configured; otherwise a valid token is required.
        if admin_auth_open() or is_admin_request():
            return fn(*args, **kwargs)
        return jsonify({"error": "Unauthorized. Provide a valid admin token."}), 401
    return wrapper


_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,100}$")


def client_owner_id():
    """Browser-generated id that scopes chat sessions to one client."""
    cid = request.headers.get("X-Client-Id", "").strip()
    return cid if _CLIENT_ID_RE.match(cid) else None


def _session_visible(session_rec: ChatSessionRecord) -> bool:
    if is_admin_request():
        return True
    owner = client_owner_id()
    if session_rec.owner_id is None:
        return True  # legacy sessions created before ownership existed
    return owner is not None and session_rec.owner_id == owner


# =====================================================================
# Request/response hooks & error handlers
# =====================================================================

@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(404)
def _not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint not found"}), 404
    if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return send_file(os.path.join(FRONTEND_DIST, "index.html"))
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def _method_not_allowed(_e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(413)
def _too_large(_e):
    return jsonify({"error": "Request body too large"}), 413


@app.errorhandler(Exception)
def _unhandled(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    logger.exception("Unhandled error on %s %s", request.method, request.path)
    body = {"error": "Internal server error"}
    if not Config.IS_PROD:
        body["detail"] = str(e)
    return jsonify(body), 500


def _payload() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# =====================================================================
# Frontend & health
# =====================================================================

@app.route("/", methods=["GET"])
def serve_frontend_root():
    index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index):
        return send_file(index)
    return jsonify({"service": "AI Digital Vending & Reseller Deep Agent", "status": "online",
                    "frontend": "Build it with `cd frontend && npm run build`"})


@app.route("/<path:path>", methods=["GET"])
def serve_frontend_static(path):
    if path.startswith("api/"):
        return jsonify({"error": "Endpoint not found"}), 404
    file_path = os.path.normpath(os.path.join(FRONTEND_DIST, path))
    if file_path.startswith(os.path.normpath(FRONTEND_DIST)) and os.path.isfile(file_path):
        return send_file(file_path)
    index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index):
        return send_file(index)
    return jsonify({"error": "File not found"}), 404


@app.route("/api/health", methods=["GET"])
def health_check():
    from sqlalchemy import text as sql_text
    db = get_db()
    try:
        db.execute(sql_text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    finally:
        db.close()
    status = agent_status()
    return jsonify({
        "status": "online" if db_ok else "degraded",
        "env": Config.APP_ENV,
        "database": "ok" if db_ok else "error",
        "engine": status["engine"],
        "model": status["model"],
        "admin_auth_required": bool(Config.ADMIN_API_KEY),
        "timestamp": datetime.utcnow().isoformat(),
    }), (200 if db_ok else 503)


@app.route("/api/qr/upi", methods=["GET"])
def generate_upi_qr():
    """Live UPI QR image. Amount/order id are validated so nothing odd lands in the payload."""
    db = get_db()
    try:
        settings = get_settings(db)
    finally:
        db.close()
    amount = request.args.get("amount", "").strip()
    order_id = request.args.get("order_id", "").strip()
    if amount and not re.fullmatch(r"\d{1,7}(\.\d{1,2})?", amount):
        return jsonify({"error": "Invalid amount"}), 400
    if order_id and not re.fullmatch(r"[A-Za-z0-9\-]{1,30}", order_id):
        return jsonify({"error": "Invalid order id"}), 400

    upi_payload = f"upi://pay?pa={settings.admin_upi_id}&pn={settings.admin_upi_name}&cu=INR"
    if amount:
        upi_payload += f"&am={amount}"
    if order_id:
        upi_payload += f"&tn={order_id}"

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(upi_payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#10b981", back_color="#0f172a")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# =====================================================================
# Chat API (public, client-scoped)
# =====================================================================

@app.route("/api/chat", methods=["POST"])
@rate_limited(Config.RATE_LIMIT_CHAT_PER_MIN, "chat")
def chat_endpoint():
    data = _payload()
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Message cannot be empty"}), 400
    if len(message) > Config.MAX_MESSAGE_LENGTH:
        return jsonify({"error": f"Message too long (max {Config.MAX_MESSAGE_LENGTH} characters)"}), 400

    user_type_hint = data.get("user_type_hint", "customer")
    if user_type_hint not in ("customer", "reseller"):
        user_type_hint = "customer"
    owner = client_owner_id()
    session_id = str(data.get("session_id") or "").strip()
    if session_id and not re.fullmatch(r"[A-Za-z0-9_\-]{4,100}", session_id):
        return jsonify({"error": "Invalid session id"}), 400
    if not session_id:
        session_id = f"chat_{int(time.time() * 1000)}"

    db = get_db()
    try:
        existing = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
        if existing and not _session_visible(existing):
            return jsonify({"error": "Forbidden"}), 403
        if existing and existing.platform == "whatsapp" and not is_admin_request():
            return jsonify({"error": "Forbidden"}), 403
    finally:
        db.close()

    result = run_deep_agent_chat(
        session_id=session_id,
        user_message=message,
        user_type_hint=user_type_hint,
        platform="web",
        owner_id=owner,
    )
    return jsonify(result), (200 if result.get("success") else 500)


@app.route("/api/chat/sessions", methods=["GET"])
def list_chat_sessions():
    db = get_db()
    try:
        q = db.query(ChatSessionRecord)
        if is_admin_request():
            platform = request.args.get("platform")
            if platform:
                q = q.filter(ChatSessionRecord.platform == platform)
            limit = 100
        else:
            owner = client_owner_id()
            if not owner:
                return jsonify([])
            q = q.filter(ChatSessionRecord.owner_id == owner)
            limit = 30
        sessions = q.order_by(ChatSessionRecord.updated_at.desc()).limit(limit).all()
        return jsonify([s.to_dict() for s in sessions])
    finally:
        db.close()


@app.route("/api/chat/history/<session_id>", methods=["GET"])
def get_chat_history(session_id):
    db = get_db()
    try:
        session_rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
        if not session_rec:
            return jsonify({"session_id": session_id, "messages": []})
        if not _session_visible(session_rec):
            return jsonify({"error": "Forbidden"}), 403
        messages = db.query(ChatMessageRecord).filter(ChatMessageRecord.session_id == session_id).order_by(ChatMessageRecord.id.asc()).all()
        formatted = []
        for m in messages:
            item = m.to_dict()
            try:
                item["metadata"] = json.loads(m.metadata_json) if m.metadata_json else {}
            except Exception:  # noqa: BLE001
                item["metadata"] = {}
            formatted.append(item)
        return jsonify({"session": session_rec.to_dict(), "messages": formatted})
    finally:
        db.close()


@app.route("/api/chat/sessions/new", methods=["POST"])
@rate_limited(Config.RATE_LIMIT_CHAT_PER_MIN, "chat-new")
def create_new_session():
    data = _payload()
    user_type = data.get("user_type", "customer")
    if user_type not in ("customer", "reseller"):
        user_type = "customer"
    session_id = f"chat_{int(time.time() * 1000)}"
    db = get_db()
    try:
        rec = ChatSessionRecord(id=session_id, owner_id=client_owner_id(), platform="web", user_type=user_type, title="New Conversation")
        db.add(rec)
        db.commit()
        return jsonify(rec.to_dict()), 201
    finally:
        db.close()


@app.route("/api/chat/sessions/<session_id>", methods=["DELETE"])
def delete_chat_session(session_id):
    db = get_db()
    try:
        rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
        if rec:
            if not _session_visible(rec):
                return jsonify({"error": "Forbidden"}), 403
            db.delete(rec)
            db.commit()
        return jsonify({"success": True})
    finally:
        db.close()


# =====================================================================
# Admin: auth & diagnostics
# =====================================================================

@app.route("/api/admin/login", methods=["POST"])
@rate_limited(Config.RATE_LIMIT_ADMIN_LOGIN_PER_MIN, "admin-login")
def admin_login():
    if admin_auth_open():
        return jsonify({"ok": True, "auth_required": False})
    token = str(_payload().get("token", "")).strip() or _admin_token_from_request()
    if token and hmac.compare_digest(token, Config.ADMIN_API_KEY):
        return jsonify({"ok": True, "auth_required": True})
    return jsonify({"ok": False, "error": "Invalid admin token"}), 401


@app.route("/api/admin/agent/status", methods=["GET"])
@require_admin
def admin_agent_status():
    return jsonify(agent_status())


@app.route("/api/admin/agent/test", methods=["POST"])
@require_admin
def admin_agent_test():
    return jsonify(test_llm_connection())


@app.route("/api/admin/metrics", methods=["GET"])
@require_admin
def get_admin_metrics():
    db = get_db()
    try:
        available = db.query(func.count(InviteLink.id)).filter(InviteLink.status == "available").scalar() or 0
        claimed = db.query(func.count(InviteLink.id)).filter(InviteLink.status == "claimed").scalar() or 0
        total_products = db.query(func.count(Product.id)).scalar() or 0
        total_resellers = db.query(func.count(Reseller.id)).scalar() or 0
        # Wallet money across resellers, normalised to INR for the dashboard card.
        usd_rate = float(get_settings(db).usd_to_inr_rate or 83.0)
        total_wallet_inr = 0.0
        for bal, cur in db.query(Reseller.wallet_balance, Reseller.currency).all():
            total_wallet_inr += float(bal or 0) * (usd_rate if (cur or "INR").upper() == "USD" else 1.0)
        revenue = db.query(func.coalesce(func.sum(CustomerOrder.total_amount), 0.0)).filter(CustomerOrder.status.in_(["delivered", "fulfillment_pending"])).scalar() or 0.0
        pending_orders = db.query(func.count(CustomerOrder.id)).filter(CustomerOrder.status == "pending_payment").scalar() or 0
        needs_fulfilment = db.query(func.count(CustomerOrder.id)).filter(CustomerOrder.status == "fulfillment_pending").scalar() or 0
        # One aggregate query for stock (scales to large catalogues); cap the alert list.
        stock_map = stock_counts_by_product(db)
        low_stock = [
            {"id": pid, "name": name, "stock": stock_map.get(pid, 0)}
            for pid, name in db.query(Product.id, Product.name).filter(Product.is_active == True).order_by(Product.id).all()  # noqa: E712
            if stock_map.get(pid, 0) <= 2
        ][:25]
        recent_claims = db.query(InviteLink).filter(InviteLink.status == "claimed").order_by(InviteLink.claimed_at.desc()).limit(8).all()
        return jsonify({
            "total_products": total_products,
            "available_links": available,
            "claimed_links": claimed,
            "total_resellers": total_resellers,
            "total_wallet_balance_inr": round(total_wallet_inr, 2),
            "total_customer_revenue": float(revenue),
            "pending_orders": pending_orders,
            "orders_needing_fulfilment": needs_fulfilment,
            "low_stock_products": low_stock,
            "recent_claims": [c.to_dict() for c in recent_claims],
            "agent": agent_status(),
        })
    finally:
        db.close()


# =====================================================================
# Admin: products & margin
# =====================================================================

def _validate_product_payload(data: dict, partial: bool = False):
    errors = []
    if not partial or "name" in data:
        if not str(data.get("name", "")).strip():
            errors.append("name is required")
    for field, lo, hi in (("base_price", 0, 10_000_000), ("margin_percent", 0, 10_000), ("reseller_margin_percent", 0, 10_000)):
        if field in data or not partial:
            try:
                val = float(data.get(field, 0))
                if not (lo <= val <= hi):
                    errors.append(f"{field} must be between {lo} and {hi}")
            except (TypeError, ValueError):
                errors.append(f"{field} must be a number")
    if "credit_cost" in data:
        try:
            if int(data.get("credit_cost", 1)) < 1:
                errors.append("credit_cost must be >= 1")
        except (TypeError, ValueError):
            errors.append("credit_cost must be an integer")
    if data.get("reseller_price") not in (None, ""):
        try:
            if not (0 <= float(data["reseller_price"]) <= 10_000_000):
                errors.append("reseller_price must be between 0 and 10000000")
        except (TypeError, ValueError):
            errors.append("reseller_price must be a number")
    return errors


def _reseller_price_from(data: dict):
    """None/'' -> NULL (use base price); otherwise the given INR price."""
    v = data.get("reseller_price")
    return None if v in (None, "") else float(v)


def _slugify(text_value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text_value).lower()).strip("-")
    return slug[:100] or f"product-{int(time.time())}"


@app.route("/api/admin/products", methods=["GET"])
@require_admin
def list_admin_products():
    """Product list with stock computed in ONE aggregate query. Optional ?q= search,
    ?limit=/?offset= paging for very large catalogues (default: all, for the current UI)."""
    db = get_db()
    try:
        q = db.query(Product)
        term = (request.args.get("q") or "").strip()
        if term:
            q = q.filter((Product.name.ilike(f"%{term}%")) | (Product.slug.ilike(f"%{term}%")))
        try:
            limit = int(request.args.get("limit", 0) or 0)
            offset = int(request.args.get("offset", 0) or 0)
        except ValueError:
            limit, offset = 0, 0
        q = q.order_by(Product.id.asc())
        if offset:
            q = q.offset(offset)
        if limit:
            q = q.limit(min(limit, 5000))
        products = q.all()
        stock_map = stock_counts_by_product(db, [p.id for p in products])
        return jsonify([p.to_dict(stock=stock_map.get(p.id, 0)) for p in products])
    finally:
        db.close()


def _apply_supplier_fields(product, data):
    """Set product.source / supplier_product_id / supplier_max_price from a payload. Returns error str|None."""
    if "source" in data:
        src = str(data["source"]).strip().lower()
        if src not in ("stock", "moonshots"):
            return "source must be 'stock' or 'moonshots'"
        product.source = src
    if "supplier_product_id" in data:
        v = data["supplier_product_id"]
        if v in (None, ""):
            product.supplier_product_id = None
        else:
            try:
                product.supplier_product_id = int(v)
            except (TypeError, ValueError):
                return "supplier_product_id must be an integer"
    if "supplier_max_price" in data:
        v = data["supplier_max_price"]
        if v in (None, ""):
            product.supplier_max_price = None
        else:
            try:
                product.supplier_max_price = max(0.0, float(v))
            except (TypeError, ValueError):
                return "supplier_max_price must be a number"
    if (product.source or "stock") == "moonshots" and not product.supplier_product_id:
        return "A m00nshots product needs a supplier_product_id"
    return None


@app.route("/api/admin/products", methods=["POST"])
@require_admin
def create_admin_product():
    data = _payload()
    errors = _validate_product_payload(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    db = get_db()
    try:
        slug = _slugify(data.get("slug") or data.get("name"))
        if db.query(Product).filter(Product.slug == slug).first():
            return jsonify({"error": f"A product with slug '{slug}' already exists"}), 409
        product = Product(
            name=str(data["name"]).strip()[:150],
            slug=slug,
            category=str(data.get("category", "AI Tools"))[:50],
            description=str(data.get("description", ""))[:2000],
            base_price=float(data.get("base_price", 0.0)),
            margin_percent=float(data.get("margin_percent", 30.0)),
            reseller_margin_percent=float(data.get("reseller_margin_percent", 0.0) or 0.0),
            credit_cost=int(data.get("credit_cost", 1) or 1),
            # Legacy explicit price still accepted; the margin slider is the primary control.
            reseller_price=_reseller_price_from(data) if "reseller_margin_percent" not in data else None,
            is_active=bool(data.get("is_active", True)),
        )
        supplier_err = _apply_supplier_fields(product, data)
        if supplier_err:
            return jsonify({"error": supplier_err}), 400
        db.add(product)
        db.commit()
        return jsonify(product.to_dict(db)), 201
    finally:
        db.close()


@app.route("/api/admin/products/<int:prod_id>", methods=["PUT"])
@require_admin
def update_admin_product(prod_id):
    data = _payload()
    errors = _validate_product_payload(data, partial=True)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    db = get_db()
    try:
        product = db.query(Product).filter(Product.id == prod_id).first()
        if not product:
            return jsonify({"error": "Product not found"}), 404
        if "name" in data: product.name = str(data["name"]).strip()[:150]
        if "category" in data: product.category = str(data["category"])[:50]
        if "description" in data: product.description = str(data["description"])[:2000]
        if "base_price" in data: product.base_price = float(data["base_price"])
        if "margin_percent" in data: product.margin_percent = float(data["margin_percent"])
        if "reseller_margin_percent" in data:
            product.reseller_margin_percent = float(data["reseller_margin_percent"] or 0.0)
            product.reseller_price = None   # the slider now drives the reseller price
        if "credit_cost" in data: product.credit_cost = int(data["credit_cost"] or 1)
        if "reseller_price" in data and "reseller_margin_percent" not in data:
            product.reseller_price = _reseller_price_from(data)
        if "is_active" in data: product.is_active = bool(data["is_active"])
        supplier_err = _apply_supplier_fields(product, data)
        if supplier_err:
            return jsonify({"error": supplier_err}), 400
        db.commit()
        return jsonify(product.to_dict(db))
    finally:
        db.close()


@app.route("/api/admin/products/<int:prod_id>/margin", methods=["POST"])
@require_admin
def update_product_margin_instant(prod_id):
    """Instant margin change (customer and/or reseller slider) - the agent quotes the new
    prices on the very next turn: customer margin -> customer price, reseller margin -> what a
    reseller's wallet is charged per link."""
    data = _payload()
    try:
        new_margin = float(data.get("margin_percent"))
    except (TypeError, ValueError):
        return jsonify({"error": "margin_percent must be a number"}), 400
    if not (0 <= new_margin <= 10_000):
        return jsonify({"error": "margin_percent out of range"}), 400
    new_reseller_margin = None
    if data.get("reseller_margin_percent") not in (None, ""):
        try:
            new_reseller_margin = float(data["reseller_margin_percent"])
        except (TypeError, ValueError):
            return jsonify({"error": "reseller_margin_percent must be a number"}), 400
        if not (0 <= new_reseller_margin <= 10_000):
            return jsonify({"error": "reseller_margin_percent out of range"}), 400
    db = get_db()
    try:
        product = db.query(Product).filter(Product.id == prod_id).first()
        if not product:
            return jsonify({"error": "Product not found"}), 404
        product.margin_percent = new_margin
        if new_reseller_margin is not None:
            product.reseller_margin_percent = new_reseller_margin
            product.reseller_price = None   # slider is now the source of truth
        db.commit()
        logger.info("Margins for %s: customer %.2f%% -> ₹%.2f, reseller %.2f%% -> ₹%.2f", product.slug,
                    product.margin_percent, product.get_customer_price(),
                    float(product.reseller_margin_percent or 0), product.get_reseller_price())
        return jsonify({
            "success": True,
            "product_id": product.id,
            "product_name": product.name,
            "base_price": product.base_price,
            "new_margin_percent": product.margin_percent,
            "new_live_customer_price": product.get_customer_price(),
            "new_reseller_margin_percent": float(product.reseller_margin_percent or 0),
            "new_live_reseller_price": product.get_reseller_price(),
        })
    finally:
        db.close()


@app.route("/api/admin/products/<int:prod_id>", methods=["DELETE"])
@require_admin
def delete_admin_product(prod_id):
    db = get_db()
    try:
        product = db.query(Product).filter(Product.id == prod_id).first()
        if not product:
            return jsonify({"error": "Product not found"}), 404
        if db.query(CustomerOrder.id).filter(CustomerOrder.product_id == prod_id).first():
            # Keep order history intact: deactivate instead of deleting.
            product.is_active = False
            db.commit()
            return jsonify({"success": True, "deactivated": True, "message": "Product has orders; it was deactivated instead of deleted."})
        db.delete(product)
        db.commit()
        return jsonify({"success": True, "deactivated": False})
    finally:
        db.close()


# =====================================================================
# Admin: inventory
# =====================================================================

@app.route("/api/admin/inventory", methods=["GET"])
@require_admin
def list_admin_inventory():
    status_filter = request.args.get("status")
    product_id_filter = request.args.get("product_id")
    try:
        limit = min(int(request.args.get("limit", 200)), 1000)
    except ValueError:
        limit = 200
    db = get_db()
    try:
        q = db.query(InviteLink)
        if status_filter in ("available", "claimed", "used"):
            q = q.filter(InviteLink.status == status_filter)
        if product_id_filter and product_id_filter.isdigit():
            q = q.filter(InviteLink.product_id == int(product_id_filter))
        return jsonify([lk.to_dict() for lk in q.order_by(InviteLink.id.desc()).limit(limit).all()])
    finally:
        db.close()


@app.route("/api/admin/inventory/bulk-upload", methods=["POST"])
@require_admin
def bulk_upload_links():
    data = _payload()
    product_id = data.get("product_id")
    if not product_id:
        return jsonify({"error": "product_id is required"}), 400

    extracted = []
    if data.get("links_text"):
        extracted += [line.strip() for line in str(data["links_text"]).splitlines() if line.strip()]
    if isinstance(data.get("links"), list):
        extracted += [str(l).strip() for l in data["links"] if str(l).strip()]
    if not extracted:
        return jsonify({"error": "No valid links or keys provided"}), 400
    if len(extracted) > 5000:
        return jsonify({"error": "Too many links in one upload (max 5000)"}), 400

    db = get_db()
    try:
        product = db.query(Product).filter(Product.id == int(product_id)).first()
        if not product:
            return jsonify({"error": "Product not found"}), 404

        existing = {row[0] for row in db.query(InviteLink.link_or_key).filter(InviteLink.product_id == product.id).all()}
        seen, added, skipped = set(), 0, 0
        for item in extracted:
            if item in existing or item in seen:
                skipped += 1
                continue
            seen.add(item)
            db.add(InviteLink(product_id=product.id, link_or_key=item[:4000], status="available"))
            added += 1
        db.commit()
        logger.info("Bulk upload for %s: %d added, %d duplicates skipped", product.slug, added, skipped)
        return jsonify({
            "success": True,
            "added_count": added,
            "skipped_duplicates": skipped,
            "product_name": product.name,
            "new_available_stock": product.get_available_stock_count(db),
        })
    finally:
        db.close()


@app.route("/api/admin/inventory/recheck", methods=["POST"])
@require_admin
def recheck_inventory():
    """
    Verify freshness of available (checkable) links now — marks used ones as 'used'
    so they stop being handed out. Optional product_id to limit scope.
    """
    from link_checker import is_checkable, check_link_freshness
    data = _payload()
    product_id = data.get("product_id")
    db = get_db()
    try:
        # Re-check available AND previously-used links, so a link wrongly marked used
        # (e.g. a transient page) can be restored if it now verifies as fresh.
        q = db.query(InviteLink).filter(InviteLink.status.in_(["available", "used"]))
        if product_id and str(product_id).isdigit():
            q = q.filter(InviteLink.product_id == int(product_id))
        links = q.order_by(InviteLink.id.asc()).limit(300).all()
        checkable = [lk for lk in links if is_checkable(lk.link_or_key)]
        # The logged-in browser launches Chromium per link and shares an hourly budget with live
        # sales, so bulk rechecks use the cheap HTTP probe; small runs (<= 5 links) may use the browser.
        allow_browser = len(checkable) <= 5
        checked = fresh = used = restored = 0
        for lk in checkable:
            h = check_link_freshness(lk.link_or_key, allow_browser=allow_browser)
            lk.health = h
            lk.health_checked_at = utcnow()
            checked += 1
            if h == "used":
                if lk.status != "used":
                    lk.status = "used"
                used += 1
            elif h == "fresh":
                fresh += 1
                if lk.status == "used":   # false positive earlier -> bring it back
                    lk.status = "available"
                    restored += 1
            db.commit()
        logger.info("Inventory recheck: checked=%d fresh=%d used=%d restored=%d", checked, fresh, used, restored)
        return jsonify({"success": True, "checked": checked, "fresh": fresh, "marked_used": used, "restored": restored})
    finally:
        db.close()


@app.route("/api/admin/inventory/<int:link_id>/restore", methods=["POST"])
@require_admin
def restore_inventory_link(link_id):
    """Manually return a link to available stock (e.g. it was wrongly flagged 'used')."""
    db = get_db()
    try:
        link = db.query(InviteLink).filter(InviteLink.id == link_id).first()
        if not link:
            return jsonify({"error": "Link not found"}), 404
        if link.status == "claimed":
            return jsonify({"error": "Claimed links cannot be restored"}), 409
        link.status = "available"
        link.health = "unchecked"
        link.health_checked_at = None
        db.commit()
        return jsonify({"success": True, "id": link.id, "status": link.status})
    finally:
        db.close()


@app.route("/api/admin/inventory/<int:link_id>", methods=["DELETE"])
@require_admin
def delete_admin_inventory_link(link_id):
    """Delete any link (available / used / claimed). Claimed links can be deleted too —
    the credit-transaction audit log keeps its own record, so history is not fully lost."""
    db = get_db()
    try:
        link = db.query(InviteLink).filter(InviteLink.id == link_id).first()
        if not link:
            return jsonify({"error": "Link not found"}), 404
        was_claimed = link.status == "claimed"
        db.delete(link)
        db.commit()
        if was_claimed:
            logger.info("Deleted CLAIMED link #%s from inventory (admin)", link_id)
        return jsonify({"success": True})
    finally:
        db.close()


# =====================================================================
# Admin: resellers
# =====================================================================

@app.route("/api/admin/resellers", methods=["GET"])
@require_admin
def list_admin_resellers():
    db = get_db()
    try:
        return jsonify([r.to_dict() for r in db.query(Reseller).order_by(Reseller.id.desc()).all()])
    finally:
        db.close()


@app.route("/api/admin/resellers", methods=["POST"])
@require_admin
def create_admin_reseller():
    data = _payload()
    phone = normalize_phone(data.get("phone", ""))
    secret_code = str(data.get("secret_code", "")).strip()
    if not re.fullmatch(r"\d{10}", phone):
        return jsonify({"error": "Phone must be a valid 10-digit number"}), 400
    if not is_valid_secret_code(secret_code):
        return jsonify({"error": "secret_code must be exactly 4 digits"}), 400

    db = get_db()
    try:
        if db.query(Reseller).filter(Reseller.phone == phone).first():
            return jsonify({"error": "A reseller with this phone number already exists"}), 409
        currency = str(data.get("currency") or "INR").upper()
        if currency not in ("INR", "USD"):
            return jsonify({"error": "currency must be INR or USD"}), 400
        try:
            initial = round(float(data.get("wallet_balance", 0) or 0), 2)
        except (TypeError, ValueError):
            return jsonify({"error": "wallet_balance must be a number"}), 400
        if initial < 0 or initial > 100_000_000:
            return jsonify({"error": "wallet_balance out of range"}), 400

        reseller = Reseller(
            name=str(data.get("name") or "New Reseller").strip()[:100],
            phone=phone,
            secret_code=secret_code,
            credits_balance=0,
            wallet_balance=0.0,
            currency=currency,
            is_active=bool(data.get("is_active", True)),
            notes=str(data.get("notes", ""))[:2000],
        )
        db.add(reseller)
        db.commit()
        if initial > 0:
            adjust_reseller_wallet(db, reseller, initial, reason="admin_topup", note="Initial onboarding top-up")
        db.refresh(reseller)
        return jsonify(reseller.to_dict()), 201
    finally:
        db.close()


@app.route("/api/admin/resellers/<int:res_id>", methods=["PUT"])
@require_admin
def update_admin_reseller(res_id):
    data = _payload()
    db = get_db()
    try:
        reseller = db.query(Reseller).filter(Reseller.id == res_id).first()
        if not reseller:
            return jsonify({"error": "Reseller not found"}), 404
        if "name" in data: reseller.name = str(data["name"]).strip()[:100]
        if "phone" in data:
            phone = normalize_phone(data["phone"])
            if not re.fullmatch(r"\d{10}", phone):
                return jsonify({"error": "Phone must be a valid 10-digit number"}), 400
            clash = db.query(Reseller).filter(Reseller.phone == phone, Reseller.id != res_id).first()
            if clash:
                return jsonify({"error": "Another reseller already uses this phone number"}), 409
            reseller.phone = phone
        if "secret_code" in data:
            code = str(data["secret_code"]).strip()
            if not is_valid_secret_code(code):
                return jsonify({"error": "secret_code must be exactly 4 digits"}), 400
            reseller.secret_code = code
            reseller.failed_attempts = 0
            reseller.locked_until = None
        if "is_active" in data: reseller.is_active = bool(data["is_active"])
        if "notes" in data: reseller.notes = str(data["notes"])[:2000]
        if "currency" in data:
            cur = str(data["currency"] or "INR").upper()
            if cur not in ("INR", "USD"):
                return jsonify({"error": "currency must be INR or USD"}), 400
            reseller.currency = cur
        db.commit()
        return jsonify(reseller.to_dict())
    finally:
        db.close()


@app.route("/api/admin/resellers/<int:res_id>/unlock", methods=["POST"])
@require_admin
def unlock_reseller(res_id):
    db = get_db()
    try:
        reseller = db.query(Reseller).filter(Reseller.id == res_id).first()
        if not reseller:
            return jsonify({"error": "Reseller not found"}), 404
        reseller.failed_attempts = 0
        reseller.locked_until = None
        db.commit()
        return jsonify({"success": True, "reseller": reseller.to_dict()})
    finally:
        db.close()


@app.route("/api/admin/resellers/<int:res_id>/wallet", methods=["POST"])
@app.route("/api/admin/resellers/<int:res_id>/credits", methods=["POST"])   # legacy alias
@require_admin
def adjust_reseller_credits(res_id):
    """Top up (+) or deduct (-) money from a reseller's wallet (in the reseller's currency)."""
    data = _payload()
    try:
        amount = round(float(data.get("amount", 0)), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be a number"}), 400
    if amount == 0 or abs(amount) > 10_000_000:
        return jsonify({"error": "amount must be non-zero and within ±10000000"}), 400
    reason = str(data.get("reason") or ("admin_topup" if amount > 0 else "admin_deduct"))[:50]
    note = str(data.get("note") or "Manual admin wallet adjustment")[:500]

    db = get_db()
    try:
        reseller = db.query(Reseller).filter(Reseller.id == res_id).first()
        if not reseller:
            return jsonify({"error": "Reseller not found"}), 404
        result = adjust_reseller_wallet(db, reseller, amount, reason=reason, note=note)
        if not result.get("success"):
            return jsonify({"error": result.get("message")}), 400
        logger.info("Admin adjusted wallet for %s by %+.2f %s (now %s)", reseller.phone, amount, reseller.currency, reseller.money())
        return jsonify({"success": True, "reseller_id": reseller.id, "reseller_name": reseller.name,
                        "change": amount, "new_balance": result["new_balance"], "currency": result["currency"],
                        "balance_display": result["balance_display"], "reseller": reseller.to_dict()})
    finally:
        db.close()


@app.route("/api/admin/resellers/<int:res_id>/transactions", methods=["GET"])
@require_admin
def get_reseller_transactions(res_id):
    db = get_db()
    try:
        txns = db.query(WalletTransaction).filter(WalletTransaction.reseller_id == res_id).order_by(WalletTransaction.id.desc()).limit(500).all()
        return jsonify([t.to_dict() for t in txns])
    finally:
        db.close()


# =====================================================================
# Admin: orders
# =====================================================================

@app.route("/api/admin/orders", methods=["GET"])
@require_admin
def list_admin_orders():
    status_filter = request.args.get("status")
    db = get_db()
    try:
        q = db.query(CustomerOrder)
        if status_filter:
            q = q.filter(CustomerOrder.status == status_filter)
        return jsonify([o.to_dict() for o in q.order_by(CustomerOrder.created_at.desc()).limit(200).all()])
    finally:
        db.close()


@app.route("/api/admin/orders/<order_id>/approve", methods=["POST"])
@require_admin
def approve_customer_order(order_id):
    payment_ref = str(_payload().get("payment_ref") or "ADMIN_APPROVED").strip()[:100]
    db = get_db()
    try:
        order = db.query(CustomerOrder).filter(CustomerOrder.id == order_id.upper()).first()
        if not order:
            return jsonify({"error": "Order not found"}), 404
        result = fulfill_order(order, payment_ref, db, actor="admin")
        if not result.get("success"):
            return jsonify({"error": result.get("message"), "code": result.get("error")}), 400
        return jsonify({"success": True, "order_id": order.id, "status": order.status, "delivered_link": result["link"], "already_delivered": result.get("already_delivered", False)})
    finally:
        db.close()


@app.route("/api/admin/orders/<order_id>/cancel", methods=["POST"])
@require_admin
def cancel_customer_order(order_id):
    db = get_db()
    try:
        order = db.query(CustomerOrder).filter(CustomerOrder.id == order_id.upper()).first()
        if not order:
            return jsonify({"error": "Order not found"}), 404
        if order.status == "delivered":
            return jsonify({"error": "Delivered orders cannot be cancelled"}), 409
        order.status = "cancelled"
        db.commit()
        return jsonify({"success": True, "order_id": order.id, "status": order.status})
    finally:
        db.close()


# =====================================================================
# Admin: settings
# =====================================================================

def _is_masked(value) -> bool:
    return isinstance(value, str) and value.startswith("••••")


@app.route("/api/admin/settings", methods=["GET"])
@require_admin
def get_system_settings_api():
    db = get_db()
    try:
        return jsonify(get_settings(db).to_dict())
    finally:
        db.close()


@app.route("/api/admin/settings", methods=["POST"])
@require_admin
def update_system_settings_api():
    data = _payload()
    db = get_db()
    try:
        s = get_settings(db)
        llm_changed = False
        if "business_name" in data: s.business_name = str(data["business_name"])[:150]
        if "admin_upi_id" in data: s.admin_upi_id = str(data["admin_upi_id"]).strip()[:100]
        if "admin_upi_name" in data: s.admin_upi_name = str(data["admin_upi_name"]).strip()[:100]
        if "admin_contact_number" in data: s.admin_contact_number = str(data["admin_contact_number"]).strip()[:30]
        if "qr_code_image_url" in data: s.qr_code_image_url = data["qr_code_image_url"]
        if "reseller_credit_rate_inr" in data:
            try:
                s.reseller_credit_rate_inr = max(0.0, float(data["reseller_credit_rate_inr"]))
            except (TypeError, ValueError):
                return jsonify({"error": "reseller_credit_rate_inr must be a number"}), 400
        if "reseller_terms" in data: s.reseller_terms = str(data["reseller_terms"])[:4000]
        if "usd_to_inr_rate" in data:
            try:
                rate = float(data["usd_to_inr_rate"])
                if rate <= 0:
                    raise ValueError
                s.usd_to_inr_rate = rate
            except (TypeError, ValueError):
                return jsonify({"error": "usd_to_inr_rate must be a positive number"}), 400
        if "evolution_api_url" in data: s.evolution_api_url = str(data["evolution_api_url"]).strip()[:200]
        if "evolution_instance_name" in data: s.evolution_instance_name = str(data["evolution_instance_name"]).strip()[:100]
        # Secrets: ignore masked echoes; empty string clears; anything else replaces.
        if "evolution_api_key" in data and not _is_masked(data["evolution_api_key"]):
            s.evolution_api_key = str(data["evolution_api_key"]).strip()[:200] or None
        if "openai_api_key" in data and not _is_masked(data["openai_api_key"]):
            s.openai_api_key = str(data["openai_api_key"]).strip()[:200] or None
            llm_changed = True
        if "openai_model_name" in data:
            s.openai_model_name = str(data["openai_model_name"]).strip()[:50] or "gpt-4o-mini"
            llm_changed = True
        if "google_checker_enabled" in data:
            s.google_checker_enabled = bool(data["google_checker_enabled"])
        if "moonshots_enabled" in data:
            s.moonshots_enabled = bool(data["moonshots_enabled"])
        if "moonshots_api_key" in data and not _is_masked(data["moonshots_api_key"]):
            s.moonshots_api_key = str(data["moonshots_api_key"]).strip()[:200] or None
        if "agent_instructions" in data:
            s.agent_instructions = str(data["agent_instructions"])[:8000]
            llm_changed = True  # trained instructions change the prompt -> rebuild agent
        db.commit()
        if llm_changed:
            invalidate_agent_cache()
        return jsonify(s.to_dict())
    finally:
        db.close()


# =====================================================================
# Admin: Google Link Checker (logged-in headless browser for Gemini links)
# =====================================================================

@app.route("/api/admin/google-checker/status", methods=["GET"])
@require_admin
def google_checker_status():
    import google_checker
    return jsonify(google_checker.checker_status())


@app.route("/api/admin/google-checker/session", methods=["POST"])
@require_admin
@rate_limited(10, "gc_session")
def google_checker_upload_session():
    """
    Connect the checker's Google account: accepts the google_session.json produced by
    `python google_checker.py login`, or a cookie export (Cookie-Editor / EditThisCookie),
    as JSON body {"session": <object or array>} or as the raw JSON itself.
    The cookies are stored only on this server; they are never sent anywhere else.
    """
    import google_checker
    data = request.get_json(silent=True)
    if isinstance(data, dict) and "session" in data:
        payload = data["session"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                return jsonify({"error": "session must be valid JSON"}), 400
    else:
        payload = data
    if payload in (None, "", [], {}):
        return jsonify({"error": "No session JSON provided"}), 400
    try:
        info = google_checker.save_session(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:   # browser lock busy
        return jsonify({"error": str(exc)}), 503
    # Verify immediately (opens one.google.com in the headless browser) when possible.
    verification = None
    if google_checker.playwright_installed():
        try:
            verification = google_checker.verify_session().as_dict()
        except Exception as exc:  # noqa: BLE001
            verification = {"status": "error", "reason": str(exc)[:200]}
    return jsonify({"success": True, "saved": info, "verification": verification, "status": google_checker.checker_status()})


@app.route("/api/admin/google-checker/session", methods=["DELETE"])
@require_admin
@rate_limited(10, "gc_session")
def google_checker_disconnect():
    import google_checker
    try:
        google_checker.clear_session()
    except RuntimeError as exc:   # browser lock busy
        return jsonify({"error": str(exc)}), 503
    return jsonify({"success": True, "status": google_checker.checker_status()})


@app.route("/api/admin/google-checker/verify", methods=["POST"])
@require_admin
@rate_limited(10, "gc_verify")
def google_checker_verify():
    import google_checker
    if not google_checker.playwright_installed():
        return jsonify({"error": "playwright is not installed on the server (pip install playwright && playwright install --with-deps chromium)"}), 400
    return jsonify({"result": google_checker.verify_session().as_dict(), "status": google_checker.checker_status()})


@app.route("/api/admin/google-checker/test", methods=["POST"])
@require_admin
@rate_limited(20, "gc_test")
def google_checker_test_link():
    """Check ONE link now (read-only) and show the verdict + evidence — for admin testing.
    Only https links on Google's activation hosts are opened: the server-side browser must never
    be pointed at internal services or arbitrary sites."""
    import google_checker
    url = str(_payload().get("url", "")).strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    if not google_checker.is_allowed_url(url):
        return jsonify({"error": "Sirf Google activation links check ho sakti hain: https://one.google.com/…, "
                                 "https://serviceactivation.google.com/…, https://families.google.com/…"}), 400
    if not google_checker.playwright_installed():
        return jsonify({"error": "playwright is not installed on the server"}), 400
    r = google_checker.check_link(url, force=True, probe=True)
    return jsonify({"result": r.as_dict(), "status": google_checker.checker_status()})


@app.route("/api/admin/google-checker/screenshot", methods=["GET"])
@require_admin
def google_checker_screenshot():
    import google_checker
    if not google_checker.LAST_SHOT.exists():
        return jsonify({"error": "No screenshot yet"}), 404
    return send_file(str(google_checker.LAST_SHOT), mimetype="image/png", max_age=0)


# =====================================================================
# Admin: m00nshots supplier (auto-buy digital products)
# =====================================================================

@app.route("/api/admin/moonshots/status", methods=["GET"])
@require_admin
def moonshots_status():
    import moonshots_service as ms
    return jsonify(ms.status_dict())


@app.route("/api/admin/moonshots/products", methods=["GET"])
@require_admin
@rate_limited(30, "ms_products")
def moonshots_products():
    """Browse the supplier catalogue so the admin can map a local product to a supplier product."""
    import moonshots_service as ms
    search = str(request.args.get("search", "")).strip()
    in_stock = request.args.get("in_stock")
    in_stock_bool = None if in_stock is None else str(in_stock).lower() in ("1", "true", "yes")
    try:
        items = ms.list_products(search=search, in_stock=in_stock_bool)
    except ms.MoonshotsError as exc:
        return jsonify({"error": exc.message, "code": exc.code}), 502
    return jsonify({"success": True, "count": len(items), "data": items})


@app.route("/api/admin/moonshots/products/<int:supplier_pid>", methods=["GET"])
@require_admin
@rate_limited(60, "ms_product")
def moonshots_product_one(supplier_pid):
    """Live name/price/stock of ONE supplier product (used while the admin types a supplier id)."""
    import moonshots_service as ms
    db = get_db()
    try:
        rate = float(get_settings(db).usd_to_inr_rate or 83.0)
    finally:
        db.close()
    fresh = str(request.args.get("fresh", "")).lower() in ("1", "true")
    info = ms.product_summary(supplier_pid, rate, max_age=0 if fresh else ms.PRODUCT_CACHE_SECONDS)
    return jsonify({"success": info.get("error") is None, "data": info, "usd_to_inr_rate": rate})


@app.route("/api/admin/moonshots/mapped", methods=["GET"])
@require_admin
@rate_limited(30, "ms_mapped")
def moonshots_mapped():
    """Live supplier info for every local product mapped to m00nshots, keyed by local product id.
    One call for the whole Products tab; results are cached ~60 s server-side."""
    import moonshots_service as ms
    db = get_db()
    try:
        rate = float(get_settings(db).usd_to_inr_rate or 83.0)
        mapped = (db.query(Product.id, Product.supplier_product_id)
                  .filter(Product.source == "moonshots", Product.supplier_product_id.isnot(None)).all())
    finally:
        db.close()
    fresh = str(request.args.get("fresh", "")).lower() in ("1", "true")
    max_age = 0 if fresh else ms.PRODUCT_CACHE_SECONDS
    items = {}
    if mapped and not ms.api_key():
        for local_id, _sid in mapped:
            items[str(local_id)] = {"error": "Supplier API key not configured (Settings -> m00nshots)", "code": "no_key"}
    else:
        seen: dict = {}
        for local_id, sid in mapped:
            if sid not in seen:                       # several local products may share one supplier id
                seen[sid] = ms.product_summary(sid, rate, max_age=max_age)
            items[str(local_id)] = seen[sid]
    return jsonify({"success": True, "usd_to_inr_rate": rate, "count": len(items), "items": items})


# =====================================================================
# Admin: Bot Tester (live chat with debug info)
# =====================================================================

@app.route("/api/admin/bot/test", methods=["POST"])
@require_admin
def admin_bot_test():
    """
    Run one turn of the real bot and return the reply PLUS debug info:
    engine used, tools called, matched FAQ, elapsed time, and the session state.
    mode="web" (customer/reseller via chat) or "whatsapp" (identity = phone number).
    """
    from database import match_knowledge, get_pending_order_for_session
    data = _payload()
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify({"error": "message required"}), 400
    mode = "whatsapp" if data.get("mode") == "whatsapp" else "web"
    phone = normalize_phone(data.get("phone", "")) if mode == "whatsapp" else ""
    if mode == "whatsapp" and not re.fullmatch(r"\d{10}", phone):
        return jsonify({"error": "WhatsApp mode needs a valid 10-digit phone"}), 400
    session_id = str(data.get("session_id") or "").strip()
    if not session_id or not session_id.startswith("test_"):
        session_id = f"test_{mode}_{phone or 'web'}_{int(time.time() * 1000)}"

    t0 = time.time()
    result = run_deep_agent_chat(
        session_id=session_id,
        user_message=message,
        user_type_hint="customer",
        platform=mode,
        owner_id="admin-tester",
        customer_phone=phone or None,
        customer_name="Bot Tester" if mode == "whatsapp" else None,
    )
    elapsed_ms = int((time.time() - t0) * 1000)

    db = get_db()
    try:
        rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
        session = {}
        if rec:
            reseller = db.query(Reseller).filter(Reseller.id == rec.reseller_id).first() if rec.reseller_id else None
            pending = get_pending_order_for_session(db, session_id)
            session = {
                "session_id": session_id,
                "platform": rec.platform,
                "user_type": rec.user_type,
                "customer_phone": rec.customer_phone,
                "reseller": {"name": reseller.name, "phone": reseller.phone, "balance": reseller.money(), "currency": (reseller.currency or "INR").upper()} if reseller else None,
                "pending_order": {"id": pending.id, "product": pending.product.name if pending.product else None, "amount": pending.total_amount} if pending else None,
                "last_order_id": rec.last_order_id,
            }
        kb = match_knowledge(db, message)
        kb_match = {"id": kb.id, "question": kb.question, "answer": kb.answer} if kb else None
        if kb:
            from agent_core import knowledge_decision
            _d = knowledge_decision(db, message, rec)
            kb_match.update({"decision": _d["decision"], "reason": _d["reason"],
                             "matched_keywords": (_d.get("match") or {}).get("matched", [])})
    finally:
        db.close()

    meta = result.get("metadata") or {}
    return jsonify({
        "success": result.get("success", False),
        "session_id": session_id,
        "reply": result.get("message"),
        "engine": meta.get("engine"),
        "tool_calls": meta.get("tool_calls", []),
        "todos": meta.get("todos", []),
        "elapsed_ms": elapsed_ms,
        "kb_match": kb_match,
        "session": session,
        "agent": agent_status(),
    })


@app.route("/api/admin/bot/test/reset", methods=["POST"])
@require_admin
def admin_bot_test_reset():
    """Delete a tester session so the next message starts fresh."""
    session_id = str(_payload().get("session_id") or "").strip()
    if not session_id.startswith("test_"):
        return jsonify({"error": "only tester sessions (test_*) can be reset here"}), 400
    db = get_db()
    try:
        rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
        if rec:
            db.delete(rec)
            db.commit()
        return jsonify({"success": True})
    finally:
        db.close()


# =====================================================================
# Admin: AI training (Knowledge Base / FAQ)
# =====================================================================

@app.route("/api/admin/knowledge", methods=["GET"])
@require_admin
def list_knowledge():
    db = get_db()
    try:
        rows = db.query(KnowledgeEntry).order_by(KnowledgeEntry.priority.desc(), KnowledgeEntry.id.desc()).all()
        return jsonify([k.to_dict() for k in rows])
    finally:
        db.close()


@app.route("/api/admin/knowledge", methods=["POST"])
@require_admin
def create_knowledge():
    data = _payload()
    question = str(data.get("question", "")).strip()
    answer = str(data.get("answer", "")).strip()
    if not question or not answer:
        return jsonify({"error": "question and answer are required"}), 400
    db = get_db()
    try:
        entry = KnowledgeEntry(
            question=question[:2000],
            answer=answer[:4000],
            keywords=str(data.get("keywords", ""))[:500],
            priority=int(data.get("priority", 0) or 0),
            is_active=bool(data.get("is_active", True)),
        )
        db.add(entry)
        db.commit()
        invalidate_agent_cache()
        return jsonify(entry.to_dict()), 201
    finally:
        db.close()


@app.route("/api/admin/knowledge/<int:entry_id>", methods=["PUT"])
@require_admin
def update_knowledge(entry_id):
    data = _payload()
    db = get_db()
    try:
        entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
        if not entry:
            return jsonify({"error": "Entry not found"}), 404
        if "question" in data: entry.question = str(data["question"]).strip()[:2000]
        if "answer" in data: entry.answer = str(data["answer"]).strip()[:4000]
        if "keywords" in data: entry.keywords = str(data["keywords"])[:500]
        if "priority" in data: entry.priority = int(data["priority"] or 0)
        if "is_active" in data: entry.is_active = bool(data["is_active"])
        db.commit()
        invalidate_agent_cache()
        return jsonify(entry.to_dict())
    finally:
        db.close()


@app.route("/api/admin/knowledge/<int:entry_id>", methods=["DELETE"])
@require_admin
def delete_knowledge(entry_id):
    db = get_db()
    try:
        entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
        if not entry:
            return jsonify({"error": "Entry not found"}), 404
        db.delete(entry)
        db.commit()
        invalidate_agent_cache()
        return jsonify({"success": True})
    finally:
        db.close()


@app.route("/api/admin/knowledge/test", methods=["POST"])
@require_admin
def test_knowledge():
    """Try a question against the trained FAQ: which entry matches, HOW (keywords/score), and
    whether the bot would actually use it for this message (same decision logic as the bot)."""
    from database import render_knowledge_answer, empty_placeholders
    from agent_core import knowledge_decision
    data = _payload()
    q = str(data.get("question", "")).strip()
    if not q:
        return jsonify({"error": "question required"}), 400
    platform = "whatsapp" if data.get("platform") == "whatsapp" else "web"
    db = get_db()
    try:
        fake = ChatSessionRecord(id="kb_test", platform=platform, user_type="customer")   # not persisted
        dec = knowledge_decision(db, q, fake)
        m = dec.get("match")
        st = agent_status()
        return jsonify({
            "matched": bool(m),
            "entry": m["entry"].to_dict() if m else None,
            "score": m["score"] if m else 0,
            "matched_keywords": m["matched"] if m else [],
            "strong": bool(m and m["strong"]),
            "decision": dec["decision"],
            "reason": dec["reason"],
            "rendered_answer": render_knowledge_answer(m["entry"].answer, get_settings(db)) if m else None,
            "empty_placeholders": empty_placeholders(m["entry"].answer, get_settings(db)) if m else [],
            "engine": st["engine"],
            "model": st["model"],
            "llm_configured": st["llm_configured"],
            "circuit_reason": st.get("circuit_reason"),
        })
    finally:
        db.close()


# =====================================================================
# WhatsApp webhook (Evolution API)
# =====================================================================

_recent_message_ids: "OrderedDict[str, float]" = OrderedDict()
_recent_lock = threading.Lock()


def _seen_recently(message_id: str) -> bool:
    """Evolution retries deliveries; make webhook processing idempotent per message id."""
    if not message_id:
        return False
    with _recent_lock:
        if message_id in _recent_message_ids:
            return True
        _recent_message_ids[message_id] = time.time()
        while len(_recent_message_ids) > 2000:
            _recent_message_ids.popitem(last=False)
    return False


def _webhook_authorised() -> bool:
    if not Config.EVOLUTION_WEBHOOK_SECRET:
        return True
    provided = request.args.get("token", "") or request.headers.get("apikey", "") or request.headers.get("X-Webhook-Token", "")
    return bool(provided) and hmac.compare_digest(provided, Config.EVOLUTION_WEBHOOK_SECRET)


def _process_whatsapp_message(parsed: dict) -> None:
    session_id = f"wa_{parsed['phone']}"
    try:
        output = run_deep_agent_chat(
            session_id=session_id,
            user_message=parsed["text"],
            user_type_hint="customer",
            platform="whatsapp",
            owner_id=f"wa:{parsed['phone']}",
            customer_phone=parsed["phone"],
            customer_name=parsed.get("sender_name"),
        )
        reply = output.get("message") or "Thanks for your message! How can I help you today?"
        send_whatsapp_message(remote_jid=parsed["remote_jid"], message_text=reply)
    except Exception:  # noqa: BLE001
        logger.exception("WhatsApp processing failed for %s", session_id)


@app.route("/api/webhook/evolution", methods=["POST"])
@rate_limited(Config.RATE_LIMIT_WEBHOOK_PER_MIN, "webhook")
def evolution_webhook():
    if not _webhook_authorised():
        return jsonify({"error": "Unauthorized webhook"}), 401
    parsed = parse_evolution_webhook_payload(_payload())
    if not parsed:
        return jsonify({"status": "ignored"}), 200
    if _seen_recently(parsed.get("message_id")):
        return jsonify({"status": "duplicate"}), 200
    # Reply asynchronously so Evolution gets its 200 immediately (LLM turns can take seconds).
    _webhook_executor.submit(_process_whatsapp_message, parsed)
    return jsonify({"status": "accepted", "session_id": f"wa_{parsed['phone']}"}), 202


@app.route("/api/webhook/simulate", methods=["POST"])
@require_admin
def simulate_evolution_whatsapp():
    """Synchronous simulator for the admin dashboard (no message is actually sent)."""
    data = _payload()
    phone = normalize_phone(data.get("phone", "9876543210")) or "9876543210"
    message = str(data.get("message") or "Hi, what products are available?")[: Config.MAX_MESSAGE_LENGTH]
    user_name = str(data.get("name") or "WhatsApp Test User")[:100]

    mock_payload = {
        "event": "messages.upsert",
        "instance": "VendingBot",
        "data": {
            "key": {"remoteJid": f"{phone}@s.whatsapp.net", "fromMe": False, "id": f"SIM_{int(time.time() * 1000)}"},
            "pushName": user_name,
            "message": {"conversation": message},
        },
    }
    parsed = parse_evolution_webhook_payload(mock_payload)
    session_id = f"wa_{parsed['phone']}"
    output = run_deep_agent_chat(
        session_id=session_id,
        user_message=parsed["text"],
        user_type_hint="customer",
        platform="whatsapp",
        owner_id=f"wa:{parsed['phone']}",
        customer_phone=parsed["phone"],
        customer_name=user_name,
    )
    return jsonify({
        "status": "success",
        "simulated_whatsapp_sender": f"+91{phone} ({user_name})",
        "incoming_message": message,
        "deep_agent_whatsapp_reply": output.get("message"),
        "todos": output.get("todos", []),
        "engine": (output.get("metadata") or {}).get("engine"),
        "session_id": session_id,
    })


# =====================================================================
# Entrypoint
# =====================================================================

def run_server() -> None:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    logger.info("AI Digital Vending Deep Agent starting on http://%s:%s (%s)", Config.HOST, Config.PORT, Config.APP_ENV)
    if Config.IS_PROD:
        try:
            from waitress import serve
            serve(app, host=Config.HOST, port=Config.PORT, threads=16, url_scheme="http")
            return
        except ImportError:
            logger.warning("waitress not installed; falling back to Flask dev server. Install waitress (or use gunicorn) in production.")
    app.run(host=Config.HOST, port=Config.PORT, debug=False, threaded=True)


if __name__ == "__main__":
    run_server()
