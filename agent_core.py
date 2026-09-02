import os
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from deep_agents import create_deep_agent
from deep_agents.backends import FileSystemBackend, StateBackend
from agent_tools import ALL_AGENT_TOOLS
from database import (
    get_db, 
    get_settings, 
    ChatSessionRecord, 
    ChatMessageRecord,
    Product,
    Reseller,
    CustomerOrder,
    InviteLink,
    normalize_phone,
    verify_reseller_auth,
    process_reseller_claim,
    claim_single_use_link
)

logger = logging.getLogger(__name__)

AGENT_MEMORY_PATH = Path(__file__).parent / "agent.md"

def load_agent_memory() -> str:
    """Load global memory & operational rules from agent.md."""
    if AGENT_MEMORY_PATH.exists():
        return AGENT_MEMORY_PATH.read_text(encoding="utf-8")
    return "You are an AI Autonomous Digital Product Vending and Reseller Management Deep Agent."


def get_llm_model(custom_api_key: Optional[str] = None, model_name: Optional[str] = None):
    """
    Initializes OpenAI LLM instance.
    Uses custom key or ENV key (OPENAI_API_KEY).
    """
    db = get_db()
    try:
        settings = get_settings(db)
        api_key = custom_api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY") or ""
        selected_model = model_name or settings.openai_model_name or "gpt-4o-mini"

        if not api_key or not api_key.startswith("sk-") or len(api_key) < 15:
            return None

        return ChatOpenAI(
            model=selected_model,
            temperature=0.2,
            api_key=api_key
        )
    finally:
        db.close()


def build_deep_agent_instance(custom_api_key: Optional[str] = None):
    """Assembles and returns a configured Deep Agent."""
    llm = get_llm_model(custom_api_key=custom_api_key)
    if not llm:
        return None
    system_memory = load_agent_memory()
    backend = FileSystemBackend(root_dir=str(Path(__file__).parent / "agent_workspace"))

    deep_agent = create_deep_agent(
        model=llm,
        tools=ALL_AGENT_TOOLS,
        system_prompt=system_memory,
        backend=backend
    )
    return deep_agent


