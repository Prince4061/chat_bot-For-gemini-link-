"""
Deep Agent execution engine - shared by the web chat API and the WhatsApp webhook.

Responsibilities
* Load / cache the compiled Deep Agent (rebuilt only when the LLM settings change).
* Build the per-turn session context (verified reseller, pending order, platform...).
* Serialise turns per session so two concurrent messages can't race on one conversation.
* Persist history and fall back to the deterministic rule engine when the LLM is
  unavailable - but never re-run business logic if tools already executed.
"""
import json
import re
from sqlalchemy import or_
import logging
import threading
import datetime
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage

from config import Config
from deep_agents import create_deep_agent, DeepAgentError, extract_text
from deep_agents.backends import FileSystemBackend
from agent_tools import ALL_AGENT_TOOLS
from agent_context import SessionContext, set_session_context, reset_session_context, record_tool_call
from database import (
    get_db,
    get_settings,
    utcnow,
    ChatSessionRecord,
    ChatMessageRecord,
    Product,
    Reseller,
    CustomerOrder,
    find_product,
    generate_order_id,
    verify_reseller_auth,
    find_reseller_by_phone,
    get_active_knowledge,
    match_knowledge,
    product_charge_for,
    stock_counts_by_product,
    process_reseller_claim_for,
    fulfill_order,
    get_pending_order_for_session,
    is_plausible_payment_ref,
    normalize_phone,
)

logger = logging.getLogger(__name__)

AGENT_MEMORY_PATH = Path(__file__).parent / "agent.md"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Phrases that mean the model deferred ("let me check / please wait") instead of acting.
# When such a reply comes back with NO tool call, we nudge the agent once to actually proceed.
_STALL_RE = re.compile(
    r"\b(please wait|hold on|one moment|just a moment|give me a moment|let me check|let me look|"
    r"i(?:'| a)?m checking|i will check|i'll check|i will get back|checking (?:the )?(?:catalog|catalogue|stock|price)|"
    r"thodi der|thoda intezaar|intezaar kar|ek minute|ek min|check karta|check kar raha|dekhata hoon|"
    r"dekh kar batata|abhi batata|abhi dekhta|ruk[iao])\b",
    re.IGNORECASE,
)


def _looks_like_stall(text: str) -> bool:
    return bool(text) and bool(_STALL_RE.search(text))

# --- Agent cache -----------------------------------------------------------
_AGENT_CACHE: Dict[str, Any] = {"signature": None, "agent": None, "model": None}
_AGENT_CACHE_LOCK = threading.Lock()

# --- Per-session locks -----------------------------------------------------
_SESSION_LOCKS: Dict[str, threading.Lock] = {}
_SESSION_LOCKS_GUARD = threading.Lock()

# --- Diagnostics for the admin dashboard ----------------------------------
_LAST_LLM_ERROR: Dict[str, Any] = {"at": None, "error": None}

# --- Circuit breaker: after an auth/connectivity failure, skip the LLM for a while
#     instead of paying a failing network round-trip on every message.
_LLM_CIRCUIT: Dict[str, Any] = {"open_until": 0.0, "reason": None}


def _open_circuit(err: Exception) -> None:
    import time
    text = str(err).lower()
    original = getattr(err, "original", err)
    name = type(original).__name__
    if "401" in text or "invalid_api_key" in text or name in ("AuthenticationError", "PermissionDeniedError"):
        seconds, reason = 300, "invalid_api_key"
    elif "429" in text or name == "RateLimitError" or "insufficient_quota" in text:
        seconds, reason = 60, "rate_limited_or_quota"
    elif name in ("APIConnectionError", "APITimeoutError", "ConnectionError", "Timeout"):
        seconds, reason = 30, "connectivity"
    else:
        return
    _LLM_CIRCUIT.update({"open_until": time.time() + seconds, "reason": reason})
    logger.warning("LLM circuit opened for %ss (%s); using rule engine meanwhile", seconds, reason)


def _circuit_open() -> bool:
    import time
    return _LLM_CIRCUIT["open_until"] > time.time()


def _session_lock(session_id: str) -> threading.Lock:
    with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _SESSION_LOCKS[session_id] = lock
            if len(_SESSION_LOCKS) > 5000:  # crude bound; sessions are cheap to re-create
                for key in list(_SESSION_LOCKS)[:1000]:
                    _SESSION_LOCKS.pop(key, None)
        return lock


def load_agent_memory() -> str:
    if AGENT_MEMORY_PATH.exists():
        return AGENT_MEMORY_PATH.read_text(encoding="utf-8")
    return "You are an AI Autonomous Digital Product Vending and Reseller Management Deep Agent."


