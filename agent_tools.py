"""
LangChain tools exposed to the Deep Agent.

Every tool is session-aware through `agent_context`: it can remember a verified
reseller for the rest of the conversation, tie orders to the conversation, and fall
back to the WhatsApp sender's phone number - none of which the LLM has to pass in.
All tools return JSON strings so results are unambiguous for the model.
"""
import json
import re
import logging
from typing import Optional

from langchain_core.tools import tool

from config import Config
from agent_context import get_session_context, record_tool_call
from database import (
    get_db,
    get_settings,
    utcnow,
    Product,
    Reseller,
    CustomerOrder,
    ChatSessionRecord,
    find_product,
    generate_order_id,
    verify_reseller_auth,
    get_reseller_product_credits,
    credits_summary_text,
    process_reseller_claim_for,
    fulfill_order,
    get_pending_order_for_session,
    is_plausible_payment_ref,
    normalize_phone,
)

logger = logging.getLogger(__name__)


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _session_record(db) -> Optional[ChatSessionRecord]:
    ctx = get_session_context()
    if not ctx:
        return None
    return db.query(ChatSessionRecord).filter(ChatSessionRecord.id == ctx.session_id).first()


def _session_reseller(db) -> Optional[Reseller]:
    """Reseller already verified earlier in this conversation (if any, and still active)."""
    rec = _session_record(db)
    if not rec or not rec.reseller_id:
        return None
    reseller = db.query(Reseller).filter(Reseller.id == rec.reseller_id).first()
    if reseller and reseller.is_active and not reseller.is_locked():
        return reseller
    return None


def _remember_reseller(db, reseller: Reseller) -> None:
    rec = _session_record(db)
    if rec:
        rec.reseller_id = reseller.id
        rec.reseller_phone = reseller.phone
        rec.reseller_verified_at = utcnow()
        rec.user_type = "reseller"
        db.commit()


# =====================================================================
# Catalogue & pricing
# =====================================================================

@tool
def get_live_product_catalog(user_role: str = "customer", search: str = "") -> str:
    """
    Fetch the live catalogue with real-time pricing and stock. The catalogue can be very large,
    so at most 25 products are returned: pass `search` (brand or product words, e.g. "notion team",
    "canva") to narrow it down, and use get_product_pricing for one exact product.
    Customers see the selling price (base + admin margin %); resellers see the credit cost per link.
    """
    from sqlalchemy import or_
    from database import stock_counts_by_product
    db = get_db()
    try:
        LIMIT = 25
        base_q = db.query(Product).filter(Product.is_active == True)  # noqa: E712
        total = base_q.count()
        terms = [t for t in re.findall(r"[a-z0-9]+", (search or "").lower()) if len(t) >= 2][:6]
        q = base_q
        if terms:
            # "figma premium" -> products matching ALL words; fall back to ANY word if nothing matches.
            q = base_q
            for t in terms:
                q = q.filter(Product.name.ilike(f"%{t}%"))
            if q.count() == 0:
                q = base_q.filter(or_(*[Product.name.ilike(f"%{t}%") for t in terms]))
        matched = q.count()
        products = q.order_by(Product.id).limit(LIMIT).all()
        stock_map = stock_counts_by_product(db, [p.id for p in products])
        catalog = []
        for p in products:
            stock = stock_map.get(p.id, 0)
            catalog.append({
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "category": p.category,
                "description": p.description,
                "customer_selling_price_inr": p.get_customer_price(),
                "reseller_credit_cost": p.credit_cost,
                "in_stock": stock > 0,
                "available_stock": stock,
            })
        record_tool_call("get_live_product_catalog", True, f"{len(catalog)}/{matched} products")
        note = None
        if matched > len(catalog):
            note = (f"Showing {len(catalog)} of {matched} matching products (catalogue has {total} total). "
                    "Ask the user for a brand/product name and call again with `search`, or use get_product_pricing.")
        return _json({"status": "success", "user_role": user_role, "total_products": total,
                      "matched": matched, "shown": len(catalog), "search": search or None,
                      "note": note, "catalog": catalog})
    finally:
        db.close()


@tool
def get_product_pricing(product_name_or_slug: str, user_role: str = "customer") -> str:
    """Fetch one product's live selling price, reseller credit cost and stock count."""
    db = get_db()
    try:
        product = find_product(db, product_name_or_slug)
        if not product:
            record_tool_call("get_product_pricing", False, "not found")
            return _json({"status": "error", "message": f"Product '{product_name_or_slug}' not found in the active catalogue."})
        stock = product.get_available_stock_count(db)
        record_tool_call("get_product_pricing", True, product.slug)
        return _json({
            "status": "success",
            "product_id": product.id,
            "product_name": product.name,
            "slug": product.slug,
            "category": product.category,
            "description": product.description,
            "customer_selling_price_inr": product.get_customer_price(),
            "reseller_credit_cost": product.credit_cost,
            "available_stock": stock,
            "in_stock": stock > 0,
        })
    finally:
        db.close()