def run_deep_agent_chat(
    session_id: str,
    user_message: str,
    user_type_hint: str = "customer",
    custom_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Platform-Independent Deep Agent Execution Engine.
    Used for both Web React Chat UI and Evolution API (WhatsApp) Webhook.
    """
    db = get_db()
    try:
        # 1. Fetch or create chat session
        session_rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
        if not session_rec:
            session_rec = ChatSessionRecord(
                id=session_id,
                user_type=user_type_hint,
                title=user_message[:40] + ("..." if len(user_message) > 40 else "")
            )
            db.add(session_rec)
            db.commit()

        # 2. Fetch past conversation history (last 12 messages for clean context)
        past_msgs_query = db.query(ChatMessageRecord).filter(
            ChatMessageRecord.session_id == session_id
        ).order_by(ChatMessageRecord.id.asc()).limit(12).all()

        formatted_messages = []
        for m in past_msgs_query:
            if m.role == "user":
                formatted_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                formatted_messages.append(AIMessage(content=m.content))

        # Add current user message
        formatted_messages.append(HumanMessage(content=user_message))

        # Save user message to database
        db.add(ChatMessageRecord(
            session_id=session_id,
            role="user",
            content=user_message
        ))
        db.commit()

        # 3. Check for direct rule shortcuts / LLM invocation
        deep_agent = build_deep_agent_instance(custom_api_key=custom_api_key)

        response_text = ""
        todos = []
        files = {}
        metadata = {}

        if deep_agent:
            try:
                agent_result = deep_agent.invoke({
                    "messages": formatted_messages,
                    "session_data": {"session_id": session_id, "user_type": user_type_hint}
                })

                last_msg = agent_result["messages"][-1]
                response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                todos = agent_result.get("todos", [])
                files = agent_result.get("files", {})
            except Exception as llm_err:
                logger.error(f"OpenAI / LLM invocation error: {str(llm_err)}")
                response_text = handle_rule_based_fallback(user_message, user_type_hint, session_id, db)
        else:
            # Direct business logic & database execution
            response_text = handle_rule_based_fallback(user_message, user_type_hint, session_id, db)

        # 4. Save Assistant message to database
        metadata["todos"] = todos
        metadata["files"] = files

        db.add(ChatMessageRecord(
            session_id=session_id,
            role="assistant",
            content=response_text,
            metadata_json=json.dumps(metadata)
        ))
        db.commit()

        return {
            "success": True,
            "session_id": session_id,
            "role": "assistant",
            "message": response_text,
            "todos": todos,
            "files": files,
            "metadata": metadata
        }

    except Exception as e:
        db.rollback()
        logger.exception("Error in run_deep_agent_chat")
        return {
            "success": False,
            "session_id": session_id,
            "role": "assistant",
            "message": f"Server error: {str(e)}",
            "todos": [],
            "files": {}
        }
    finally:
        db.close()


def handle_rule_based_fallback(user_message: str, user_type_hint: str, session_id: str, db) -> str:
    """
    Fallback deterministic handler that fulfills the core customer & reseller logic
    with multi-turn context memory and Hindi/Hinglish natural language recognition.
    """
    import re
    msg = user_message.lower().strip()
    settings = get_settings(db)
    session_rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()

    # 1. Check if user is an already verified reseller in this conversation session
    active_reseller_phone = session_rec.reseller_phone if session_rec else None

    # Check for credentials in current message
    phone_match = re.search(r"\b(\d{10})\b", user_message)
    code_match = re.search(r"\b(\d{4})\b", user_message)

    if phone_match and code_match:
        phone = phone_match.group(1)
        code = code_match.group(1)
        from database import process_reseller_claim, verify_reseller_auth
        is_auth, res_obj, auth_msg = verify_reseller_auth(phone, code, db=db)
        if is_auth and res_obj:
            if session_rec:
                session_rec.reseller_phone = res_obj.phone
                session_rec.user_type = "reseller"
                db.commit()
            active_reseller_phone = res_obj.phone

            # Check if a product is also mentioned in the same turn
            products = db.query(Product).filter(Product.is_active == True).all()
            target_prod = None
            for p in products:
                slug_clean = p.slug.replace("-", " ").lower()
                name_words = [w.lower() for w in p.name.split() if len(w) > 3]
                if p.slug in msg or slug_clean in msg or any(w in msg for w in name_words):
                    target_prod = p
                    break

            if target_prod:
                claim_res = process_reseller_claim(phone, code, target_prod.id, 1, db=db)
                if claim_res.get("success"):
                    link = claim_res["links"][0]
                    return f"🎉 **Verification Successful! Link Claimed & Burned:**\n\n" \
                           f"👤 Reseller: **{claim_res['reseller_name']}**\n" \
                           f"📦 Product: **{claim_res['product_name']}**\n" \
                           f"💳 Credits Deducted: **{claim_res['credits_deducted']}** | Remaining: **{claim_res['remaining_credits']}**\n\n" \
                           f"🔗 **Your Single-Use Invite Link:**\n`{link}`\n\n" \
                           f"⚠️ *Note: This link has been permanently burned from stock and is reserved exclusively for you.*"
                else:
                    return f"❌ **Reseller Operation Failed:** {claim_res.get('message')}"

            return f"✅ **Reseller Verified!**\n\n" \
                   f"👤 Name: **{res_obj.name}**\n" \
                   f"📱 Phone: **{res_obj.phone}**\n" \
                   f"💳 Wallet Balance: **{res_obj.credits_balance} Credit(s)**\n\n" \
                   f"Reply with the product you want to claim (e.g., *'mujhe Gemini ki link de do'* or *'Claim Claude Pro'*)."
        else:
            return f"❌ **Verification Failed:** {auth_msg}\n\n" \
                   f"🌟 **Want to become a Reseller?**\n" \
                   f"1 Credit = ₹{settings.reseller_credit_rate_inr}\n" \
                   f"Pay via UPI: `{settings.admin_upi_id}` and contact Admin to get your 4-digit secret passcode."

    # 2. If already verified in this session and asking for a product link
    if active_reseller_phone:
        from database import Reseller, process_reseller_claim
        reseller = db.query(Reseller).filter(
            (Reseller.phone == active_reseller_phone) | 
            (Reseller.phone == normalize_phone(active_reseller_phone))
        ).first()

        if reseller:
            products = db.query(Product).filter(Product.is_active == True).all()
            target_prod = None
            for p in products:
                slug_clean = p.slug.replace("-", " ").lower()
                name_words = [w.lower() for w in p.name.split() if len(w) > 3]
                if p.slug in msg or slug_clean in msg or any(w in msg for w in name_words):
                    target_prod = p
                    break

            if target_prod:
                claim_res = process_reseller_claim(reseller.phone, reseller.secret_code, target_prod.id, 1, db=db)
                if claim_res.get("success"):
                    link = claim_res["links"][0]
                    return f"🎉 **Link Claimed & Burned for Verified Reseller:**\n\n" \
                           f"👤 Reseller: **{claim_res['reseller_name']}**\n" \
                           f"📦 Product: **{claim_res['product_name']}**\n" \
                           f"💳 Credits Deducted: **{claim_res['credits_deducted']}** | Remaining: **{claim_res['remaining_credits']}**\n\n" \
                           f"🔗 **Your Single-Use Invite Link:**\n`{link}`\n\n" \
                           f"⚠️ *Note: This link has been permanently burned from stock and is reserved exclusively for you.*"
                else:
                    return f"❌ **Reseller Operation Failed:** {claim_res.get('message')}"

    # 3. Product catalog / Rates
    if any(k in msg for k in ["product", "rate", "price", "list", "catalog", "kitne ka", "cost", "kya hai", "batao", "dikhao"]):
        products = db.query(Product).filter(Product.is_active == True).all()
        res = "🛍️ **Available Digital Products & Dynamic Live Rates:**\n\n"
        for p in products:
            stock = p.get_available_stock_count(db)
            stock_badge = f"✅ In Stock ({stock} available)" if stock > 0 else "❌ Out of Stock"
            res += f"• **{p.name}**\n"
            res += f"  - Customer Price: **₹{p.get_customer_price():,.2f}** (Includes dynamic {p.margin_percent}% margin)\n"
            res += f"  - Reseller Cost: **{p.credit_cost} Credit**\n"
            res += f"  - Status: {stock_badge}\n"
            res += f"  - Description: {p.description}\n\n"
        res += "💡 *To buy as a Customer, reply with the product name. To claim as a Reseller, share your registered phone number & 4-digit code.*"
        return res

    # 4. Check for UTR / Payment confirmation for regular customer
    utr_match = re.search(r"\b(\d{12})\b", user_message)
    if utr_match or "utr" in msg or "transaction" in msg or "paid" in msg:
        utr_val = utr_match.group(1) if utr_match else "CUSTOMER_PAYMENT_UTR"
        from database import CustomerOrder, claim_single_use_link
        pending_order = db.query(CustomerOrder).filter(
            CustomerOrder.status == "pending_payment"
        ).order_by(CustomerOrder.created_at.desc()).first()

        if pending_order:
            ok, link_obj, lmsg = claim_single_use_link(
                product_id=pending_order.product_id,
                claimed_by_type="customer",
                claimed_by_id=pending_order.customer_phone or pending_order.id,
                order_id=pending_order.id,
                db=db
            )
            if ok and link_obj:
                pending_order.status = "delivered"
                pending_order.payment_ref = utr_val
                pending_order.delivered_link_id = link_obj.id
                pending_order.delivered_link_content = link_obj.link_or_key
                db.commit()

                return f"🎉 **Payment Confirmed! Order #{pending_order.id} Fulfilled:**\n\n" \
                       f"📦 Product: **{pending_order.product.name}**\n" \
                       f"💳 Payment Ref: `{utr_val}`\n\n" \
                       f"🔗 **Your Single-Use Invite Link:**\n`{link_obj.link_or_key}`\n\n" \
                       f"🔒 *This is a private single-use invite link. Once claimed, it is permanently locked to your account.*"

    # 5. Customer Buy / Product detail Flow
    products = db.query(Product).filter(Product.is_active == True).all()
    for p in products:
        slug_clean = p.slug.replace("-", " ").lower()
        name_words = [w.lower() for w in p.name.split() if len(w) > 3]
        if p.slug in msg or slug_clean in msg or any(w in msg for w in name_words):
            price = p.get_customer_price()
            import random
            from database import CustomerOrder
            order_id = f"ORD-{random.randint(10000, 99999)}"
            new_order = CustomerOrder(
                id=order_id,
                customer_name="Customer",
                product_id=p.id,
                quantity=1,
                unit_price=price,
                total_amount=price,
                payment_method="UPI_QR",
                status="pending_payment"
            )
            db.add(new_order)
            db.commit()

            return f"🛒 **Order Details for {p.name} (Order #{order_id})**\n\n" \
                   f"• Selling Price: **₹{price:,.2f}**\n" \
                   f"• Payment Mode: **UPI / QR Code**\n" \
                   f"• Admin UPI ID: `{settings.admin_upi_id}` ({settings.admin_upi_name})\n\n" \
                   f"📲 **Payment Instructions:**\n" \
                   f"1. Open GPay / PhonePe / Paytm / BHIM\n" \
                   f"2. Pay ₹{price:,.2f} to `{settings.admin_upi_id}`\n" \
                   f"3. Reply with your 12-digit UTR / Payment Transaction ID to instantly receive your private invite link!"

    # 6. Default Greeting
    return f"👋 **Welcome to {settings.business_name}!**\n\n" \
           f"I am your AI Automated Assistant. How can I assist you today?\n\n" \
           f"1. 🛍️ **Regular Customer**: Browse live digital products, dynamic pricing & buy with UPI.\n" \
           f"2. 🔑 **Reseller**: Login with your registered phone number & 4-digit passcode to claim single-use links using your credits.\n\n" \
           f"Please let me know if you are a **Customer** or **Reseller**!"
