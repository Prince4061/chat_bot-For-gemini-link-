"""
Persistence layer: SQLAlchemy models + the atomic business operations that must never
be duplicated across the code base (link burning, credit deduction, order fulfilment).

Concurrency model
-----------------
* Single-use links are burned with a conditional UPDATE (`WHERE status='available'`)
  and a rowcount check, so two concurrent claims can never receive the same link -
  on SQLite (WAL + busy_timeout) and on Postgres alike.
* Wallet money is deducted/added with conditional `UPDATE ... WHERE wallet_balance + :amt >= 0`,
  never with a read-modify-write in Python.
* Every multi-step operation runs inside one transaction and is rolled back as a whole.
"""
import re
import secrets
import string
import datetime
import logging
import threading
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import (
    create_engine,
    event,
    inspect,
    text,
    update,
    func,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
    UniqueConstraint,
    or_,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import Config

logger = logging.getLogger(__name__)

# =====================================================================
# Engine & session factory
# =====================================================================

DATABASE_URL = Config.DATABASE_URL
IS_SQLITE = DATABASE_URL.startswith("sqlite")

_engine_kwargs: Dict[str, Any] = {"echo": False, "pool_pre_ping": True}
if IS_SQLITE:
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    _engine_kwargs.update({"pool_size": 10, "max_overflow": 20})

engine = create_engine(DATABASE_URL, **_engine_kwargs)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        """Applied to every pooled connection: WAL for concurrency, busy_timeout so
        writers wait instead of failing with 'database is locked'."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()

# Session-per-call (NOT scoped_session): every get_db() returns an independent Session.
# This is essential - helper functions that create their own session (db=None) close it in
# `finally`; with a thread-shared scoped session that close would detach objects still in use
# by the calling request. Concurrency is handled per request, with _CLAIM_LOCK guarding writes.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()

# SQLite serialises writers anyway; this lock keeps the claim critical section short
# and avoids busy-timeout churn under bursts. It is a no-op safety net on Postgres.
_CLAIM_LOCK = threading.RLock()


def utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


# =====================================================================
# Models
# =====================================================================

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    category = Column(String(50), default="AI Tools")
    description = Column(Text, default="")
    base_price = Column(Float, nullable=False, default=0.0)        # Admin cost
    margin_percent = Column(Float, nullable=False, default=30.0)   # Live margin %
    credit_cost = Column(Integer, nullable=False, default=1)       # legacy (credits era), unused
    # What a RESELLER pays per link, in INR. NULL = same as base_price.
    reseller_price = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    links = relationship("InviteLink", back_populates="product", cascade="all, delete-orphan")

    def get_customer_price(self) -> float:
        """Customer price = base + base * margin% / 100 (computed live, never stored)."""
        return round(self.base_price + self.base_price * (self.margin_percent / 100.0), 2)

    def get_reseller_price(self) -> float:
        """Reseller pays this per link (INR). Defaults to the base price when not set."""
        return round(float(self.reseller_price if self.reseller_price is not None else self.base_price), 2)

    def get_available_stock_count(self, session) -> int:
        return session.query(func.count(InviteLink.id)).filter(
            InviteLink.product_id == self.id,
            InviteLink.status == "available",
        ).scalar() or 0

    def to_dict(self, session=None, stock: Optional[int] = None) -> Dict[str, Any]:
        # Pass `stock` (from stock_counts_by_product) when listing many products to avoid N+1 queries.
        if stock is None:
            stock = self.get_available_stock_count(session) if session else 0
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "category": self.category,
            "description": self.description,
            "base_price": self.base_price,
            "margin_percent": self.margin_percent,
            "customer_price": self.get_customer_price(),
            "credit_cost": self.credit_cost,
            "reseller_price": self.get_reseller_price(),
            "reseller_price_set": self.reseller_price is not None,
            "is_active": self.is_active,
            "stock_count": stock,
            "in_stock": stock > 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class InviteLink(Base):
    """
    Single-use link / key inventory. Status is only ever 'available' -> 'claimed';
    a claimed row is immutable and never handed out again.
    """
    __tablename__ = "invite_links"
    __table_args__ = (Index("ix_invite_links_product_status", "product_id", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    link_or_key = Column(Text, nullable=False)
    status = Column(String(20), default="available", index=True)  # available | claimed | used
    # Freshness of the link itself (for auto-verifiable links like Gemini/Google One).
    health = Column(String(20), default="unchecked")     # unchecked | fresh | used | unknown
    health_checked_at = Column(DateTime, nullable=True)
    claimed_by_type = Column(String(20), nullable=True)   # "customer" | "reseller" | "admin"
    claimed_by_id = Column(String(100), nullable=True)    # phone / client id
    claimed_at = Column(DateTime, nullable=True)
    order_id = Column(String(50), nullable=True, index=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    product = relationship("Product", back_populates="links")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else "Unknown",
            "link_or_key": self.link_or_key,
            "status": self.status,
            "health": self.health or "unchecked",
            "health_checked_at": self.health_checked_at.isoformat() if self.health_checked_at else None,
            "claimed_by_type": self.claimed_by_type,
            "claimed_by_id": self.claimed_by_id,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "order_id": self.order_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Reseller(Base):
    __tablename__ = "resellers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(30), unique=True, index=True, nullable=False)
    secret_code = Column(String(10), nullable=False)   # 4-digit passcode
    # TOTAL of per-product credits (kept in sync; display only). Claims use ResellerCredit rows.
    credits_balance = Column(Integer, default=0, nullable=False)
    # Old generic wallet credits that were never tied to a product. Not claimable until the
    # admin assigns them to a product (see assign_legacy_credits).
    legacy_unassigned_credits = Column(Integer, default=0, nullable=False)
    # MONEY WALLET (current model): balance in the reseller's currency. Each claimed link
    # deducts the product's reseller price (converted to this currency if USD).
    wallet_balance = Column(Float, default=0.0, nullable=False)
    currency = Column(String(5), default="INR", nullable=False)   # INR | USD
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    # Brute-force protection
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    transactions = relationship("CreditTransaction", back_populates="reseller", cascade="all, delete-orphan")
    product_credits = relationship("ResellerCredit", back_populates="reseller", cascade="all, delete-orphan")
    wallet_transactions = relationship("WalletTransaction", back_populates="reseller", cascade="all, delete-orphan")

    def money(self, amount: Optional[float] = None) -> str:
        """Format an amount in this reseller's currency, e.g. ₹1,500.00 / $18.07."""
        amt = self.wallet_balance if amount is None else amount
        sym = "$" if (self.currency or "INR").upper() == "USD" else "₹"
        return f"{sym}{float(amt or 0):,.2f}"

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > utcnow())

    def to_dict(self, include_secret: bool = True) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "wallet_balance": round(float(self.wallet_balance or 0), 2),
            "currency": (self.currency or "INR").upper(),
            "wallet_display": self.money(),
            "is_active": self.is_active,
            "is_locked": self.is_locked(),
            "failed_attempts": self.failed_attempts or 0,
            "locked_until": self.locked_until.isoformat() if self.locked_until else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_secret:
            data["secret_code"] = self.secret_code
        return data