# =====================================================================
# Reseller authentication & claims
# =====================================================================

@tool
def verify_reseller_credentials(phone: str, secret_code: str) -> str:
    """
    Verify a reseller's registered phone number and 4-digit secret passcode.
    On success the reseller stays verified for the rest of this conversation, so you
    must NOT ask for the passcode again.
    """
    db = get_db()
    try:
        is_auth, reseller, msg = verify_reseller_auth(phone, secret_code, db=db)
        if not is_auth:
            record_tool_call("verify_reseller_credentials", False, msg)
            return _json({
                "status": "failed",
                "authenticated": False,
                "message": msg,
                "suggestion": "If they are not a reseller yet, call get_reseller_onboarding_info to explain how to buy credits.",
            })
        _remember_reseller(db, reseller)
        record_tool_call("verify_reseller_credentials", True, reseller.phone)
        return _json({
            "status": "success",
            "authenticated": True,
            "reseller_id": reseller.id,
            "reseller_name": reseller.name,
            "phone": reseller.phone,
            "credits_balance": reseller.credits_balance,
            "credits_by_product": get_reseller_product_credits(db, reseller),
            "credits_summary": credits_summary_text(db, reseller),
            "note": "Credits are PER PRODUCT - the reseller can only claim products they have credits for.",
            "message": f"Welcome back {reseller.name}! Credits: {credits_summary_text(db, reseller)}. Verified for this session.",
        })
    finally:
        db.close()


@tool
def check_reseller_credits(phone: str = "", secret_code: str = "") -> str:
    """
    Check a reseller's wallet balance. If the reseller is already verified in this
    conversation you may call this with no arguments.
    """
    db = get_db()
    try:
        reseller = None
        if phone and secret_code:
            is_auth, reseller, msg = verify_reseller_auth(phone, secret_code, db=db)
            if not is_auth:
                record_tool_call("check_reseller_credits", False, msg)
                return _json({"status": "failed", "message": msg})
            _remember_reseller(db, reseller)
        else:
            reseller = _session_reseller(db)
            if not reseller:
                record_tool_call("check_reseller_credits", False, "not verified")
                return _json({"status": "auth_required", "message": "Ask the reseller for their registered phone number and 4-digit passcode first."})

        record_tool_call("check_reseller_credits", True, reseller.phone)
        return _json({
            "status": "success",
            "reseller_name": reseller.name,
            "phone": reseller.phone,
            "credits_balance": reseller.credits_balance,
            "credits_by_product": get_reseller_product_credits(db, reseller),
            "credits_summary": credits_summary_text(db, reseller),
            "rate_info": "1 Credit = 1 single-use link of THAT product only (credits are per product)",
        })
    finally:
        db.close()


@tool
def claim_reseller_product_link(product_name: str, quantity: int = 1, phone: str = "", secret_code: str = "") -> str:
    """
    Dispense single-use invite link(s) to a reseller: verifies credentials (or reuses the
    verification from earlier in this conversation), checks credits and stock, atomically
    burns the link(s) from inventory and deducts credits.
    Pass phone + secret_code only if the reseller is not yet verified in this session.
    """
    db = get_db()
    try:
        reseller = None
        if phone and secret_code:
            is_auth, reseller, msg = verify_reseller_auth(phone, secret_code, db=db)
            if not is_auth:
                record_tool_call("claim_reseller_product_link", False, msg)
                return _json({"success": False, "error": "AUTH_FAILED", "message": msg})
            _remember_reseller(db, reseller)
        else:
            reseller = _session_reseller(db)
            if not reseller:
                record_tool_call("claim_reseller_product_link", False, "auth required")
                return _json({
                    "success": False,
                    "error": "AUTH_REQUIRED",
                    "message": "Reseller is not verified in this conversation. Ask for the registered phone number and 4-digit passcode.",
                })

        product = find_product(db, product_name)
        if not product:
            record_tool_call("claim_reseller_product_link", False, "product not found")
            return _json({"success": False, "error": "PRODUCT_NOT_FOUND", "message": f"Product '{product_name}' not found. Show the catalogue and ask which one they want."})

        result = process_reseller_claim_for(reseller, product, quantity, db)
        record_tool_call("claim_reseller_product_link", bool(result.get("success")), result.get("error", product.slug))
        if result.get("success"):
            result["delivery_note"] = (
                "Each link is single-use and has been permanently burned from stock. "
                "Present every link clearly, one per line, in a code block."
            )
        return _json(result)
    finally:
        db.close()


