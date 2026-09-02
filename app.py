import os
import io
import json
import base64
import logging
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import qrcode
from dotenv import load_dotenv

load_dotenv()

from database import (
    init_db,
    get_db,
    get_settings,
    Product,
    InviteLink,
    Reseller,
    CreditTransaction,
    CustomerOrder,
    SystemSettings,
    ChatSessionRecord,
    ChatMessageRecord,
    claim_single_use_link,
    normalize_phone
)
from agent_core import run_deep_agent_chat
from evolution_service import parse_evolution_webhook_payload, send_whatsapp_message

# Initialize Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Initialize Flask App
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
app = Flask(__name__, static_folder=FRONTEND_DIST, static_url_path="")
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialize Database on boot
with app.app_context():
    init_db()


# =====================================================================
# Frontend & Health Endpoints
# =====================================================================

@app.route("/", methods=["GET"])
def serve_frontend_root():
    if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return send_file(os.path.join(FRONTEND_DIST, "index.html"))
    return jsonify({
        "service": "AI Digital Vending & Reseller Deep Agent Backend",
        "frontend": "Run 'cd frontend && npm run dev' or build with 'npm run build'",
        "status": "online"
    })


@app.route("/<path:path>", methods=["GET"])
def serve_frontend_static(path):
    if path.startswith("api/"):
        return jsonify({"error": "Endpoint not found"}), 404
    file_path = os.path.join(FRONTEND_DIST, path)
    if os.path.exists(file_path):
        return send_file(file_path)
    if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return send_file(os.path.join(FRONTEND_DIST, "index.html"))
    return jsonify({"error": "File not found"}), 404

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "online",
        "service": "AI Digital Vending & Reseller Deep Agent Backend",
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route("/api/qr/upi", methods=["GET"])
def generate_upi_qr():
    """Generates a live QR code image for UPI payments."""
    db = get_db()
    try:
        settings = get_settings(db)
        amount = request.args.get("amount", "")
        order_id = request.args.get("order_id", "ORDER")
        
        upi_id = settings.admin_upi_id or "resellerpay@upi"
        payee_name = settings.admin_upi_name or "Digital Hub"

        upi_payload = f"upi://pay?pa={upi_id}&pn={payee_name}"
        if amount:
            upi_payload += f"&am={amount}&cu=INR"
        if order_id:
            upi_payload += f"&tn={order_id}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(upi_payload)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#10b981", back_color="#0f172a") # sleek emerald on dark
        img_io = io.BytesIO()
        img.save(img_io, "PNG")
        img_io.seek(0)
        
        return send_file(img_io, mimetype="image/png")
    finally:
        db.close()


# =====================================================================
# Chat & Deep Agent Endpoints (ChatGPT-Style UI)
# =====================================================================

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """
    Main Deep Agent Chat interface for web frontend.
    Accepts: { session_id, message, user_type_hint, custom_api_key }
    """
    data = request.get_json() or {}
    session_id = data.get("session_id") or f"session_{int(datetime.utcnow().timestamp())}"
    message = data.get("message", "").strip()
    user_type_hint = data.get("user_type_hint", "customer")
    custom_api_key = data.get("custom_api_key")

    if not message:
        return jsonify({"error": "Message cannot be empty"}), 400

    result = run_deep_agent_chat(
        session_id=session_id,
        user_message=message,
        user_type_hint=user_type_hint,
        custom_api_key=custom_api_key
    )

    return jsonify(result)


@app.route("/api/chat/sessions", methods=["GET"])
def list_chat_sessions():
    """Returns list of recent chat conversations for the ChatGPT sidebar."""
    db = get_db()
    try:
        sessions = db.query(ChatSessionRecord).order_by(ChatSessionRecord.updated_at.desc()).limit(30).all()
        return jsonify([s.to_dict() for s in sessions])
    finally:
        db.close()


@app.route("/api/chat/history/<session_id>", methods=["GET"])
def get_chat_history(session_id):
    """Fetches all messages for a specific session."""
    db = get_db()
    try:
        session_rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
        if not session_rec:
            return jsonify({"session_id": session_id, "messages": []})

        messages = db.query(ChatMessageRecord).filter(
            ChatMessageRecord.session_id == session_id
        ).order_by(ChatMessageRecord.id.asc()).all()

        formatted_msgs = []
        for m in messages:
            item = m.to_dict()
            if m.metadata_json:
                try:
                    item["metadata"] = json.loads(m.metadata_json)
                except Exception:
                    item["metadata"] = {}
            else:
                item["metadata"] = {}
            formatted_msgs.append(item)

        return jsonify({
            "session": session_rec.to_dict(),
            "messages": formatted_msgs
        })
    finally:
        db.close()