def build_full_system_prompt(db=None) -> str:
    """agent.md + admin-trained custom instructions + Knowledge Base (FAQ), so the admin
    can shape how the bot replies without touching code."""
    close = db is None
    db = db or get_db()
    try:
        parts = [load_agent_memory()]
        settings = get_settings(db)
        instructions = (settings.agent_instructions or "").strip()
        if instructions:
            parts.append("## Additional Admin Instructions (follow these)\n" + instructions)

        kb = get_active_knowledge(db)
        if kb:
            lines = [
                "## Knowledge Base — admin-trained answers",
                "When the user's question matches one of these, answer using the given answer "
                "(paraphrase naturally, keep facts/prices/links exact). If none match, answer normally.",
            ]
            for e in kb[:80]:
                q = " ".join((e.question or "").split())[:300]
                a = " ".join((e.answer or "").split())[:800]
                lines.append(f"\nQ: {q}\nA: {a}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)
    finally:
        if close:
            db.close()


def resolve_llm_settings(db=None) -> Dict[str, str]:
    """Admin-dashboard settings win over environment variables."""
    close = db is None
    db = db or get_db()
    try:
        s = get_settings(db)
        api_key = (s.openai_api_key or Config.OPENAI_API_KEY or "").strip()
        model = (s.openai_model_name or Config.OPENAI_MODEL_NAME or "gpt-4o-mini").strip()
        return {"api_key": api_key, "model": model}
    finally:
        if close:
            db.close()


def llm_key_looks_valid(api_key: str) -> bool:
    return bool(api_key) and api_key.startswith("sk-") and len(api_key) >= 20


def get_llm_model(api_key: str, model_name: str) -> Optional[ChatOpenAI]:
    if not llm_key_looks_valid(api_key):
        return None
    return ChatOpenAI(
        model=model_name,
        temperature=0.2,
        api_key=api_key,
        timeout=Config.LLM_TIMEOUT_SECONDS,
        max_retries=Config.LLM_MAX_RETRIES,
    )


def invalidate_agent_cache() -> None:
    with _AGENT_CACHE_LOCK:
        _AGENT_CACHE.update({"signature": None, "agent": None, "model": None})
    _LLM_CIRCUIT.update({"open_until": 0.0, "reason": None})  # new settings deserve a fresh try


def get_deep_agent():
    """Return the cached Deep Agent, rebuilding it only when key/model/prompt change."""
    if _circuit_open():
        return None
    llm_cfg = resolve_llm_settings()
    if not llm_key_looks_valid(llm_cfg["api_key"]):
        return None
    prompt = build_full_system_prompt()   # includes admin instructions + trained FAQ
    signature = hashlib.sha256(f"{llm_cfg['api_key']}|{llm_cfg['model']}|{prompt}".encode("utf-8")).hexdigest()

    with _AGENT_CACHE_LOCK:
        if _AGENT_CACHE["signature"] == signature and _AGENT_CACHE["agent"] is not None:
            return _AGENT_CACHE["agent"]
        llm = get_llm_model(llm_cfg["api_key"], llm_cfg["model"])
        if llm is None:
            return None
        backend = FileSystemBackend(root_dir=str(Config.AGENT_WORKSPACE_DIR))
        agent = create_deep_agent(
            model=llm,
            tools=ALL_AGENT_TOOLS,
            system_prompt=prompt,
            backend=backend,
            recursion_limit=Config.AGENT_RECURSION_LIMIT,
            enable_file_tools=False,
        )
        _AGENT_CACHE.update({"signature": signature, "agent": agent, "model": llm_cfg["model"]})
        logger.info("Deep Agent (re)built with model %s", llm_cfg["model"])
        return agent


def agent_status() -> Dict[str, Any]:
    llm_cfg = resolve_llm_settings()
    return {
        "llm_configured": llm_key_looks_valid(llm_cfg["api_key"]),
        "model": llm_cfg["model"],
        "agent_cached": _AGENT_CACHE["agent"] is not None,
        "tools": [t.name for t in ALL_AGENT_TOOLS],
        "recursion_limit": Config.AGENT_RECURSION_LIMIT,
        "history_window": Config.CHAT_HISTORY_WINDOW,
        "last_llm_error": _LAST_LLM_ERROR,
        "circuit_open": _circuit_open(),
        "circuit_reason": _LLM_CIRCUIT["reason"] if _circuit_open() else None,
        "engine": "deep_agent" if (llm_key_looks_valid(llm_cfg["api_key"]) and not _circuit_open()) else "rule_based_fallback",
    }


def test_llm_connection() -> Dict[str, Any]:
    """Cheap round-trip used by the admin settings page."""
    llm_cfg = resolve_llm_settings()
    llm = get_llm_model(llm_cfg["api_key"], llm_cfg["model"])
    if llm is None:
        return {"ok": False, "error": "No valid OpenAI API key configured."}
    try:
        reply = llm.invoke([HumanMessage(content="Reply with the single word: pong")])
        return {"ok": True, "model": llm_cfg["model"], "reply": extract_text(reply)[:50]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": llm_cfg["model"], "error": str(exc)[:300]}


# =====================================================================
# Session context
# =====================================================================

def build_session_context_text(db, session_rec: ChatSessionRecord) -> str:
    settings = get_settings(db)
    now_ist = datetime.datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    lines = [
        f"- Business: {settings.business_name} | Admin UPI: {settings.admin_upi_id} ({settings.admin_upi_name})",
        f"- Channel: {'WhatsApp (keep replies short, plain text, no markdown tables)' if session_rec.platform == 'whatsapp' else 'Web chat (markdown allowed)'}",
        f"- Current time: {now_ist}",
        f"- User type hint from UI: {session_rec.user_type}",
    ]
    if session_rec.customer_name or session_rec.customer_phone:
        lines.append(f"- Known customer: {session_rec.customer_name or 'Customer'} {session_rec.customer_phone or ''}".rstrip())

    is_whatsapp = session_rec.platform == "whatsapp"
    contact = (settings.admin_contact_number or "").strip()

    reseller = None
    if session_rec.reseller_id:
        reseller = db.query(Reseller).filter(Reseller.id == session_rec.reseller_id).first()
    if reseller and reseller.is_active and not reseller.is_locked():
        how = "auto-verified by their WhatsApp number" if is_whatsapp else "verified in this conversation"
        summary = reseller.money()
        lines.append(
            f"- RESELLER VERIFIED ({how}): {reseller.name} (phone {reseller.phone}). "
            f"They have a MONEY wallet with balance {summary} ({(reseller.currency or 'INR').upper()}). "
            "Each link deducts that product's reseller price from the wallet; they can buy any product "
            "whose price fits the balance. Do NOT ask for phone or passcode; call "
            "claim_reseller_product_link(product_name, quantity) or check_reseller_balance() directly."
        )
        lines.append(
            f"- AUTHORITATIVE BALANCE: {summary} is the ONLY correct, current balance. IGNORE any "
            "credits/balance numbers that appear in earlier messages of this conversation — the old "
            "credit system was replaced by this money wallet. Never say 'credits'; say the money amount."
        )
        if is_whatsapp:
            lines.append(
                "- On WhatsApp, when this reseller greets or sends a general message, reply IMMEDIATELY like "
                f"'Hello <first name> sir! Aapke paas {summary} balance hai. Kya aapko koi link chahiye?' "
                "— do NOT wait for them to ask for their balance."
            )
    elif is_whatsapp:
        # On WhatsApp the sender's number is known and is NOT a registered reseller.
        contact_line = (f"Tell them to contact {contact} to pay and get reseller access."
                        if contact else "Tell them to contact the admin to pay and get reseller access.")
        lines.append(
            "- This WhatsApp number is NOT a registered reseller, so treat them as a CUSTOMER. On a greeting "
            "or general message, reply like: 'Namaste! Aapko kaunsa product chahiye?' and show the live "
            "catalogue (call get_live_product_catalog). NEVER ask 'customer ya reseller' on WhatsApp. "
            "Do NOT greet them by any reseller name, show any credit balance, or claim any link for them. "
            "Never ask them for a phone number (you already have it) or a passcode. They buy via UPI. "
            f"If they ask for reseller credits/links: {contact_line}"
        )
    else:
        lines.append("- Reseller: NOT verified. On web, links are claimed only after phone + 4-digit passcode verification.")

    pending = get_pending_order_for_session(db, session_rec.id)
    if pending:
        lines.append(
            f"- PENDING ORDER awaiting payment: {pending.id} for {pending.product.name if pending.product else 'product'} "
            f"at ₹{pending.total_amount:,.2f}. If the user sends a UTR / transaction ID, call "
            "confirm_customer_payment_and_deliver(payment_ref) immediately."
        )
    elif session_rec.last_order_id:
        last = db.query(CustomerOrder).filter(CustomerOrder.id == session_rec.last_order_id).first()
        if last:
            lines.append(f"- Last order {last.id}: status {last.status}. Use get_order_status() if they ask about it.")
    else:
        lines.append("- No order created yet in this conversation.")
    return "\n".join(lines)


# =====================================================================
# Main entry point
# =====================================================================

def run_deep_agent_chat(
    session_id: str,
    user_message: str,
    user_type_hint: str = "customer",
    platform: str = "web",
    owner_id: Optional[str] = None,
    customer_phone: Optional[str] = None,
    customer_name: Optional[str] = None,
) -> Dict[str, Any]:
    user_message = (user_message or "").strip()[: Config.MAX_MESSAGE_LENGTH]
    if not user_message:
        return {"success": False, "session_id": session_id, "role": "assistant", "message": "Empty message.", "todos": [], "files": {}}

    with _session_lock(session_id):
        db = get_db()
        try:
            # 1. Session bookkeeping
            session_rec = db.query(ChatSessionRecord).filter(ChatSessionRecord.id == session_id).first()
            if not session_rec:
                session_rec = ChatSessionRecord(
                    id=session_id,
                    owner_id=owner_id,
                    platform=platform,
                    user_type=user_type_hint,
                    customer_phone=normalize_phone(customer_phone) or None,
                    customer_name=customer_name,
                    title=user_message[:40] + ("..." if len(user_message) > 40 else ""),
                )
                db.add(session_rec)
            else:
                if session_rec.title in (None, "", "New Conversation"):
                    session_rec.title = user_message[:40] + ("..." if len(user_message) > 40 else "")
                if customer_phone and not session_rec.customer_phone:
                    session_rec.customer_phone = normalize_phone(customer_phone)
                if customer_name and not session_rec.customer_name:
                    session_rec.customer_name = customer_name
                if user_type_hint and session_rec.user_type != "reseller":
                    session_rec.user_type = user_type_hint
            # 1b. WhatsApp identity = sender's number. Re-derive EVERY turn so it always
            #     reflects the current DB: verify a registered reseller, and CLEAR any stale
            #     reseller link if this number is not (or no longer) a registered reseller.
            #     (Fixes old sessions that got linked to a reseller by a typed phone+code.)
            if platform == "whatsapp":
                reseller = find_reseller_by_phone(db, session_rec.customer_phone) if session_rec.customer_phone else None
                if reseller and reseller.is_active and not reseller.is_locked():
                    if session_rec.reseller_id != reseller.id:
                        session_rec.reseller_id = reseller.id
                        session_rec.reseller_phone = reseller.phone
                        session_rec.reseller_verified_at = utcnow()
                        session_rec.user_type = "reseller"
                        logger.info("WhatsApp auto-verified reseller %s by number", reseller.phone)
                elif session_rec.reseller_id:
                    # Stale link from an earlier typed phone+code, or reseller removed → clear it.
                    logger.info("Clearing stale reseller link on WhatsApp session %s (number %s not a reseller)",
                                session_id, session_rec.customer_phone)
                    session_rec.reseller_id = None
                    session_rec.reseller_phone = None
                    session_rec.reseller_verified_at = None
                    session_rec.user_type = "customer"

            session_rec.updated_at = utcnow()
            db.add(ChatMessageRecord(session_id=session_id, role="user", content=user_message))
            db.commit()

            # 2. Conversation window (most recent N, chronological order)
            recent = (
                db.query(ChatMessageRecord)
                .filter(ChatMessageRecord.session_id == session_id)
                .order_by(ChatMessageRecord.id.desc())
                .limit(Config.CHAT_HISTORY_WINDOW)
                .all()
            )
            history: List[Any] = []
            for m in reversed(recent):
                if m.role == "user":
                    history.append(HumanMessage(content=m.content))
                elif m.role == "assistant" and m.content:
                    history.append(AIMessage(content=m.content))
            # The current user message is already the last item of `recent`.

            # 3. Run the Deep Agent (or the rule engine)
            ctx = SessionContext(
                session_id=session_id,
                platform=platform,
                owner_id=owner_id,
                customer_phone=session_rec.customer_phone,
                customer_name=session_rec.customer_name,
                user_type_hint=session_rec.user_type,
            )
            token = set_session_context(ctx)
            response_text, todos, engine = "", [], "rule_based"
            try:
                # Deterministic fast-path: a verified reseller's greeting / balance question is a DB
                # FACT. Skip the LLM for it (agent=None -> rule engine answers from the live wallet),
                # so an old "credits: 5" in chat history can never be repeated as the balance.
                fact_reply = None
                if session_rec.reseller_id:
                    _r = db.query(Reseller).filter(Reseller.id == session_rec.reseller_id).first()
                    if _r and _r.is_active and not _r.is_locked():
                        fact_reply = _verified_reseller_fact_reply(db, _r, user_message)
                agent = None if fact_reply else get_deep_agent()
                if agent is not None:
                    engine = "deep_agent"
                    context_text = build_session_context_text(db, session_rec)
                    try:
                        result = agent.invoke({
                            "messages": history,
                            "session_data": {"session_id": session_id, "context_text": context_text},
                        })
                        response_text = extract_text(result["messages"][-1]) if result.get("messages") else ""
                        todos = result.get("todos", []) or []

                        # Anti-stall: the model sometimes says "let me check / please wait" and ends the
                        # turn without calling a tool. Detect that and nudge it once to actually act.
                        if not ctx.tool_calls and _looks_like_stall(response_text):
                            logger.info("Agent stalled without calling tools; nudging to proceed.")
                            nudge_history = list(result.get("messages", history))
                            nudge_history.append(HumanMessage(content=(
                                "Please proceed now: call the necessary tools and give me the complete answer "
                                "in this reply. Do not ask me to wait."
                            )))
                            retry = agent.invoke({
                                "messages": nudge_history,
                                "session_data": {"session_id": session_id, "context_text": context_text},
                            })
                            retry_text = extract_text(retry["messages"][-1]) if retry.get("messages") else ""
                            if retry_text and not _looks_like_stall(retry_text):
                                response_text = retry_text
                                todos = retry.get("todos", []) or todos

                        if not response_text:
                            response_text = _summarise_tool_outcome(result.get("messages", [])) or \
                                "Done. Let me know if you need anything else."
                    except DeepAgentError as err:
                        _LAST_LLM_ERROR.update({"at": utcnow().isoformat(), "error": str(err)[:300]})
                        logger.error("Deep Agent failed: %s (tools executed: %s)", err, err.tools_executed)
                        _open_circuit(err)
                        if err.tools_executed:
                            # Business actions already happened - report them, never re-run the rule engine.
                            engine = "deep_agent_partial"
                            response_text = _summarise_tool_outcome(err.partial_state.get("messages", [])) or (
                                "Your request was processed but I hit a temporary AI error while writing the reply. "
                                "Please ask me for the status and I'll confirm the details."
                            )
                        else:
                            engine = "rule_based_fallback"
                            response_text = handle_rule_based_fallback(user_message, session_rec, db)
                else:
                    response_text = handle_rule_based_fallback(user_message, session_rec, db)
            finally:
                reset_session_context(token)

            # 4. Persist the assistant turn
            metadata = {"todos": todos, "engine": engine, "tool_calls": ctx.tool_calls}
            db.add(ChatMessageRecord(session_id=session_id, role="assistant", content=response_text, metadata_json=json.dumps(metadata, ensure_ascii=False)))
            session_rec.updated_at = utcnow()
            db.commit()

            return {
                "success": True,
                "session_id": session_id,
                "role": "assistant",
                "message": response_text,
                "todos": todos,
                "files": {},
                "metadata": metadata,
            }
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("run_deep_agent_chat crashed")
            return {
                "success": False,
                "session_id": session_id,
                "role": "assistant",
                "message": "Sorry, something went wrong on our side. Please try again in a moment.",
                "error": str(exc) if not Config.IS_PROD else None,
                "todos": [],
                "files": {},
            }
        finally:
            db.close()


def _summarise_tool_outcome(messages: List[Any]) -> str:
    """Best-effort human summary from the last tool result when the model produced no text."""
    from langchain_core.messages import ToolMessage
    for m in reversed(messages):
        if isinstance(m, ToolMessage):
            try:
                data = json.loads(m.content)
            except Exception:  # noqa: BLE001
                return str(m.content)[:800]
            if isinstance(data, dict):
                bits = []
                if data.get("message"):
                    bits.append(str(data["message"]))
                links = data.get("links") or ([data["single_use_invite_link"]] if data.get("single_use_invite_link") else [])
                if links:
                    bits.append("Your single-use link(s):\n" + "\n".join(f"`{l}`" for l in links))
                if data.get("payment_instructions"):
                    bits.append(str(data["payment_instructions"]))
                return "\n\n".join(bits)
    return ""


# =====================================================================
# Deterministic fallback (no LLM key / LLM outage)
# =====================================================================

_CATALOG_KEYWORDS = ("product", "rate", "price", "list", "catalog", "catalogue", "kitne", "cost", "kya hai", "batao", "dikhao", "menu", "available")


def _record_skipped_check(res: Dict[str, Any]) -> None:
    try:
        from link_checker import is_checkable
        delivered = list((res or {}).get("links") or ([] if not (res or {}).get("link") else [res["link"]]))
        if not any(is_checkable(l) for l in delivered):
            return
        import google_checker
        reason = google_checker.not_ready_reason() or "browser gave no verdict"
        record_tool_call("link_check", False, f"skipped: {reason}")
        logger.warning("Google link delivered WITHOUT live verification: %s", reason)
    except Exception:  # noqa: BLE001
        pass


def _verification_line(res: Dict[str, Any]) -> str:
    """Tell the buyer whether the delivered link was live-verified by the logged-in Google checker.
    Also records a `link_check` tool-call so the admin Bot Tester shows it."""
    v = (res or {}).get("link_verification") or {}
    if v.get("method") != "browser" or not v.get("checked"):
        # Nothing was live-checked. Say nothing to the buyer, but if a Google link went out
        # unverified, tell the admin why (Bot Tester `link_check` chip / logs).
        _record_skipped_check(res)
        return ""
    many = len(v.get("links_health") or []) > 1
    if v.get("verified_fresh"):
        record_tool_call("link_check", True, f"fresh (Google live check); skipped used={v.get('skipped_used', 0)}")
        return ("\n\n✅ *Ye sabhi links Google par live verify ki gayi hain — fresh hain.*" if many
                else "\n\n✅ *Ye link Google par live verify ki gayi hai — fresh hai.*")
    record_tool_call("link_check", False, f"not verified: {v.get('links_health')}")
    return "\n\nℹ️ *Link is baar Google par live verify nahi ho paayi. Agar kaam na kare to reply karo: 'link used'.*"


def _fmt_links(links: List[str]) -> str:
    return "\n".join(f"`{l}`" for l in links)


_GREETING_RE = re.compile(r"\W*(hi+|hello+|hey+|hii+|namaste|namaskar|start|menu|help|yo|ok|hlo)\W*")


def _verified_reseller_fact_reply(db, reseller: Reseller, user_message: str) -> Optional[str]:
    """
    Deterministic reply for a verified reseller's greeting / balance question, built straight
    from the wallet in the DB. Used BEFORE the LLM so the balance can never be hallucinated or
    parroted from old chat history (e.g. a stale "credits: 5" from the pre-wallet era).
    Returns None when the message is about something else (e.g. names a product).
    """
    msg = (user_message or "").lower().strip()
    asks_balance = any(k in msg for k in ("balance", "credit", "wallet", "paise", "paisa", "kitna paisa", "kitne paise"))
    is_greeting = bool(_GREETING_RE.fullmatch(msg)) or len(msg) <= 2
    if not (asks_balance or is_greeting):
        return None
    if find_product(db, user_message):
        return None
    db.refresh(reseller)  # always the live wallet value
    first_name = reseller.name.split(" (")[0].split()[0] if reseller.name else "Reseller"
    return (
        f"👋 Hello **{first_name}** sir! Aapke paas **{reseller.money()}** balance hai.\n\n"
        "Kya aapko koi link chahiye? Bas product ka naam bhejo (jaise *'Gemini ki link do'*).\n\n"
        f"Link prices (aapke liye):\n{_reseller_prices_lines(db, reseller)}"
    )


def _reseller_prices_lines(db, reseller: Reseller, limit: int = 8) -> str:
    """'• Gemini Advanced — ₹450' lines in the reseller's currency (what a link costs them)."""
    prods = db.query(Product).filter(Product.is_active == True).order_by(Product.id).limit(limit).all()  # noqa: E712
    return "\n".join(f"• {p.name.split(' (')[0]} — {reseller.money(product_charge_for(db, reseller, p))}" for p in prods)


def _reseller_claim_reply(res: Dict[str, Any]) -> str:
    if not res.get("success"):
        return f"❌ **Reseller operation failed:** {res.get('message')}"
    return (
        "🎉 **Link Claimed & Burned:**\n\n"
        f"👤 Reseller: **{res['reseller_name']}**\n"
        f"📦 Product: **{res['product_name']}** × {res['quantity']}\n"
        f"💳 Deducted: **{res['charged_display']}** | Wallet balance left: **{res['balance_display']}**\n\n"
        f"🔗 **Your Single-Use Invite Link(s):**\n{_fmt_links(res['links'])}\n\n"
        "⚠️ *Each link is permanently burned from stock and reserved for you alone.*"
        + _verification_line(res)
    )


def handle_rule_based_fallback(user_message: str, session_rec: ChatSessionRecord, db) -> str:
    """
    Keyword/regex engine covering the core flows in Hindi, English and Hinglish.
    Uses the same atomic database operations as the LLM tools.
    """
    msg = user_message.lower().strip()
    settings = get_settings(db)
    session_id = session_rec.id
    is_whatsapp = session_rec.platform == "whatsapp"
    contact = (settings.admin_contact_number or "").strip()

    # Quantity: "2 links", "2 gemini links do", "gemini 3 link" — a standalone 1-2 digit number
    # anywhere in the message when a unit word is present (365 in "office 365" is 3 digits -> ignored).
    quantity = 1
    if re.search(r"\b(links?|credits?|pcs|pieces|qty|keys?)\b", msg):
        # Number must be a standalone word: "2 links" yes; "9fa56274", "gpt-4o", "x2" no.
        qty_match = re.search(r"(?<![\w.])(\d{1,2})(?![\w.])", msg)
        if qty_match and 1 <= int(qty_match.group(1)) <= Config.MAX_CLAIM_QUANTITY:
            quantity = int(qty_match.group(1))

    reseller_intent = any(k in msg for k in ("reseller", "credit", "wallet", "balance", "link do", "link chahiye", "claim"))

    # WhatsApp: sender number is known. If it is NOT a registered reseller and they ask
    # about reseller/credits, guide them to the admin contact instead of asking for a code.
    if is_whatsapp and not session_rec.reseller_id and reseller_intent and not find_product(db, user_message):
        c = f" Contact *{contact}* to pay and get reseller access." if contact else " Please contact the admin to pay and get reseller access."
        return (
            "ℹ️ Aapka ye number reseller ke roop me registered nahi hai.\n\n"
            f"Reseller ke paas ek wallet hota hai (min top-up ₹{settings.reseller_credit_rate_inr:,.0f}); har link ka reseller price wallet se katta hai."
            f"{c}\n\n"
            "Ya aap normal customer ki tarah bhi kharid sakte ho — bas product ka naam bhejo aur UPI se pay karo."
        )

    # 1. (Web only) Credentials in this message -> verify (and claim if a product is named).
    phone_match = re.search(r"(?<!\d)(\d{10})(?!\d)", user_message) if not is_whatsapp else None
    code_match = re.search(r"(?<!\d)(\d{4})(?!\d)", user_message) if not is_whatsapp else None
    if phone_match and code_match:
        is_auth, reseller, auth_msg = verify_reseller_auth(phone_match.group(1), code_match.group(1), db=db)
        if not is_auth:
            return (
                f"❌ **Verification failed:** {auth_msg}\n\n"
                "🌟 **Want to become a reseller?**\n"
                f"Wallet me paise daal kar links lo (min top-up ₹{settings.reseller_credit_rate_inr:,.0f}). Pay via UPI `{settings.admin_upi_id}` and contact the admin for your 4-digit passcode."
            )
        session_rec.reseller_id = reseller.id
        session_rec.reseller_phone = reseller.phone
        session_rec.reseller_verified_at = utcnow()
        session_rec.user_type = "reseller"
        db.commit()
        product = find_product(db, user_message)
        if product:
            return _reseller_claim_reply(process_reseller_claim_for(reseller, product, quantity, db))
        return (
            "✅ **Reseller verified!**\n\n"
            f"👤 Name: **{reseller.name}**\n📱 Phone: **{reseller.phone}**\n"
            f"💰 Wallet balance: **{reseller.money()}**\n\n"
            f"Aapke liye link prices:\n{_reseller_prices_lines(db, reseller)}\n\n"
            "Reply with the product you want (e.g. *'Gemini ki link do'*) — price wallet se kat jayega."
        )

    # 2. Already-verified reseller (web-verified or WhatsApp auto-verified by number)
    if session_rec.reseller_id:
        reseller = db.query(Reseller).filter(Reseller.id == session_rec.reseller_id).first()
        if reseller and reseller.is_active:
            product = find_product(db, user_message)
            # Registered reseller says "hi" (or asks balance) -> name + LIVE wallet balance from the
            # DB right away, no need to ask. (Same helper the LLM fast-path uses.)
            fact = _verified_reseller_fact_reply(db, reseller, user_message)
            if fact:
                return fact
            if product and not any(k in msg for k in _CATALOG_KEYWORDS):
                return _reseller_claim_reply(process_reseller_claim_for(reseller, product, quantity, db))

    # 3. Catalogue (or a single product's price card when one is named)
    if any(k in msg for k in _CATALOG_KEYWORDS):
        named = find_product(db, user_message)
        if named and not any(k in msg for k in ("list", "catalog", "catalogue", "menu", "sab", "all", "products")):
            stock = named.get_available_stock_count(db)
            return (
                f"💰 **{named.name}**\n\n"
                f"• Customer price: **₹{named.get_customer_price():,.2f}**\n"
                f"• Reseller price: **₹{named.get_reseller_price():,.2f}** (wallet se katta hai)\n"
                f"• Stock: {'✅ ' + str(stock) + ' available' if stock else '❌ Out of stock'}\n"
                f"• {named.description}\n\n"
                f"Reply *'buy {named.name.split(' (')[0]}'* to order, or send your reseller phone + 4-digit code to claim."
            )
        # Large catalogues: never dump everything. Optional search term narrows the list,
        # otherwise show the first page and tell the user how to search.
        CATALOG_PAGE = 20
        base_q = db.query(Product).filter(Product.is_active == True)  # noqa: E712
        total = base_q.count()
        term_tokens = [t for t in re.findall(r"[a-z0-9]+", msg) if len(t) >= 3 and t not in _CATALOG_KEYWORDS and t not in ("products", "product", "sab", "all", "menu", "list", "catalog", "catalogue", "dikhao", "batao", "kya", "hai", "hain", "aur", "the", "mujhe", "bhai", "koi", "kon", "kaun", "sa", "se", "kya")]
        search_q = base_q
        if term_tokens:
            # ALL words first ("figma premium" -> Figma Premium only), then ANY word, then full list.
            search_q = base_q
            for t in term_tokens[:5]:
                search_q = search_q.filter(Product.name.ilike(f"%{t}%"))
            if search_q.count() == 0:
                search_q = base_q.filter(or_(*[Product.name.ilike(f"%{t}%") for t in term_tokens[:5]]))
            if search_q.count() == 0:
                search_q = base_q
                term_tokens = []
        shown_total = search_q.count()
        products = search_q.order_by(Product.id).limit(CATALOG_PAGE).all()
        stock_map = stock_counts_by_product(db, [p.id for p in products])

        title = f"🛍️ **Products matching '{' '.join(term_tokens)}'** ({shown_total})" if term_tokens else f"🛍️ **Available Digital Products & Live Rates** ({total} products)"
        out = title + "\n\n"
        for p in products:
            stock = stock_map.get(p.id, 0)
            badge = f"✅ {stock} in stock" if stock > 0 else "❌ Out of stock"
            out += f"• **{p.name}** — ₹{p.get_customer_price():,.2f} · reseller ₹{p.get_reseller_price():,.0f} · {badge}\n"
        if shown_total > len(products):
            out += f"\n…aur {shown_total - len(products)} products hain. Brand/naam bhejo (jaise *'notion'*, *'canva pro'*) to exact product dikhaunga.\n"
        out += "\n💡 *Kharidne ke liye product ka naam bhejo. Reseller: bas product ka naam bhejo, wallet se price kat kar link milegi.*"
        return out

    # 4. Payment reference for this conversation's pending order
    ref_match = re.search(r"(?<!\d)(\d{12})(?!\d)", user_message)
    if ref_match or any(k in msg for k in ("utr", "transaction", "paid", "payment done", "pay kar diya")):
        pending = get_pending_order_for_session(db, session_id)
        if not pending:
            return "ℹ️ I couldn't find an unpaid order in this conversation. Tell me which product you'd like and I'll create one."
        ref = ref_match.group(1) if ref_match else ""
        if not is_plausible_payment_ref(ref):
            return f"📲 Please share the **12-digit UTR / transaction ID** from your UPI app for order **{pending.id}** so I can deliver your link."
        res = fulfill_order(pending, ref, db, actor="rule_engine")
        if not res.get("success"):
            return f"⚠️ {res.get('message')}"
        return (
            f"🎉 **Payment confirmed! Order {res['order_id']} fulfilled.**\n\n"
            f"📦 Product: **{res['product_name']}**\n💳 Payment ref: `{ref}`\n\n"
            f"🔗 **Your Single-Use Invite Link:**\n`{res['link']}`\n\n"
            "🔒 *Private single-use link - once activated it cannot be used again.*"
            + _verification_line(res)
        )

    # 5. Customer naming a product -> create / reuse order
    product = find_product(db, user_message)
    if product:
        if product.get_available_stock_count(db) < 1:
            return f"❌ **{product.name}** is currently out of stock. Ask me for the catalogue to see what's available."
        order = get_pending_order_for_session(db, session_id)
        if not order or order.product_id != product.id:
            order = CustomerOrder(
                id=generate_order_id(db),
                session_id=session_id,
                platform=session_rec.platform or "web",
                customer_name=session_rec.customer_name or "Customer",
                customer_phone=session_rec.customer_phone,
                product_id=product.id,
                quantity=1,
                unit_price=product.get_customer_price(),
                total_amount=product.get_customer_price(),
                status="pending_payment",
            )
            db.add(order)
        session_rec.last_order_id = order.id
        db.commit()
        price = order.total_amount
        return (
            f"🛒 **Order {order.id} - {product.name}**\n\n"
            f"• Price: **₹{price:,.2f}**\n• Pay via UPI: `{settings.admin_upi_id}` ({settings.admin_upi_name})\n\n"
            "📲 **Steps:**\n1. Open GPay / PhonePe / Paytm / BHIM\n"
            f"2. Pay ₹{price:,.2f} to `{settings.admin_upi_id}` (note: {order.id})\n"
            "3. Reply here with your 12-digit UTR / transaction ID to get your private invite link instantly."
        )

    # 5b. Admin-trained FAQ / knowledge base (answers general questions the flows above
    #     didn't handle — refund/delivery/how-to-pay/etc., trained from the admin panel).
    kb = match_knowledge(db, user_message)
    if kb:
        record_tool_call("knowledge_base", True, f"#{kb.id} {kb.question}")  # visible in Bot Tester / metadata
        return kb.answer

    # 6. Greeting / help (platform-aware)
    if is_whatsapp:
        # Unregistered WhatsApp number = customer. Never ask "customer ya reseller" — just ask
        # which product they want and show the live catalogue from the admin panel.
        top = db.query(Product).filter(Product.is_active == True).order_by(Product.id).limit(8).all()  # noqa: E712
        total = db.query(Product).filter(Product.is_active == True).count()  # noqa: E712
        stock_map = stock_counts_by_product(db, [p.id for p in top])
        lines = [f"• {p.name.split(' (')[0]} — ₹{p.get_customer_price():,.0f}" + ("" if stock_map.get(p.id, 0) else " (out of stock)") for p in top]
        more = f"\n…aur {total - len(top)} products. Naam bhejo to details dunga." if total > len(top) else ""
        return (
            f"👋 Namaste! **{settings.business_name}** me swagat hai.\n\n"
            "Sir, aapko **kaunsa product** chahiye?\n\n"
            + "\n".join(lines) + more +
            "\n\nBas product ka naam bhejo — price, UPI payment aur link turant milega."
        )
    return (
        f"👋 **Welcome to {settings.business_name}!**\n\n"
        "1. 🛍️ **Customer** - say *'products'* to see live prices and buy via UPI.\n"
        "2. 🔑 **Reseller** - send your registered phone number + 4-digit passcode; link prices are deducted from your wallet.\n\n"
        "How can I help you today?"
    )