@tool
def logout_reseller_session() -> str:
    """Forget the reseller verification for this conversation (use when the reseller asks to log out)."""
    db = get_db()
    try:
        rec = _session_record(db)
        if rec:
            rec.reseller_id = None
            rec.reseller_phone = None
            rec.reseller_verified_at = None
            db.commit()
        record_tool_call("logout_reseller_session", True)
        return _json({"status": "success", "message": "Reseller session cleared."})
    finally:
        db.close()


# =====================================================================
# Customer orders & payment
# =====================================================================

@tool
def create_customer_order(product_name: str, customer_name: str = "", customer_phone: str = "") -> str:
    """
    Create (or reuse) a pending order for a customer at the live price and return UPI
    payment instructions. If this conversation already has an unpaid order for the same
    product, that order is returned instead of creating a duplicate.
    """
    db = get_db()
    ctx = get_session_context()
    try:
        product = find_product(db, product_name)
        if not product:
            record_tool_call("create_customer_order", False, "product not found")
            return _json({"status": "error", "message": f"Product '{product_name}' was not found. Show the catalogue and ask which one they want."})

        stock = product.get_available_stock_count(db)
        if stock < 1:
            record_tool_call("create_customer_order", False, "out of stock")
            return _json({"status": "out_of_stock", "message": f"{product.name} is currently out of stock. Offer another product or ask them to check back later."})

        settings = get_settings(db)
        session_id = ctx.session_id if ctx else None
        phone = normalize_phone(customer_phone) or (ctx.customer_phone if ctx else None)
        name = (customer_name or (ctx.customer_name if ctx else "") or "Customer").strip()

        order = None
        if session_id:
            pending = get_pending_order_for_session(db, session_id)
            if pending and pending.product_id == product.id:
                order = pending  # don't spam duplicate orders for the same intent

        if order is None:
            order = CustomerOrder(
                id=generate_order_id(db),
                session_id=session_id,
                platform=ctx.platform if ctx else "web",
                customer_name=name,
                customer_phone=phone or None,
                product_id=product.id,
                quantity=1,
                unit_price=product.get_customer_price(),
                total_amount=product.get_customer_price(),
                payment_method="UPI_QR",
                status="pending_payment",
            )
            db.add(order)

        rec = _session_record(db)
        if rec:
            rec.last_order_id = order.id
            if phone and not rec.customer_phone:
                rec.customer_phone = phone
            if name and name != "Customer" and not rec.customer_name:
                rec.customer_name = name
        db.commit()

        amount = order.total_amount
        upi_link = f"upi://pay?pa={settings.admin_upi_id}&pn={settings.admin_upi_name}&am={amount}&cu=INR&tn={order.id}"
        record_tool_call("create_customer_order", True, order.id)
        return _json({
            "status": "order_created",
            "order_id": order.id,
            "product_name": product.name,
            "amount_payable_inr": amount,
            "admin_upi_id": settings.admin_upi_id,
            "admin_upi_name": settings.admin_upi_name,
            "upi_payment_link": upi_link,
            "payment_instructions": (
                f"Pay ₹{amount:,.2f} to UPI ID {settings.admin_upi_id} ({settings.admin_upi_name}) using any UPI app "
                f"with note '{order.id}', then reply with the 12-digit UTR / transaction ID to receive the link instantly."
            ),
        })
    except Exception as exc:
        db.rollback()
        logger.exception("create_customer_order failed")
        record_tool_call("create_customer_order", False, str(exc))
        return _json({"status": "error", "message": str(exc)})
    finally:
        db.close()


