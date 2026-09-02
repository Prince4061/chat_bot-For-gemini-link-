import json
from typing import Dict, Any, Optional
from langchain_core.tools import tool

from database import (
    get_db,
    get_settings,
    Product,
    InviteLink,
    Reseller,
    CustomerOrder,
    verify_reseller_auth,
    claim_single_use_link,
    process_reseller_claim,
    normalize_phone
)

@tool
def get_live_product_catalog(user_role: str = "customer") -> str:
    """
    Fetches the live catalog of digital products with real-time dynamic pricing and stock.
    For regular customers: displays dynamically calculated selling price (Base Price + Admin Margin %).
    For resellers: displays required credit cost per link (1 Credit = 1 Link).
    """
    db = get_db()
    try:
        products = db.query(Product).filter(Product.is_active == True).all()
        if not products:
            return "No digital products are currently available in the catalog."

        output_list = []
        for p in products:
            stock = p.get_available_stock_count(db)
            customer_price = p.get_customer_price()
            
            p_data = {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "customer_selling_price_inr": f"₹{customer_price:,.2f}",
                "reseller_credit_cost": f"{p.credit_cost} Credit",
                "in_stock": stock > 0,
                "available_stock": stock
            }
            output_list.append(p_data)

        return json.dumps({
            "status": "success",
            "user_role": user_role,
            "total_products": len(output_list),
            "catalog": output_list
        }, indent=2)
    finally:
        db.close()


@tool
def get_product_pricing(product_name_or_slug: str, user_role: str = "customer") -> str:
    """
    Fetch specific product dynamic pricing, margin, and live stock count.
    """
    db = get_db()
    try:
        product = db.query(Product).filter(
            (Product.slug.ilike(f"%{product_name_or_slug}%")) | 
            (Product.name.ilike(f"%{product_name_or_slug}%")),
            Product.is_active == True
        ).first()

        if not product:
            return json.dumps({
                "status": "error",
                "message": f"Product '{product_name_or_slug}' not found in active catalog."
            })

        stock = product.get_available_stock_count(db)
        customer_price = product.get_customer_price()

        return json.dumps({
            "status": "success",
            "product_id": product.id,
            "product_name": product.name,
            "category": product.category,
            "description": product.description,
            "customer_selling_price_inr": customer_price,
            "reseller_credit_cost": product.credit_cost,
            "available_stock": stock,
            "in_stock": stock > 0
        }, indent=2)
    finally:
        db.close()


@tool
def verify_reseller_credentials(phone: str, secret_code: str) -> str:
    """
    Verifies a reseller's registered phone number and 4-digit secret passcode.
    Returns reseller account name, wallet credit balance, and verification status.
    """
    db = get_db()
    try:
        is_auth, reseller, msg = verify_reseller_auth(phone, secret_code, db=db)
        if not is_auth:
            return json.dumps({
                "status": "failed",
                "authenticated": False,
                "message": msg,
                "suggestion": "If you are not yet a reseller, check reseller onboarding terms to buy credits."
            })

        return json.dumps({
            "status": "success",
            "authenticated": True,
            "reseller_id": reseller.id,
            "reseller_name": reseller.name,
            "phone": reseller.phone,
            "credits_balance": reseller.credits_balance,
            "message": f"Welcome back {reseller.name}! You have {reseller.credits_balance} available credit(s)."
        }, indent=2)
    finally:
        db.close()


@tool
def check_reseller_credits(phone: str, secret_code: str) -> str:
    """
    Quickly checks the available wallet credits balance for a verified reseller.
    """
    db = get_db()
    try:
        is_auth, reseller, msg = verify_reseller_auth(phone, secret_code, db=db)
        if not is_auth:
            return json.dumps({"status": "failed", "message": msg})

        return json.dumps({
            "status": "success",
            "reseller_name": reseller.name,
            "phone": reseller.phone,
            "credits_balance": reseller.credits_balance,
            "rate_info": "1 Credit = 1 Single-Use Digital Product Invite Link"
        })
    finally:
        db.close()


@tool
def claim_reseller_product_link(
    phone: str, 
    secret_code: str, 
    product_name: str, 
    quantity: int = 1
) -> str:
    """
    AUTOMATED RESELLER LINK DISPENSING & BURNING:
    1. Authenticates reseller phone + 4-digit passcode
    2. Checks required credits vs available balance
    3. Atomically burns / claims single-use invite link(s) from inventory
    4. Deducts wallet credits
    5. Returns single-use invite link(s)
    """
    db = get_db()
    try:
        result = process_reseller_claim(
            phone=phone,
            secret_code=secret_code,
            product_id_or_slug=product_name,
            quantity=quantity,
            db=db
        )
        return json.dumps(result, indent=2)
    finally:
        db.close()