class ResellerCredit(Base):
    """
    Per-product credit wallet. Credits given for Gemini can ONLY claim Gemini links.
    This is the source of truth for what a reseller may claim; Reseller.credits_balance
    is just the synced total for display.
    """
    __tablename__ = "reseller_credits"
    __table_args__ = (UniqueConstraint("reseller_id", "product_id", name="uq_reseller_product_credit"),)

    id = Column(Integer, primary_key=True, index=True)
    reseller_id = Column(Integer, ForeignKey("resellers.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    credits = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    reseller = relationship("Reseller", back_populates="product_credits")
    product = relationship("Product")


class WalletTransaction(Base):
    """Money ledger for reseller wallets: top-ups, deductions, link purchases, migrations."""
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    reseller_id = Column(Integer, ForeignKey("resellers.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)          # + top-up / - deduction, in `currency`
    balance_after = Column(Float, nullable=False)
    currency = Column(String(5), default="INR")
    reason = Column(String(50), nullable=False)     # admin_topup | admin_deduct | purchase | link_purchase | migration
    product_id = Column(Integer, nullable=True)
    link_id = Column(Integer, nullable=True)
    reference_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    reseller = relationship("Reseller", back_populates="wallet_transactions")

    def to_dict(self) -> Dict[str, Any]:
        sym = "$" if (self.currency or "INR").upper() == "USD" else "₹"
        return {
            "id": self.id,
            "reseller_id": self.reseller_id,
            "reseller_name": self.reseller.name if self.reseller else "Unknown",
            "reseller_phone": self.reseller.phone if self.reseller else "Unknown",
            "amount": round(float(self.amount), 2),
            "amount_display": f"{'+' if self.amount >= 0 else '-'}{sym}{abs(float(self.amount)):,.2f}",
            "balance_after": round(float(self.balance_after), 2),
            "currency": (self.currency or "INR").upper(),
            "reason": self.reason,
            "product_id": self.product_id,
            "link_id": self.link_id,
            "reference_note": self.reference_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    reseller_id = Column(Integer, ForeignKey("resellers.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)          # +credits / -credits
    balance_after = Column(Integer, nullable=False)
    reason = Column(String(50), nullable=False)       # claim_link | admin_topup | admin_deduct | purchase
    product_id = Column(Integer, nullable=True)
    link_id = Column(Integer, nullable=True)
    reference_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    reseller = relationship("Reseller", back_populates="transactions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "reseller_id": self.reseller_id,
            "reseller_name": self.reseller.name if self.reseller else "Unknown",
            "reseller_phone": self.reseller.phone if self.reseller else "Unknown",
            "amount": self.amount,
            "balance_after": self.balance_after,
            "reason": self.reason,
            "product_id": self.product_id,
            "link_id": self.link_id,
            "reference_note": self.reference_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CustomerOrder(Base):
    __tablename__ = "customer_orders"

    id = Column(String(50), primary_key=True, index=True)      # ORD-XXXXXX
    session_id = Column(String(100), nullable=True, index=True)  # chat session that created it
    platform = Column(String(20), default="web")
    customer_name = Column(String(100), default="Customer")
    customer_phone = Column(String(30), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    payment_method = Column(String(30), default="UPI_QR")
    payment_ref = Column(String(100), nullable=True, index=True)   # UTR / txn reference
    status = Column(String(30), default="pending_payment", index=True)  # pending_payment | delivered | cancelled | fulfillment_pending
    delivered_link_id = Column(Integer, nullable=True)
    delivered_link_content = Column(Text, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    product = relationship("Product")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "platform": self.platform,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else "Unknown",
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "total_amount": self.total_amount,
            "payment_method": self.payment_method,
            "payment_ref": self.payment_ref,
            "status": self.status,
            "delivered_link_id": self.delivered_link_id,
            "delivered_link_content": self.delivered_link_content,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)
    business_name = Column(String(150), default="AI Digital Vending Hub")
    admin_upi_id = Column(String(100), default=Config.ADMIN_UPI_ID)
    admin_upi_name = Column(String(100), default=Config.ADMIN_UPI_NAME)
    # WhatsApp/phone number an unregistered user is told to contact to buy credits.
    admin_contact_number = Column(String(30), default="")
    qr_code_image_url = Column(Text, nullable=True)
    reseller_credit_rate_inr = Column(Float, default=Config.RESELLER_CREDIT_RATE_INR)   # now: minimum wallet top-up (INR)
    usd_to_inr_rate = Column(Float, default=83.0)   # used to charge USD-wallet resellers for INR-priced products
    reseller_terms = Column(Text, default="Minimum credit pack: 10 Credits (Rs 1,500). 1 Credit = 1 Single-Use Invite Link.")
    evolution_api_url = Column(String(200), default=Config.EVOLUTION_API_URL)
    evolution_api_key = Column(String(200), default=Config.EVOLUTION_API_KEY)
    evolution_instance_name = Column(String(100), default=Config.EVOLUTION_INSTANCE_NAME)
    openai_api_key = Column(String(200), nullable=True)
    openai_model_name = Column(String(50), default=Config.OPENAI_MODEL_NAME)
    # Free-text extra instructions the admin trains the agent with (persona, rules, tone...).
    agent_instructions = Column(Text, default="")

    @staticmethod
    def _mask(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return "••••" + value[-4:] if len(value) > 4 else "••••"

    def to_dict(self) -> Dict[str, Any]:
        """Secrets are never returned in clear text - only a masked tail."""
        return {
            "id": self.id,
            "business_name": self.business_name,
            "admin_upi_id": self.admin_upi_id,
            "admin_upi_name": self.admin_upi_name,
            "admin_contact_number": self.admin_contact_number or "",
            "qr_code_image_url": self.qr_code_image_url,
            "reseller_credit_rate_inr": self.reseller_credit_rate_inr,
            "usd_to_inr_rate": self.usd_to_inr_rate or 83.0,
            "reseller_terms": self.reseller_terms,
            "evolution_api_url": self.evolution_api_url,
            "evolution_api_key": self._mask(self.evolution_api_key),
            "evolution_instance_name": self.evolution_instance_name,
            "openai_model_name": self.openai_model_name,
            "openai_api_key": self._mask(self.openai_api_key),
            "has_openai_key": bool(self.openai_api_key or Config.OPENAI_API_KEY),
            "agent_instructions": self.agent_instructions or "",
        }


class ChatSessionRecord(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(100), primary_key=True)
    owner_id = Column(String(100), nullable=True, index=True)   # browser client id / WhatsApp phone
    platform = Column(String(20), default="web")                # web | whatsapp
    user_type = Column(String(30), default="customer")          # customer | reseller
    title = Column(String(200), default="New Conversation")
    customer_name = Column(String(100), nullable=True)
    customer_phone = Column(String(30), nullable=True)
    # Reseller "login" state for this conversation
    reseller_id = Column(Integer, nullable=True)
    reseller_phone = Column(String(30), nullable=True)
    reseller_verified_at = Column(DateTime, nullable=True)
    # Most recent order created from this conversation
    last_order_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, index=True)

    messages = relationship(
        "ChatMessageRecord", back_populates="session",
        cascade="all, delete-orphan", order_by="ChatMessageRecord.id",
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "platform": self.platform,
            "user_type": self.user_type,
            "title": self.title,
            "customer_phone": self.customer_phone,
            "reseller_phone": self.reseller_phone,
            "reseller_verified": bool(self.reseller_id),
            "last_order_id": self.last_order_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)   # user | assistant | system
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    session = relationship("ChatSessionRecord", back_populates="messages")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class KnowledgeEntry(Base):
    """
    Admin-trained Q&A / FAQ. The bot uses these to answer matching questions:
    the LLM gets them as reference material, and the rule engine matches on keywords.
    """
    __tablename__ = "knowledge_entries"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)             # the example question / topic
    answer = Column(Text, nullable=False)               # how the bot should reply
    keywords = Column(Text, default="")                 # comma/newline separated trigger words
    priority = Column(Integer, default=0)               # higher = matched first
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def keyword_list(self) -> List[str]:
        raw = self.keywords or ""
        parts = re.split(r"[,\n;]+", raw)
        return [p.strip().lower() for p in parts if p.strip()]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "keywords": self.keywords or "",
            "priority": self.priority or 0,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =====================================================================
# Helpers
# =====================================================================

def normalize_phone(phone: Optional[str]) -> str:
    """Strip formatting and reduce Indian numbers to their 10-digit form."""
    if not phone:
        return ""
    clean = re.sub(r"[^\d+]", "", str(phone).strip())
    if clean.startswith("+91") and len(clean) == 13:
        return clean[3:]
    if clean.startswith("91") and len(clean) == 12:
        return clean[2:]
    if clean.startswith("0") and len(clean) == 11:
        return clean[1:]
    return clean


def is_valid_secret_code(code: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", str(code or "").strip()))


def is_plausible_payment_ref(ref: str) -> bool:
    """UPI UTRs are 12 digits; bank references vary. Accept 6-40 alphanumerics."""
    return bool(re.fullmatch(r"[A-Za-z0-9\-]{6,40}", str(ref or "").strip()))


def get_db():
    """Thread-local SQLAlchemy session. Caller must `close()`."""
    return SessionLocal()


def get_settings(db=None) -> SystemSettings:
    close_when_done = db is None
    db = db or get_db()
    try:
        settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
        if not settings:
            settings = SystemSettings(id=1)
            db.add(settings)
            db.commit()
            db.refresh(settings)
        return settings
    finally:
        if close_when_done:
            db.close()


_STOPWORDS = {
    "the", "and", "for", "you", "your", "kya", "hai", "hain", "kaise", "kaisa", "mera", "meri",
    "main", "mujhe", "aap", "how", "what", "when", "where", "can", "please", "will", "with",
    "about", "koi", "hoga", "karo", "karna", "chahiye", "chahta", "batao", "bata",
}


def get_active_knowledge(db, limit: int = 200) -> List["KnowledgeEntry"]:
    return (
        db.query(KnowledgeEntry)
        .filter(KnowledgeEntry.is_active == True)  # noqa: E712
        .order_by(KnowledgeEntry.priority.desc(), KnowledgeEntry.id.asc())
        .limit(limit)
        .all()
    )


def match_knowledge(db, message: str) -> Optional["KnowledgeEntry"]:
    """
    Return the best-matching active knowledge entry for a user message, or None.
    Matches on admin keywords first; falls back to significant words of the question.
    Requires at least one solid keyword hit so it never hijacks unrelated messages.
    """
    text = (message or "").lower()
    if not text.strip():
        return None
    best, best_score = None, 0
    for entry in get_active_knowledge(db):
        kws = entry.keyword_list()
        if not kws:
            # derive keywords from the question itself
            kws = [w for w in re.findall(r"[a-z0-9]+", (entry.question or "").lower())
                   if len(w) >= 4 and w not in _STOPWORDS]
        score = 0
        for kw in kws:
            if not kw:
                continue
            # phrase keyword (has space) -> substring; single word -> word-boundary match
            if " " in kw:
                if kw in text:
                    score += 2
            elif re.search(rf"\b{re.escape(kw)}\b", text):
                score += 1
        if score > best_score:
            best, best_score = entry, score
    return best if best_score >= 1 else None


def stock_counts_by_product(db, product_ids: Optional[List[int]] = None) -> Dict[int, int]:
    """One GROUP BY query for available stock -> {product_id: count}. Use for lists/metrics."""
    q = db.query(InviteLink.product_id, func.count(InviteLink.id)).filter(InviteLink.status == "available")
    if product_ids is not None:
        if not product_ids:
            return {}
        q = q.filter(InviteLink.product_id.in_(product_ids))
    return {pid: int(n) for pid, n in q.group_by(InviteLink.product_id).all()}


# Words that carry no product identity in a chat message (kept out of the SQL pre-filter).
_QUERY_NOISE = _STOPWORDS | {
    "link", "links", "chahiye", "chaiye", "price", "rate", "cost", "kitne", "kitna", "dikhao",
    "batao", "bhejo", "claim", "order", "buy", "want", "need", "give", "send", "please", "bhai",
    "mujhe", "muje", "mera", "meri", "hai", "hain", "kya", "kaise", "ka", "ki", "ke", "do", "de",
}


def find_product(db, name_or_slug_or_id: Any, active_only: bool = True) -> Optional[Product]:
    """
    Resolve a product by id, exact slug, direct name/slug substring, or free text.
    Scales to very large catalogues: free-text matching pre-filters candidates in SQL by the
    message's significant words, then ranks them by (distinctive-token hits, all-token hits,
    shorter name). Tier words like "Team"/"Enterprise" and numbers act as tie-breakers, so
    "notion team" picks a Notion *Team* plan and "00302" picks the exact variant.
    """
    if name_or_slug_or_id is None:
        return None
    q = db.query(Product)
    if active_only:
        q = q.filter(Product.is_active == True)  # noqa: E712

    raw = str(name_or_slug_or_id).strip()
    if not raw:
        return None
    if raw.isdigit():
        return q.filter(Product.id == int(raw)).first()

    exact = q.filter(func.lower(Product.slug) == raw.lower()).first()
    if exact:
        return exact

    like = f"%{raw}%"
    candidates = q.filter((Product.slug.ilike(like)) | (Product.name.ilike(like))).limit(50).all()
    if candidates:
        # Prefer the shortest name: "Claude Pro" beats "Claude Pro Team Bundle" for "claude".
        return sorted(candidates, key=lambda p: len(p.name))[0]

    text_tokens = set(re.findall(r"[a-z0-9]+", raw.lower()))
    # SQL pre-filter: only products whose name/slug contains at least one significant word.
    sig = [t for t in text_tokens if len(t) >= 3 and t not in _QUERY_NOISE]
    if not sig:
        return None
    conds = []
    for t in sig[:8]:
        conds.append(Product.name.ilike(f"%{t}%"))
        conds.append(Product.slug.ilike(f"%{t}%"))
    cands = q.filter(or_(*conds)).limit(3000).all()

    best, best_key = None, None
    for p in cands:
        tokens = set(re.findall(r"[a-z0-9]+", f"{p.name} {p.slug}".lower()))
        distinctive = {t for t in tokens if len(t) >= 4 and t not in _GENERIC_PRODUCT_WORDS}
        primary = len(distinctive & text_tokens)          # brand / model / number words
        if primary == 0:
            continue
        secondary = len(tokens & text_tokens)             # + tier words (team, premium, ...)
        key = (primary, secondary, -len(p.name))
        if best_key is None or key > best_key:
            best, best_key = p, key
    return best


_GENERIC_PRODUCT_WORDS = {
    "link", "links", "invite", "invitation", "private", "organization", "organisation", "account",
    "year", "month", "lifetime", "seat", "workspace", "device", "devices", "enterprise", "edu",
    "premium", "plus", "advanced", "with", "from", "digital", "product", "subscription", "access",
    "family", "team", "plan", "pack", "license", "licence", "key", "code",
}


def generate_order_id(db) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(10):
        candidate = "ORD-" + "".join(secrets.choice(alphabet) for _ in range(6))
        if not db.query(CustomerOrder.id).filter(CustomerOrder.id == candidate).first():
            return candidate
    raise RuntimeError("Could not generate a unique order id")


# =====================================================================
# Reseller authentication (with brute-force lockout)
# =====================================================================

def find_reseller_by_phone(db, phone: str) -> Optional[Reseller]:
    norm = normalize_phone(phone)
    if not norm:
        return None
    return db.query(Reseller).filter(
        (Reseller.phone == norm) | (Reseller.phone == f"+91{norm}") | (Reseller.phone == f"91{norm}")
    ).first()


# ---------------------------------------------------------------------
# Per-product credits (the ONLY thing a reseller can claim against)
# ---------------------------------------------------------------------

def get_reseller_product_credits(db, reseller: Reseller) -> List[Dict[str, Any]]:
    rows = db.query(ResellerCredit).filter(ResellerCredit.reseller_id == reseller.id).all()
    out = []
    for rc in rows:
        p = rc.product
        out.append({
            "product_id": rc.product_id,
            "product_name": p.name if p else f"#{rc.product_id}",
            "slug": p.slug if p else None,
            "credits": rc.credits,
        })
    return sorted(out, key=lambda x: x["product_id"])


def get_reseller_credit_for_product(db, reseller_id: int, product_id: int) -> int:
    rc = db.query(ResellerCredit).filter_by(reseller_id=reseller_id, product_id=product_id).first()
    return int(rc.credits) if rc else 0


def credits_summary_text(db, reseller: Reseller) -> str:
    """Human line like 'Gemini Advanced: 5, Claude Pro: 2' (only products with credits)."""
    items = [
        f"{c['product_name'].split(' (')[0]}: {c['credits']}"
        for c in get_reseller_product_credits(db, reseller) if c["credits"] > 0
    ]
    return ", ".join(items) if items else "koi credits nahi"


def sync_reseller_total(db, reseller: Reseller) -> int:
    """Keep Reseller.credits_balance == sum of per-product credits (display only)."""
    db.flush()  # session has autoflush=False: push pending credit changes before summing
    total = db.query(func.coalesce(func.sum(ResellerCredit.credits), 0)).filter(
        ResellerCredit.reseller_id == reseller.id
    ).scalar() or 0
    reseller.credits_balance = int(total)
    reseller.updated_at = utcnow()
    return int(total)


def adjust_reseller_product_credits(db, reseller: Reseller, product: Product, amount: int,
                                    reason: str = "admin_topup", note: str = "") -> Dict[str, Any]:
    """Add (+) or deduct (-) credits for ONE product. Never lets a product go negative."""
    amount = int(amount)
    if amount == 0:
        return {"success": False, "error": "INVALID_AMOUNT", "message": "Amount cannot be zero."}
    rc = db.query(ResellerCredit).filter_by(reseller_id=reseller.id, product_id=product.id).first()
    if not rc:
        rc = ResellerCredit(reseller_id=reseller.id, product_id=product.id, credits=0)
        db.add(rc)
        db.flush()
    if rc.credits + amount < 0:
        return {"success": False, "error": "INSUFFICIENT",
                "message": f"Cannot deduct {abs(amount)}: only {rc.credits} credit(s) for {product.name}."}
    rc.credits += amount
    rc.updated_at = utcnow()
    total = sync_reseller_total(db, reseller)
    db.add(CreditTransaction(
        reseller_id=reseller.id, amount=amount, balance_after=rc.credits, reason=reason,
        product_id=product.id,
        reference_note=note or f"{'Added' if amount > 0 else 'Deducted'} {abs(amount)} credit(s) for {product.name}",
    ))
    db.commit()
    db.refresh(reseller)
    return {"success": True, "product_id": product.id, "product_name": product.name, "change": amount,
            "credits_for_product": rc.credits, "total_credits": total}


def assign_legacy_credits(db, reseller: Reseller, product: Product, amount: int) -> Dict[str, Any]:
    """Move old un-tied wallet credits onto a specific product so they become claimable."""
    amount = int(amount)
    legacy = reseller.legacy_unassigned_credits or 0
    if amount <= 0 or amount > legacy:
        return {"success": False, "error": "INVALID_AMOUNT", "message": f"Choose between 1 and {legacy} legacy credit(s)."}
    reseller.legacy_unassigned_credits = legacy - amount
    return adjust_reseller_product_credits(db, reseller, product, amount, reason="legacy_assign",
                                           note=f"Assigned {amount} legacy credit(s) to {product.name}")


# ---------------------------------------------------------------------
# Money wallet (current model). The per-product credit helpers above are legacy and
# only used by the one-time migration.
# ---------------------------------------------------------------------

def product_charge_for(db, reseller: Reseller, product: Product) -> float:
    """What this reseller pays for ONE link of `product`, in the reseller's own currency."""
    price_inr = product.get_reseller_price()
    if (reseller.currency or "INR").upper() == "USD":
        rate = float(get_settings(db).usd_to_inr_rate or 83.0)
        return round(price_inr / rate, 2) if rate > 0 else price_inr
    return price_inr


def wallet_summary_text(db, reseller: Reseller) -> str:
    return reseller.money()


def adjust_reseller_wallet(db, reseller: Reseller, amount: float, reason: str = "admin_topup",
                           note: str = "", product_id: Optional[int] = None, link_id: Optional[int] = None) -> Dict[str, Any]:
    """Add (+) or deduct (-) money from a reseller's wallet with a ledger entry. Never goes negative."""
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return {"success": False, "error": "INVALID_AMOUNT", "message": "Amount must be a number."}
    if amount == 0:
        return {"success": False, "error": "INVALID_AMOUNT", "message": "Amount cannot be zero."}
    # Atomic conditional UPDATE against the LIVE database value. Never do read-modify-write on the
    # in-memory object: a stale copy (e.g. admin top-up while a claim ran in another request) would
    # silently overwrite money. The WHERE clause also guarantees the balance can't go negative.
    with _CLAIM_LOCK:
        result = db.execute(
            update(Reseller)
            .where(Reseller.id == reseller.id, Reseller.wallet_balance + amount >= 0)
            .values(wallet_balance=Reseller.wallet_balance + amount, updated_at=utcnow())
        )
        if result.rowcount != 1:
            db.rollback()
            db.refresh(reseller)
            return {"success": False, "error": "INSUFFICIENT",
                    "message": f"Cannot deduct {reseller.money(abs(amount))}: balance is only {reseller.money()}."}
        db.refresh(reseller)  # re-read the row we just updated (same transaction)
        db.add(WalletTransaction(
            reseller_id=reseller.id, amount=amount, balance_after=round(float(reseller.wallet_balance), 2),
            currency=(reseller.currency or "INR").upper(), reason=reason, product_id=product_id, link_id=link_id,
            reference_note=note or (f"{'Added' if amount > 0 else 'Deducted'} {reseller.money(abs(amount))}"),
        ))
        db.commit()
    db.refresh(reseller)
    return {"success": True, "change": amount, "new_balance": round(float(reseller.wallet_balance), 2),
            "currency": (reseller.currency or "INR").upper(), "balance_display": reseller.money()}


def verify_reseller_auth(phone: str, secret_code: str, db=None) -> Tuple[bool, Optional[Reseller], str]:
    """
    Returns (is_valid, reseller, message). Wrong codes count towards a temporary lockout;
    a correct code resets the counter.
    """
    close_when_done = db is None
    db = db or get_db()
    try:
        reseller = find_reseller_by_phone(db, phone)
        if not reseller:
            return False, None, "This phone number is not registered as a reseller."
        if not reseller.is_active:
            return False, reseller, "Reseller account is inactive. Please contact the admin."
        if reseller.is_locked():
            remaining = int((reseller.locked_until - utcnow()).total_seconds() // 60) + 1
            return False, reseller, f"Too many failed attempts. Account locked for {remaining} more minute(s)."

        if (reseller.secret_code or "").strip() != str(secret_code or "").strip():
            reseller.failed_attempts = (reseller.failed_attempts or 0) + 1
            attempts_left = Config.RESELLER_MAX_FAILED_ATTEMPTS - reseller.failed_attempts
            if attempts_left <= 0:
                reseller.locked_until = utcnow() + datetime.timedelta(minutes=Config.RESELLER_LOCKOUT_MINUTES)
                reseller.failed_attempts = 0
                db.commit()
                return False, reseller, (
                    f"Incorrect passcode. Account locked for {Config.RESELLER_LOCKOUT_MINUTES} minutes "
                    "for security."
                )
            db.commit()
            return False, reseller, f"Incorrect 4-digit passcode. {attempts_left} attempt(s) left."

        reseller.failed_attempts = 0
        reseller.locked_until = None
        reseller.last_login_at = utcnow()
        db.commit()
        return True, reseller, "Authentication successful."
    finally:
        if close_when_done:
            db.close()


# =====================================================================
# Atomic single-use link burning
# =====================================================================

def _claim_links_in_transaction(
    db, product_id: int, quantity: int, claimed_by_type: str, claimed_by_id: str, order_id: Optional[str]
) -> List[InviteLink]:
    """
    Burns up to `quantity` links using conditional UPDATEs. Runs inside the caller's
    transaction and does NOT commit. Returns the claimed link rows (may be fewer than
    requested if stock ran out - caller decides whether to roll back).
    """
    claimed_ids: List[int] = []
    attempts = 0
    max_attempts = quantity * 5 + 5
    now = utcnow()
    raw_who = str(claimed_by_id or "")
    # Only phone-like identifiers get normalised; session/client ids are stored verbatim.
    who = normalize_phone(raw_who) if re.fullmatch(r"[\d+\-\s()]{6,}", raw_who) else raw_who[:100]

    while len(claimed_ids) < quantity and attempts < max_attempts:
        attempts += 1
        candidate = (
            db.query(InviteLink.id)
            .filter(InviteLink.product_id == product_id, InviteLink.status == "available")
            .order_by(InviteLink.id.asc())
            .first()
        )
        if not candidate:
            break
        result = db.execute(
            update(InviteLink)
            .where(InviteLink.id == candidate.id, InviteLink.status == "available")
            .values(
                status="claimed",
                claimed_by_type=claimed_by_type,
                claimed_by_id=who,
                claimed_at=now,
                order_id=order_id,
            )
        )
        if result.rowcount == 1:
            claimed_ids.append(candidate.id)
        # rowcount 0 => somebody else won that row; loop picks the next one.

    if not claimed_ids:
        return []
    return db.query(InviteLink).filter(InviteLink.id.in_(claimed_ids)).order_by(InviteLink.id).all()


def ensure_fresh_stock(db, product_id: int, max_checks: int = 12) -> Dict[str, Any]:
    """
    Lazily verify links AT CLAIM TIME: walk the oldest available links, and for any that
    are verifiable (e.g. Gemini/Google One), check freshness. Mark USED links as status='used'
    (so they are never handed out and show up in the admin panel), and stop as soon as the
    front-most available link is fresh/unknown/non-checkable. Runs OUTSIDE the claim lock
    (does its own commits) so we never hold a DB lock during network calls.
    """
    from link_checker import is_checkable, check_link_freshness  # local import: optional dep

    marked_used, checked = 0, 0
    while checked < max_checks:
        link = (
            db.query(InviteLink)
            .filter(InviteLink.product_id == product_id, InviteLink.status == "available")
            .order_by(InviteLink.id.asc())
            .first()
        )
        if not link:
            break
        if not is_checkable(link.link_or_key):
            break  # can't verify this type -> hand it out as-is
        checked += 1
        health = check_link_freshness(link.link_or_key)
        link.health = health
        link.health_checked_at = utcnow()
        if health == "used":
            link.status = "used"
            marked_used += 1
            db.commit()
            continue  # try the next available link
        db.commit()
        break  # front link is fresh/unknown -> good to hand out
    return {"checked": checked, "marked_used": marked_used}


def claim_single_use_link(
    product_id: int,
    claimed_by_type: str,
    claimed_by_id: str,
    order_id: Optional[str] = None,
    db=None,
) -> Tuple[bool, Optional[InviteLink], str]:
    """Burn exactly one link and commit. Used by admin fulfilment and tests."""
    close_when_done = db is None
    db = db or get_db()
    try:
        with _CLAIM_LOCK:
            links = _claim_links_in_transaction(db, product_id, 1, claimed_by_type, claimed_by_id, order_id)
            if not links:
                db.rollback()
                return False, None, "Out of stock! No available single-use invite links for this product."
            db.commit()
        return True, links[0], "Link successfully claimed."
    except Exception as exc:
        db.rollback()
        logger.exception("claim_single_use_link failed")
        return False, None, f"Database error claiming link: {exc}"
    finally:
        if close_when_done:
            db.close()


# =====================================================================
# Reseller claim workflow
# =====================================================================

def process_reseller_claim_for(reseller: Reseller, product: Product, quantity: int, db) -> Dict[str, Any]:
    """
    Core reseller claim for an already-authenticated reseller. One transaction:
      deduct credits (guarded) -> burn links -> write audit rows -> commit.
    Any failure rolls back everything, so credits are never lost without links.
    """
    try:
        quantity = 1 if quantity is None else int(quantity)
    except (TypeError, ValueError):
        return {"success": False, "error": "INVALID_QUANTITY", "message": "Quantity must be a whole number."}
    if quantity < 1:
        return {"success": False, "error": "INVALID_QUANTITY", "message": "Quantity must be at least 1."}
    if quantity > Config.MAX_CLAIM_QUANTITY:
        return {
            "success": False,
            "error": "INVALID_QUANTITY",
            "message": f"You can claim at most {Config.MAX_CLAIM_QUANTITY} links per request.",
        }

    unit_charge = product_charge_for(db, reseller, product)     # in the reseller's currency
    total_charge = round(unit_charge * quantity, 2)

    # Verify freshness lazily before claiming, so resellers only get fresh links.
    try:
        for _ in range(quantity):
            ensure_fresh_stock(db, product.id)
    except Exception:  # noqa: BLE001
        logger.exception("ensure_fresh_stock failed (continuing with unchecked stock)")

    try:
        with _CLAIM_LOCK:
            # 1. Guarded WALLET deduction: money is taken only if the balance covers the price.
            if not reseller.is_active:
                return {"success": False, "error": "AUTH_FAILED", "message": "Reseller account is inactive."}
            result = db.execute(
                update(Reseller)
                .where(
                    Reseller.id == reseller.id,
                    Reseller.is_active == True,  # noqa: E712
                    Reseller.wallet_balance >= total_charge,
                )
                .values(wallet_balance=Reseller.wallet_balance - total_charge, updated_at=utcnow())
            )
            if result.rowcount != 1:
                db.rollback()
                db.refresh(reseller)
                return {
                    "success": False,
                    "error": "INSUFFICIENT_BALANCE",
                    "message": (
                        f"Aapke wallet me {reseller.money()} hai, lekin {product.name.split(' (')[0]} "
                        f"ki {quantity} link ka price {reseller.money(total_charge)} hai "
                        f"({reseller.money(unit_charge)} x {quantity}). Wallet top-up ke liye admin se baat karein."
                    ),
                    "wallet_balance": reseller.wallet_balance,
                    "balance_display": reseller.money(),
                    "required": total_charge,
                    "required_display": reseller.money(total_charge),
                    "currency": (reseller.currency or "INR").upper(),
                }

            # 2. Burn links.
            order_ref = f"RES-{reseller.id}-{int(utcnow().timestamp())}"
            links = _claim_links_in_transaction(db, product.id, quantity, "reseller", reseller.phone, order_ref)
            if len(links) < quantity:
                db.rollback()
                available = product.get_available_stock_count(db)
                return {
                    "success": False,
                    "error": "OUT_OF_STOCK",
                    "message": f"Only {available} link(s) currently in stock for {product.name}. Requested {quantity}. No money was deducted.",
                    "available_stock": available,
                }

            # 3. Ledger entries (one per link).
            db.refresh(reseller)
            running = float(reseller.wallet_balance) + total_charge
            for link in links:
                running = round(running - unit_charge, 2)
                db.add(WalletTransaction(
                    reseller_id=reseller.id,
                    amount=-unit_charge,
                    balance_after=running,
                    currency=(reseller.currency or "INR").upper(),
                    reason="link_purchase",
                    product_id=product.id,
                    link_id=link.id,
                    reference_note=f"Bought 1 single-use link of {product.name} ({order_ref})",
                ))
            db.commit()
            db.refresh(reseller)

        logger.info("Reseller %s bought %d x %s for %s (balance now %s)", reseller.phone, quantity, product.slug,
                    reseller.money(total_charge), reseller.money())
        return {
            "success": True,
            "message": f"Successfully claimed {quantity} link(s) for {product.name}!",
            "product_name": product.name,
            "quantity": quantity,
            "charged": total_charge,
            "charged_display": reseller.money(total_charge),
            "unit_price": unit_charge,
            "unit_price_display": reseller.money(unit_charge),
            "remaining_balance": reseller.wallet_balance,
            "balance_display": reseller.money(),
            "currency": (reseller.currency or "INR").upper(),
            "links": [l.link_or_key for l in links],
            "links_claimed_ids": [l.id for l in links],
            "reseller_name": reseller.name,
            "reseller_phone": reseller.phone,
        }
    except Exception as exc:
        db.rollback()
        logger.exception("process_reseller_claim_for failed")
        return {"success": False, "error": "SERVER_ERROR", "message": f"An error occurred: {exc}"}


def process_reseller_claim(phone: str, secret_code: str, product_id_or_slug: Any, quantity: int = 1, db=None) -> Dict[str, Any]:
    """Authenticate, resolve product, then run the atomic claim."""
    close_when_done = db is None
    db = db or get_db()
    try:
        is_auth, reseller, msg = verify_reseller_auth(phone, secret_code, db=db)
        if not is_auth:
            return {"success": False, "error": "AUTH_FAILED", "message": msg}
        product = find_product(db, product_id_or_slug)
        if not product:
            return {"success": False, "error": "PRODUCT_NOT_FOUND", "message": f"Product '{product_id_or_slug}' not found or inactive."}
        return process_reseller_claim_for(reseller, product, quantity, db)
    finally:
        if close_when_done:
            db.close()


# =====================================================================
# Customer order fulfilment
# =====================================================================

def is_payment_ref_used(db, payment_ref: str, exclude_order_id: Optional[str] = None) -> bool:
    """A UTR may only ever fulfil one order (prevents replaying one payment)."""
    ref = str(payment_ref or "").strip()
    if not ref or ref.upper() == "ADMIN_APPROVED":
        return False
    q = db.query(CustomerOrder.id).filter(func.upper(CustomerOrder.payment_ref) == ref.upper())
    if exclude_order_id:
        q = q.filter(CustomerOrder.id != exclude_order_id)
    return q.first() is not None


def fulfill_order(order: CustomerOrder, payment_ref: str, db, actor: str = "customer") -> Dict[str, Any]:
    """
    Mark an order paid and deliver exactly one burned link. Idempotent: a delivered order
    returns its existing link instead of burning another.
    """
    ref = str(payment_ref or "").strip()

    if order.status == "delivered" and order.delivered_link_content:
        return {
            "success": True,
            "already_delivered": True,
            "order_id": order.id,
            "product_name": order.product.name if order.product else "Digital Product",
            "link": order.delivered_link_content,
            "message": f"Order {order.id} was already fulfilled.",
        }
    if order.status == "cancelled":
        return {"success": False, "error": "ORDER_CANCELLED", "message": f"Order {order.id} was cancelled."}
    if is_payment_ref_used(db, ref, exclude_order_id=order.id):
        return {
            "success": False,
            "error": "PAYMENT_REF_REUSED",
            "message": "This payment reference has already been used for another order. Please share the correct UTR.",
        }

    # Verify freshness lazily before delivering, so customers only get fresh links.
    try:
        ensure_fresh_stock(db, order.product_id)
    except Exception:  # noqa: BLE001
        logger.exception("ensure_fresh_stock failed (continuing with unchecked stock)")

    try:
        with _CLAIM_LOCK:
            links = _claim_links_in_transaction(
                db, order.product_id, 1, "customer",
                order.customer_phone or order.session_id or order.id, order.id,
            )
            if not links:
                # Keep the payment on record so the admin can fulfil manually.
                order.payment_ref = ref or order.payment_ref
                order.paid_at = order.paid_at or utcnow()
                order.status = "fulfillment_pending"
                db.commit()
                return {
                    "success": False,
                    "error": "OUT_OF_STOCK",
                    "order_id": order.id,
                    "message": (
                        f"Payment reference {ref} recorded for order {order.id}, but stock is momentarily exhausted. "
                        "The admin has been notified and will deliver your link shortly."
                    ),
                }
            link = links[0]
            order.payment_ref = ref or order.payment_ref
            order.paid_at = order.paid_at or utcnow()
            order.delivered_at = utcnow()
            order.status = "delivered"
            order.delivered_link_id = link.id
            order.delivered_link_content = link.link_or_key
            db.commit()
        logger.info("Order %s fulfilled by %s (ref=%s)", order.id, actor, ref)
        return {
            "success": True,
            "already_delivered": False,
            "order_id": order.id,
            "product_name": order.product.name if order.product else "Digital Product",
            "link": link.link_or_key,
            "payment_ref": order.payment_ref,
            "message": "Payment confirmed and single-use link delivered.",
        }
    except Exception as exc:
        db.rollback()
        logger.exception("fulfill_order failed")
        return {"success": False, "error": "SERVER_ERROR", "message": str(exc)}


def get_pending_order_for_session(db, session_id: str) -> Optional[CustomerOrder]:
    if not session_id:
        return None
    return (
        db.query(CustomerOrder)
        .filter(CustomerOrder.session_id == session_id, CustomerOrder.status == "pending_payment")
        .order_by(CustomerOrder.created_at.desc())
        .first()
    )


# =====================================================================
# Schema bootstrap & light migrations
# =====================================================================

def _ensure_columns() -> None:
    """
    `create_all` never alters existing tables. Add any columns that newer versions
    introduced so an existing SQLite/Postgres database keeps working after upgrade.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}'))
                logger.info("Migrated: added column %s.%s", table.name, column.name)
    # `create_all` skips existing tables entirely, so newly declared indexes need an explicit pass.
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)


def _migrate_credits_to_wallet(db) -> None:
    """
    One-time conversion of the old credit systems into money:
      * per-product credits  -> credits x that product's reseller price (INR)
      * unassigned/generic credits -> credits x reseller_credit_rate_inr
    Balances land in `wallet_balance` (INR) with a 'migration' ledger entry; the old rows/
    counters are zeroed/deleted so this is idempotent and never runs twice for a reseller.
    """
    rate = float(get_settings(db).reseller_credit_rate_inr or 150.0)
    migrated = 0
    for r in db.query(Reseller).all():
        rows = db.query(ResellerCredit).filter_by(reseller_id=r.id).all()
        legacy = int(r.legacy_unassigned_credits or 0)
        generic = int(r.credits_balance or 0) if not rows else 0   # credits_balance mirrors rows when rows exist
        if not rows and legacy == 0 and generic == 0:
            continue
        value = 0.0
        for rc in rows:
            price = rc.product.get_reseller_price() if rc.product else rate
            value += rc.credits * price
            db.delete(rc)
        value += legacy * rate + generic * rate
        value = round(value, 2)
        r.legacy_unassigned_credits = 0
        r.credits_balance = 0
        if value > 0:
            r.wallet_balance = round(float(r.wallet_balance or 0) + value, 2)
            db.add(WalletTransaction(reseller_id=r.id, amount=value, balance_after=r.wallet_balance,
                                     currency=(r.currency or "INR").upper(), reason="migration",
                                     reference_note="Converted old credits into wallet money"))
        migrated += 1
    if migrated:
        db.commit()
        logger.info("Converted old credits into wallet money for %d reseller(s).", migrated)


def init_db() -> None:
    """Create tables, apply light migrations, seed demo data on first run."""
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    db = SessionLocal()
    try:
        if db.query(Product).count() == 0:
            seed_data(db)
            logger.info("Seeded demo products, links and resellers.")
        _migrate_credits_to_wallet(db)
    finally:
        db.close()


def seed_data(db) -> None:
    """Demo catalogue so the app is usable immediately. Replace via the admin dashboard."""
    db.merge(SystemSettings(
        id=1,
        business_name="AI Digital Vending Hub",
        admin_upi_id=Config.ADMIN_UPI_ID,
        admin_upi_name=Config.ADMIN_UPI_NAME,
        reseller_credit_rate_inr=Config.RESELLER_CREDIT_RATE_INR,
        reseller_terms=(
            "🌟 *Reseller Pricing & Rules*:\n"
            "• 1 Credit = 1 Digital Product Invite Link\n"
            "• 10 Credits Pack = ₹1,500\n"
            "• 50 Credits Pack = ₹6,500 (Save ₹1,000!)\n"
            "• 100 Credits Pack = ₹12,000 (VIP Reseller Rate)\n\n"
            f"To purchase credits, pay via UPI to `{Config.ADMIN_UPI_ID}` and share the payment screenshot with Admin."
        ),
        evolution_api_url=Config.EVOLUTION_API_URL,
        evolution_api_key=Config.EVOLUTION_API_KEY,
        evolution_instance_name=Config.EVOLUTION_INSTANCE_NAME,
        openai_model_name=Config.OPENAI_MODEL_NAME,
    ))

    products = [
        Product(name="Gemini Advanced (1-Year Invite Link)", slug="gemini-advanced-1y", category="AI Models",
                description="Google One AI Premium 2TB cloud storage + Gemini Pro/Ultra access. Full 1-year private family invite link.",
                base_price=450.0, margin_percent=40.0, credit_cost=1),
        Product(name="Claude Pro (Private Organization Invite)", slug="claude-pro-invite", category="AI Models",
                description="Claude Sonnet & Opus access with Artifacts and Projects workspace.",
                base_price=600.0, margin_percent=35.0, credit_cost=1),
        Product(name="ChatGPT Plus (1-Month Workspace Seat)", slug="chatgpt-plus-1m", category="AI Models",
                description="GPT-4o, o1 reasoning model, DALL-E 3 image generation, and custom GPTs access.",
                base_price=350.0, margin_percent=45.0, credit_cost=1),
        Product(name="Canva Pro (Lifetime Edu Invite)", slug="canva-pro-lifetime", category="Design Tools",
                description="Full access to 100M+ premium assets, magic AI resize, background remover, and brand kit.",
                base_price=100.0, margin_percent=100.0, credit_cost=1),
        Product(name="Office 365 (5-Device Enterprise Account)", slug="office-365-5devices", category="Productivity",
                description="Word, Excel, PowerPoint, Outlook + 5TB OneDrive storage for 5 devices.",
                base_price=200.0, margin_percent=50.0, credit_cost=1),
    ]
    db.add_all(products)
    db.commit()
    p1, p2, p3, p4, p5 = products

    links_data = [
        (p1.id, "https://families.google.com/join/invite?token=GM_ADV_9921_XKL89"),
        (p1.id, "https://families.google.com/join/invite?token=GM_ADV_3381_QPZ44"),
        (p1.id, "https://families.google.com/join/invite?token=GM_ADV_7720_MNB12"),
        (p2.id, "https://claude.ai/invite/org_8921_sonnet_vip_pass"),
        (p2.id, "https://claude.ai/invite/org_4412_sonnet_fast_access"),
        (p3.id, "https://chatgpt.com/workspace/invite/tok_cgpt_4o_tier1"),
        (p3.id, "https://chatgpt.com/workspace/invite/tok_cgpt_4o_tier2"),
        (p4.id, "https://www.canva.com/brand/join?token=CANVA_PRO_LIFETIME_EDU_89"),
        (p4.id, "https://www.canva.com/brand/join?token=CANVA_PRO_LIFETIME_EDU_90"),
        (p5.id, "OFFICE365-USER: vip_user_891@cloudms.org | PASS: Win365#Pass2026"),
    ]
    for pid, lk in links_data:
        db.add(InviteLink(product_id=pid, link_or_key=lk, status="available"))

    resellers = [
        Reseller(name="Rahul Sharma (Verified Reseller)", phone="9876543210", secret_code="1234", notes="Top Tier Reseller - Delhi Region"),
        Reseller(name="Amit Patel (Reseller Pro)", phone="9123456780", secret_code="8899", notes="Mumbai Reseller Partner"),
        Reseller(name="Pooja Verma (Tech Store)", phone="9988776655", secret_code="4321", notes="New Reseller Account"),
    ]
    db.add_all(resellers)
    db.commit()

    # Money wallets: each link costs the product's reseller price (defaults to base price).
    r1, r2, r3 = resellers
    for reseller, amount in ((r1, 5000.0), (r2, 2000.0), (r3, 500.0)):
        adjust_reseller_wallet(db, reseller, amount, reason="admin_topup", note="Initial onboarding top-up")