@tool
def confirm_customer_payment_and_deliver(payment_ref: str, order_id: str = "") -> str:
    """
    Record the customer's payment reference (UTR / transaction ID) and deliver one
    single-use link for the order. If order_id is omitted, the latest unpaid order from
    this conversation is used. Safe to retry: a delivered order returns the same link.
    """
    db = get_db()
    ctx = get_session_context()
    try:
        ref = str(payment_ref or "").strip()
        if not is_plausible_payment_ref(ref):
            record_tool_call("confirm_customer_payment_and_deliver", False, "bad ref")
            return _json({"status": "error", "message": "That does not look like a valid payment reference. Ask for the 12-digit UTR / transaction ID from their UPI app."})

        order = None
        if order_id:
            order = db.query(CustomerOrder).filter(CustomerOrder.id == str(order_id).strip().upper()).first()
            if order and ctx and order.session_id and order.session_id != ctx.session_id:
                order = None  # never let one conversation fulfil another conversation's order
        if order is None and ctx:
            order = get_pending_order_for_session(db, ctx.session_id)
            if order is None:
                rec = _session_record(db)
                if rec and rec.last_order_id:
                    order = db.query(CustomerOrder).filter(CustomerOrder.id == rec.last_order_id).first()
        if order is None:
            record_tool_call("confirm_customer_payment_and_deliver", False, "no order")
            return _json({"status": "error", "message": "No order found for this conversation. Create an order with create_customer_order first."})

        result = fulfill_order(order, ref, db, actor="customer_chat")
        record_tool_call("confirm_customer_payment_and_deliver", bool(result.get("success")), result.get("error", order.id))
        if result.get("success"):
            return _json({
                "status": "already_delivered" if result.get("already_delivered") else "success",
                "order_id": order.id,
                "product_name": result["product_name"],
                "single_use_invite_link": result["link"],
                "message": result["message"],
                "security_note": "Private single-use link - once activated it cannot be used again.",
            })
        return _json({"status": result.get("error", "error").lower(), "order_id": order.id, "message": result.get("message")})
    except Exception as exc:
        db.rollback()
        logger.exception("confirm_customer_payment_and_deliver failed")
        return _json({"status": "error", "message": str(exc)})
    finally:
        db.close()


@tool
def get_order_status(order_id: str = "") -> str:
    """Look up an order's status. With no order_id, returns the latest order from this conversation."""
    db = get_db()
    ctx = get_session_context()
    try:
        order = None
        if order_id:
            order = db.query(CustomerOrder).filter(CustomerOrder.id == str(order_id).strip().upper()).first()
            if order and ctx and order.session_id and order.session_id != ctx.session_id:
                order = None
        elif ctx:
            rec = _session_record(db)
            if rec and rec.last_order_id:
                order = db.query(CustomerOrder).filter(CustomerOrder.id == rec.last_order_id).first()
        if not order:
            return _json({"status": "not_found", "message": "No matching order found for this conversation."})
        data = order.to_dict()
        if order.status != "delivered":
            data.pop("delivered_link_content", None)
        record_tool_call("get_order_status", True, order.id)
        return _json({"status": "success", "order": data})
    finally:
        db.close()


# =====================================================================
# Info tools
# =====================================================================

@tool
def get_reseller_onboarding_info() -> str:
    """Reseller onboarding terms, credit pack prices and how to pay the admin to buy credits."""
    db = get_db()
    try:
        s = get_settings(db)
        rate = s.reseller_credit_rate_inr
        contact = (s.admin_contact_number or "").strip()
        record_tool_call("get_reseller_onboarding_info", True)
        join = (
            f"1. Contact the admin{(' on ' + contact) if contact else ''} to buy a credit pack. "
            f"2. Pay via UPI to {s.admin_upi_id} and share the screenshot. "
            "3. Admin registers your number as a reseller. "
            "4. After that, just message from this same number and your credits/links work automatically."
        )
        return _json({
            "status": "success",
            "business_name": s.business_name,
            "credit_rate_per_unit_inr": rate,
            "credit_packages": [
                {"pack": "Starter Pack", "credits": 10, "price_inr": round(rate * 10)},
                {"pack": "Growth Pack", "credits": 50, "price_inr": round(rate * 50 * 0.9), "note": "10% discount"},
                {"pack": "VIP Wholesaler", "credits": 100, "price_inr": round(rate * 100 * 0.8), "note": "20% discount"},
            ],
            "admin_upi_id": s.admin_upi_id,
            "admin_upi_name": s.admin_upi_name,
            "admin_contact_number": contact,
            "terms": s.reseller_terms,
            "how_to_join": join,
        })
    finally:
        db.close()


@tool
def get_payment_qr_info() -> str:
    """Admin UPI ID and payee name for direct transfers."""
    db = get_db()
    try:
        s = get_settings(db)
        record_tool_call("get_payment_qr_info", True)
        return _json({"admin_upi_id": s.admin_upi_id, "admin_upi_name": s.admin_upi_name, "instructions": "Scan the QR code or pay directly to the UPI ID."})
    finally:
        db.close()


ALL_AGENT_TOOLS = [
    get_live_product_catalog,
    get_product_pricing,
    verify_reseller_credentials,
    check_reseller_credits,
    claim_reseller_product_link,
    logout_reseller_session,
    create_customer_order,
    confirm_customer_payment_and_deliver,
    get_order_status,
    get_reseller_onboarding_info,
    get_payment_qr_info,
]