@app.route("/api/chat/sessions/new", methods=["POST"])
def create_new_session():
    """Starts a clean chat session."""
    data = request.get_json() or {}
    user_type = data.get("user_type", "customer")
    session_id = f"chat_{int(datetime.utcnow().timestamp())}"

    db = get_db()
    try:
        session_rec = ChatSessionRecord(
            id=session_id,
            user_type=user_type,
            title="New Conversation"
        )
        db.add(session_rec)
        db.commit()
        return jsonify(session_rec.to_dict())
    finally:
        db.close()


@app.route("/api/chat/sessions/<session_id>", methods=["DELETE"])
def delete_chat_session(session_id):
    """Deletes a conversation history."""
    db = get_db()
    try:
        session_rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
        if session_rec:
            db.delete(session_rec)
            db.commit()
        return jsonify({"success": True})
    finally:
        db.close()


# =====================================================================
# Admin Dashboard APIs
# =====================================================================

@app.route("/api/admin/metrics", methods=["GET"])
def get_admin_metrics():
    """Aggregates real-time stats for the Admin Overview tab."""
    db = get_db()
    try:
        total_products = db.query(Product).count()
        available_links = db.query(InviteLink).filter(InviteLink.status == "available").count()
        claimed_links = db.query(InviteLink).filter(InviteLink.status == "claimed").count()
        total_resellers = db.query(Reseller).count()
        
        # Calculate total reseller credits in circulation
        resellers = db.query(Reseller).all()
        total_credits = sum(r.credits_balance for r in resellers)

        # Total revenue estimate from delivered customer orders
        orders = db.query(CustomerOrder).all()
        total_customer_revenue = sum(o.total_amount for o in orders if o.status in ["paid", "delivered"])

        recent_claims = db.query(InviteLink).filter(
            InviteLink.status == "claimed"
        ).order_by(InviteLink.claimed_at.desc()).limit(8).all()

        return jsonify({
            "total_products": total_products,
            "available_links": available_links,
            "claimed_links": claimed_links,
            "total_resellers": total_resellers,
            "total_credits_in_wallets": total_credits,
            "total_customer_revenue": total_customer_revenue,
            "recent_claims": [c.to_dict() for c in recent_claims]
        })
    finally:
        db.close()


# --- Products & Live Dynamic Margin Management ---

@app.route("/api/admin/products", methods=["GET"])
def list_admin_products():
    db = get_db()
    try:
        products = db.query(Product).order_by(Product.id.asc()).all()
        return jsonify([p.to_dict(db) for p in products])
    finally:
        db.close()