@tool
def create_customer_order(
    product_name: str, 
    customer_name: str = "Customer", 
    customer_phone: str = ""
) -> str:
    """
    Creates a pending customer order with live dynamic pricing and generates UPI / QR payment instructions.
    """
    db = get_db()
    try:
        product = db.query(Product).filter(
            (Product.slug.ilike(f"%{product_name}%")) | 
            (Product.name.ilike(f"%{product_name}%")),
            Product.is_active == True
        ).first()

        if not product:
            return json.dumps({
                "status": "error",
                "message": f"Product '{product_name}' was not found in our catalog."
            })

        stock = product.get_available_stock_count(db)
        if stock < 1:
            return json.dumps({
                "status": "out_of_stock",
                "message": f"Sorry! {product.name} is currently out of stock. Please check back shortly or choose another product."
            })

        selling_price = product.get_customer_price()
        settings = get_settings(db)

        # Generate unique order id
        import random
        order_id = f"ORD-{random.randint(10000, 99999)}"

        order = CustomerOrder(
            id=order_id,
            customer_name=customer_name or "Customer",
            customer_phone=normalize_phone(customer_phone) if customer_phone else None,
            product_id=product.id,
            quantity=1,
            unit_price=selling_price,
            total_amount=selling_price,
            payment_method="UPI_QR",
            status="pending_payment"
        )
        db.add(order)
        db.commit()

        # UPI Payment Link & Instructions
        upi_string = f"upi://pay?pa={settings.admin_upi_id}&pn={settings.admin_upi_name}&am={selling_price}&cu=INR&tn={order_id}"

        return json.dumps({
            "status": "order_created",
            "order_id": order_id,
            "product_name": product.name,
            "amount_payable_inr": f"₹{selling_price:,.2f}",
            "amount_raw": selling_price,
            "admin_upi_id": settings.admin_upi_id,
            "admin_upi_name": settings.admin_upi_name,
            "upi_payment_link": upi_string,
            "payment_instructions": f"Please transfer ₹{selling_price:,.2f} to UPI ID `{settings.admin_upi_id}` using Google Pay, PhonePe, Paytm, or BHIM. After paying, reply with your 12-digit UTR / Payment Transaction ID to instantly receive your private invite link."
        }, indent=2)
    except Exception as e:
        db.rollback()
        return json.dumps({"status": "error", "message": str(e)})
    finally:
        db.close()


@tool
def confirm_customer_payment_and_deliver(order_id: str, payment_ref: str) -> str:
    """
    Confirms the customer's payment reference (UTR / Transaction ID), marks the order as paid,
    and atomically burns and delivers a single-use invite link.
    """
    db = get_db()
    try:
        clean_order_id = str(order_id).strip().upper()
        order = db.query(CustomerOrder).filter(CustomerOrder.id == clean_order_id).first()

        if not order:
            return json.dumps({
                "status": "error",
                "message": f"Order '{clean_order_id}' was not found. Please verify your Order ID."
            })

        if order.status == "delivered" and order.delivered_link_content:
            return json.dumps({
                "status": "already_delivered",
                "message": f"This order #{order.id} has already been fulfilled.",
                "delivered_link": order.delivered_link_content
            })

        # Claim single-use link atomically
        ok, link_obj, msg = claim_single_use_link(
            product_id=order.product_id,
            claimed_by_type="customer",
            claimed_by_id=order.customer_phone or order.customer_name or order.id,
            order_id=order.id,
            db=db
        )

        if not ok or not link_obj:
            return json.dumps({
                "status": "fulfillment_delayed",
                "message": f"Payment recorded (Ref: {payment_ref}), but stock was momentarily exhausted. Our admin has been notified to deliver your link manually immediately."
            })

        # Update order status
        order.payment_ref = str(payment_ref).strip()
        order.status = "delivered"
        order.delivered_link_id = link_obj.id
        order.delivered_link_content = link_obj.link_or_key
        db.commit()

        return json.dumps({
            "status": "success",
            "message": "Payment confirmed! Your private single-use invite link has been generated and unlocked below.",
            "order_id": order.id,
            "product_name": order.product.name if order.product else "Digital Product",
            "single_use_invite_link": link_obj.link_or_key,
            "security_note": "This is a private single-use invite link. Once activated, it cannot be used again."
        }, indent=2)
    except Exception as e:
        db.rollback()
        return json.dumps({"status": "error", "message": str(e)})
    finally:
        db.close()


@tool
def get_reseller_onboarding_info() -> str:
    """
    Provides reseller onboarding terms, bulk credit rates, and admin UPI payment details
    for users who want to purchase credits and become a registered reseller.
    """
    db = get_db()
    try:
        settings = get_settings(db)
        return json.dumps({
            "status": "success",
            "business_name": settings.business_name,
            "credit_rate_per_unit_inr": f"₹{settings.reseller_credit_rate_inr}",
            "credit_packages": [
                {"pack": "Starter Pack", "credits": 10, "price": f"₹{settings.reseller_credit_rate_inr * 10:,.0f}"},
                {"pack": "Growth Pack", "credits": 50, "price": f"₹{settings.reseller_credit_rate_inr * 50 * 0.9:,.0f} (10% Discount)"},
                {"pack": "VIP Wholesaler", "credits": 100, "price": f"₹{settings.reseller_credit_rate_inr * 100 * 0.8:,.0f} (20% Discount)"}
            ],
            "admin_upi_id": settings.admin_upi_id,
            "admin_upi_name": settings.admin_upi_name,
            "terms": settings.reseller_terms,
            "how_to_join": f"1. Pay for your desired credit pack to UPI ID: {settings.admin_upi_id}\n2. Admin will register your phone number and provide your 4-digit secret passcode\n3. Start claiming instant single-use links 24/7!"
        }, indent=2)
    finally:
        db.close()


@tool
def get_payment_qr_info() -> str:
    """
    Fetches the Admin UPI ID and Payment details for custom transfers.
    """
    db = get_db()
    try:
        settings = get_settings(db)
        return json.dumps({
            "admin_upi_id": settings.admin_upi_id,
            "admin_upi_name": settings.admin_upi_name,
            "instructions": "Scan QR Code or pay directly to the UPI ID."
        })
    finally:
        db.close()


ALL_AGENT_TOOLS = [
    get_live_product_catalog,
    get_product_pricing,
    verify_reseller_credentials,
    check_reseller_credits,
    claim_reseller_product_link,
    create_customer_order,
    confirm_customer_payment_and_deliver,
    get_reseller_onboarding_info,
    get_payment_qr_info
]