@app.route("/api/admin/products", methods=["POST"])
def create_admin_product():
    data = request.get_json() or {}
    db = get_db()
    try:
        slug = data.get("slug") or data.get("name", "").lower().replace(" ", "-")
        product = Product(
            name=data.get("name"),
            slug=slug,
            category=data.get("category", "AI Tools"),
            description=data.get("description", ""),
            base_price=float(data.get("base_price", 0.0)),
            margin_percent=float(data.get("margin_percent", 30.0)),
            credit_cost=int(data.get("credit_cost", 1)),
            is_active=bool(data.get("is_active", True))
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return jsonify(product.to_dict(db)), 201
    finally:
        db.close()


@app.route("/api/admin/products/<int:prod_id>", methods=["PUT"])
def update_admin_product(prod_id):
    data = request.get_json() or {}
    db = get_db()
    try:
        product = db.query(Product).filter(Product.id == prod_id).first()
        if not product:
            return jsonify({"error": "Product not found"}), 404

        if "name" in data: product.name = data["name"]
        if "category" in data: product.category = data["category"]
        if "description" in data: product.description = data["description"]
        if "base_price" in data: product.base_price = float(data["base_price"])
        if "margin_percent" in data: product.margin_percent = float(data["margin_percent"])
        if "credit_cost" in data: product.credit_cost = int(data["credit_cost"])
        if "is_active" in data: product.is_active = bool(data["is_active"])

        db.commit()
        db.refresh(product)
        return jsonify(product.to_dict(db))
    finally:
        db.close()


@app.route("/api/admin/products/<int:prod_id>/margin", methods=["POST"])
def update_product_margin_instant(prod_id):
    """
    CRITICAL REQUIREMENT:
    Instant Margin % update. As soon as admin updates this, the Deep Agent
    immediately computes and replies with the new rate in the next turn.
    """
    data = request.get_json() or {}
    db = get_db()
    try:
        product = db.query(Product).filter(Product.id == prod_id).first()
        if not product:
            return jsonify({"error": "Product not found"}), 404

        new_margin = float(data.get("margin_percent", product.margin_percent))
        product.margin_percent = new_margin
        db.commit()
        db.refresh(product)

        return jsonify({
            "success": True,
            "product_id": product.id,
            "product_name": product.name,
            "base_price": product.base_price,
            "new_margin_percent": product.margin_percent,
            "new_live_customer_price": product.get_customer_price()
        })
    finally:
        db.close()


@app.route("/api/admin/products/<int:prod_id>", methods=["DELETE"])
def delete_admin_product(prod_id):
    db = get_db()
    try:
        product = db.query(Product).filter(Product.id == prod_id).first()
        if not product:
            return jsonify({"error": "Product not found"}), 404
        db.delete(product)
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()


# --- Single-Use Link Inventory Management ---

@app.route("/api/admin/inventory", methods=["GET"])
def list_admin_inventory():
    status_filter = request.args.get("status")
    product_id_filter = request.args.get("product_id")

    db = get_db()
    try:
        query = db.query(InviteLink)
        if status_filter:
            query = query.filter(InviteLink.status == status_filter)
        if product_id_filter:
            query = query.filter(InviteLink.product_id == int(product_id_filter))

        links = query.order_by(InviteLink.id.desc()).limit(150).all()
        return jsonify([lk.to_dict() for lk in links])
    finally:
        db.close()


@app.route("/api/admin/inventory/bulk-upload", methods=["POST"])
def bulk_upload_links():
    """
    Bulk stock upload for Single-Use invite links or keys.
    Takes lines of links and creates available inventory items.
    """
    data = request.get_json() or {}
    product_id = data.get("product_id")
    raw_text = data.get("links_text", "")
    links_array = data.get("links", [])

    if not product_id:
        return jsonify({"error": "Product ID is required"}), 400

    # Parse lines if raw_text is passed
    extracted = []
    if raw_text:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        extracted.extend(lines)
    if links_array:
        extracted.extend([l.strip() for l in links_array if l.strip()])

    if not extracted:
        return jsonify({"error": "No valid links or keys provided"}), 400

    db = get_db()
    try:
        product = db.query(Product).filter(Product.id == int(product_id)).first()
        if not product:
            return jsonify({"error": "Product not found"}), 404

        added_items = []
        for item in extracted:
            link_obj = InviteLink(
                product_id=product.id,
                link_or_key=item,
                status="available"
            )
            db.add(link_obj)
            added_items.append(link_obj)

        db.commit()
        new_total_stock = product.get_available_stock_count(db)

        return jsonify({
            "success": True,
            "added_count": len(added_items),
            "product_name": product.name,
            "new_available_stock": new_total_stock
        })
    finally:
        db.close()


@app.route("/api/admin/inventory/<int:link_id>", methods=["DELETE"])
def delete_admin_inventory_link(link_id):
    db = get_db()
    try:
        link = db.query(InviteLink).filter(InviteLink.id == link_id).first()
        if not link:
            return jsonify({"error": "Link not found"}), 404
        db.delete(link)
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()


# --- Reseller Management ---

@app.route("/api/admin/resellers", methods=["GET"])
def list_admin_resellers():
    db = get_db()
    try:
        resellers = db.query(Reseller).order_by(Reseller.id.desc()).all()
        return jsonify([r.to_dict() for r in resellers])
    finally:
        db.close()


@app.route("/api/admin/resellers", methods=["POST"])
def create_admin_reseller():
    data = request.get_json() or {}
    phone = normalize_phone(data.get("phone", ""))
    secret_code = str(data.get("secret_code", "")).strip()

    if not phone or not secret_code:
        return jsonify({"error": "Phone number and 4-digit secret code are required"}), 400

    db = get_db()
    try:
        existing = db.query(Reseller).filter(Reseller.phone == phone).first()
        if existing:
            return jsonify({"error": "A reseller with this phone number already exists"}), 400

        reseller = Reseller(
            name=data.get("name", "New Reseller"),
            phone=phone,
            secret_code=secret_code,
            credits_balance=int(data.get("credits_balance", 0)),
            is_active=bool(data.get("is_active", True)),
            notes=data.get("notes", "")
        )
        db.add(reseller)
        db.commit()
        db.refresh(reseller)

        # Log initial credit transaction if credits > 0
        if reseller.credits_balance > 0:
            db.add(CreditTransaction(
                reseller_id=reseller.id,
                amount=reseller.credits_balance,
                balance_after=reseller.credits_balance,
                reason="admin_topup",
                reference_note="Initial onboarding credits"
            ))
            db.commit()

        return jsonify(reseller.to_dict()), 201
    finally:
        db.close()


@app.route("/api/admin/resellers/<int:res_id>", methods=["PUT"])
def update_admin_reseller(res_id):
    data = request.get_json() or {}
    db = get_db()
    try:
        reseller = db.query(Reseller).filter(Reseller.id == res_id).first()
        if not reseller:
            return jsonify({"error": "Reseller not found"}), 404

        if "name" in data: reseller.name = data["name"]
        if "phone" in data: reseller.phone = normalize_phone(data["phone"])
        if "secret_code" in data: reseller.secret_code = str(data["secret_code"]).strip()
        if "is_active" in data: reseller.is_active = bool(data["is_active"])
        if "notes" in data: reseller.notes = data["notes"]

        db.commit()
        db.refresh(reseller)
        return jsonify(reseller.to_dict())
    finally:
        db.close()


@app.route("/api/admin/resellers/<int:res_id>/credits", methods=["POST"])
def adjust_reseller_credits(res_id):
    """Admin manually adds or subtracts credits from a reseller's wallet."""
    data = request.get_json() or {}
    amount = int(data.get("amount", 0))
    reason = data.get("reason", "admin_topup")
    note = data.get("note", "Manual admin credit adjustment")

    if amount == 0:
        return jsonify({"error": "Amount cannot be zero"}), 400

    db = get_db()
    try:
        reseller = db.query(Reseller).filter(Reseller.id == res_id).first()
        if not reseller:
            return jsonify({"error": "Reseller not found"}), 404

        reseller.credits_balance += amount
        if reseller.credits_balance < 0:
            reseller.credits_balance = 0

        # Record audit log
        txn = CreditTransaction(
            reseller_id=reseller.id,
            amount=amount,
            balance_after=reseller.credits_balance,
            reason=reason,
            reference_note=note
        )
        db.add(txn)
        db.commit()
        db.refresh(reseller)

        return jsonify({
            "success": True,
            "reseller_id": reseller.id,
            "reseller_name": reseller.name,
            "change": amount,
            "new_balance": reseller.credits_balance
        })
    finally:
        db.close()


@app.route("/api/admin/resellers/<int:res_id>/transactions", methods=["GET"])
def get_reseller_transactions(res_id):
    db = get_db()
    try:
        txns = db.query(CreditTransaction).filter(
            CreditTransaction.reseller_id == res_id
        ).order_by(CreditTransaction.id.desc()).all()
        return jsonify([t.to_dict() for t in txns])
    finally:
        db.close()


# --- Customer Orders & Fulfillment ---

@app.route("/api/admin/orders", methods=["GET"])
def list_admin_orders():
    db = get_db()
    try:
        orders = db.query(CustomerOrder).order_by(CustomerOrder.created_at.desc()).limit(100).all()
        return jsonify([o.to_dict() for o in orders])
    finally:
        db.close()


@app.route("/api/admin/orders/<order_id>/approve", methods=["POST"])
def approve_customer_order(order_id):
    """Admin manually approves payment and fulfills single-use link for an order."""
    data = request.get_json() or {}
    payment_ref = data.get("payment_ref", "ADMIN_APPROVED")

    db = get_db()
    try:
        order = db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            return jsonify({"error": "Order not found"}), 404

        if order.status == "delivered":
            return jsonify({"message": "Order already fulfilled", "link": order.delivered_link_content})

        ok, link_obj, msg = claim_single_use_link(
            product_id=order.product_id,
            claimed_by_type="customer",
            claimed_by_id=order.customer_phone or order.customer_name or order.id,
            order_id=order.id,
            db=db
        )

        if not ok or not link_obj:
            return jsonify({"error": "Out of stock. Cannot fulfill order."}), 400

        order.status = "delivered"
        order.payment_ref = payment_ref
        order.delivered_link_id = link_obj.id
        order.delivered_link_content = link_obj.link_or_key
        db.commit()

        return jsonify({
            "success": True,
            "order_id": order.id,
            "status": "delivered",
            "delivered_link": link_obj.link_or_key
        })
    finally:
        db.close()


# --- System Settings ---

@app.route("/api/admin/settings", methods=["GET"])
def get_system_settings_api():
    db = get_db()
    try:
        settings = get_settings(db)
        return jsonify(settings.to_dict())
    finally:
        db.close()


@app.route("/api/admin/settings", methods=["POST"])
def update_system_settings_api():
    data = request.get_json() or {}
    db = get_db()
    try:
        settings = get_settings(db)
        if "business_name" in data: settings.business_name = data["business_name"]
        if "admin_upi_id" in data: settings.admin_upi_id = data["admin_upi_id"]
        if "admin_upi_name" in data: settings.admin_upi_name = data["admin_upi_name"]
        if "qr_code_image_url" in data: settings.qr_code_image_url = data["qr_code_image_url"]
        if "reseller_credit_rate_inr" in data: settings.reseller_credit_rate_inr = float(data["reseller_credit_rate_inr"])
        if "reseller_terms" in data: settings.reseller_terms = data["reseller_terms"]
        if "evolution_api_url" in data: settings.evolution_api_url = data["evolution_api_url"]
        if "evolution_api_key" in data: settings.evolution_api_key = data["evolution_api_key"]
        if "evolution_instance_name" in data: settings.evolution_instance_name = data["evolution_instance_name"]
        if "openai_api_key" in data and data["openai_api_key"]: settings.openai_api_key = data["openai_api_key"]
        if "openai_model_name" in data: settings.openai_model_name = data["openai_model_name"]

        db.commit()
        db.refresh(settings)
        return jsonify(settings.to_dict())
    finally:
        db.close()


# =====================================================================
# Evolution API (WhatsApp) Webhook & Simulator
# =====================================================================

@app.route("/api/webhook/evolution", methods=["POST"])
def evolution_webhook():
    """
    Live Evolution API Webhook Receiver.
    Extracts WhatsApp message -> runs Deep Agent -> replies on WhatsApp.
    """
    payload = request.get_json() or {}
    parsed = parse_evolution_webhook_payload(payload)
    if not parsed:
        return jsonify({"status": "ignored"}), 200

    phone = parsed["phone"]
    remote_jid = parsed["remote_jid"]
    text = parsed["text"]

    # Session ID mapped to WhatsApp sender phone
    session_id = f"wa_{phone}"

    # Execute Deep Agent
    agent_output = run_deep_agent_chat(
        session_id=session_id,
        user_message=text,
        user_type_hint="customer" # Deep agent dynamically verifies customer vs reseller
    )

    reply_text = agent_output.get("message", "Thank you for reaching out!")

    # Dispatch reply back via Evolution API
    send_whatsapp_message(remote_jid=remote_jid, message_text=reply_text)

    return jsonify({"status": "processed", "session_id": session_id})


@app.route("/api/webhook/simulate", methods=["POST"])
def simulate_evolution_whatsapp():
    """
    Simulator for Evolution API WhatsApp Webhook to test WhatsApp logic directly from the UI.
    """
    data = request.get_json() or {}
    phone = data.get("phone", "9876543210")
    message = data.get("message", "Hi, what products are available?")
    user_name = data.get("name", "WhatsApp Test User")

    mock_payload = {
        "event": "messages.upsert",
        "instance": "VendingBot",
        "data": {
            "key": {
                "remoteJid": f"{phone}@s.whatsapp.net",
                "fromMe": False,
                "id": f"MSG_{int(datetime.utcnow().timestamp())}"
            },
            "pushName": user_name,
            "message": {
                "conversation": message
            }
        }
    }

    parsed = parse_evolution_webhook_payload(mock_payload)
    session_id = f"wa_{parsed['phone']}"

    agent_output = run_deep_agent_chat(
        session_id=session_id,
        user_message=parsed["text"],
        user_type_hint="customer"
    )

    return jsonify({
        "status": "success",
        "simulated_whatsapp_sender": f"+{phone} ({user_name})",
        "incoming_message": message,
        "deep_agent_whatsapp_reply": agent_output.get("message"),
        "todos": agent_output.get("todos", []),
        "session_id": session_id
    })


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    port = int(os.getenv("PORT", 5000))
    print(f"AI Digital Vending & Reseller Deep Agent running on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
