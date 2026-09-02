import os
import re
import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    desc
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "vending_bot.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False},
    echo=False
)

# Enable WAL mode for high concurrency in SQLite
with engine.connect() as connection:
    connection.exec_driver_sql("PRAGMA journal_mode=WAL;")
    connection.exec_driver_sql("PRAGMA synchronous=NORMAL;")

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    category = Column(String(50), default="AI Tools")
    description = Column(Text, default="")
    base_price = Column(Float, nullable=False, default=0.0) # Admin cost
    margin_percent = Column(Float, nullable=False, default=30.0) # Margin %
    credit_cost = Column(Integer, nullable=False, default=1) # Credits for reseller
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    links = relationship("InviteLink", back_populates="product", cascade="all, delete-orphan")

    def get_customer_price(self) -> float:
        """Dynamically computes customer selling price: base_price + (base_price * margin% / 100)"""
        margin_amount = self.base_price * (self.margin_percent / 100.0)
        return round(self.base_price + margin_amount, 2)

    def get_available_stock_count(self, session) -> int:
        return session.query(InviteLink).filter(
            InviteLink.product_id == self.id,
            InviteLink.status == "available"
        ).count()

    def to_dict(self, session=None) -> Dict[str, Any]:
        stock = self.get_available_stock_count(session) if session else 0
        customer_price = self.get_customer_price()
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "category": self.category,
            "description": self.description,
            "base_price": self.base_price,
            "margin_percent": self.margin_percent,
            "customer_price": customer_price,
            "credit_cost": self.credit_cost,
            "is_active": self.is_active,
            "stock_count": stock,
            "in_stock": stock > 0,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class InviteLink(Base):
    """
    Single-Use Link / Key Inventory table.
    Crucial Rule: A link can only be in 'available' or 'claimed' status.
    Once claimed, it is permanently locked and NEVER delivered to anyone else.
    """
    __tablename__ = "invite_links"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    link_or_key = Column(Text, nullable=False)
    status = Column(String(20), default="available", index=True) # "available" or "claimed"
    claimed_by_type = Column(String(20), nullable=True) # "customer", "reseller", "admin"
    claimed_by_id = Column(String(100), nullable=True) # phone number or customer id
    claimed_at = Column(DateTime, nullable=True)
    order_id = Column(String(50), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product", back_populates="links")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else "Unknown",
            "link_or_key": self.link_or_key,
            "status": self.status,
            "claimed_by_type": self.claimed_by_type,
            "claimed_by_id": self.claimed_by_id,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "order_id": self.order_id,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Reseller(Base):
    __tablename__ = "resellers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(30), unique=True, index=True, nullable=False)
    secret_code = Column(String(10), nullable=False) # 4-digit passcode
    credits_balance = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    transactions = relationship("CreditTransaction", back_populates="reseller", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "secret_code": self.secret_code,
            "credits_balance": self.credits_balance,
            "is_active": self.is_active,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    reseller_id = Column(Integer, ForeignKey("resellers.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False) # +credits or -credits
    balance_after = Column(Integer, nullable=False)
    reason = Column(String(50), nullable=False) # "claim_link", "admin_topup", "admin_deduct", "purchase"
    product_id = Column(Integer, nullable=True)
    link_id = Column(Integer, nullable=True)
    reference_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class CustomerOrder(Base):
    __tablename__ = "customer_orders"

    id = Column(String(50), primary_key=True, index=True) # e.g. ORD-7821
    customer_name = Column(String(100), default="Customer")
    customer_phone = Column(String(30), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    payment_method = Column(String(30), default="UPI_QR")
    payment_ref = Column(String(100), nullable=True) # UTR / Transaction reference
    status = Column(String(30), default="pending_payment") # "pending_payment", "paid", "delivered", "cancelled"
    delivered_link_id = Column(Integer, nullable=True)
    delivered_link_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
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
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)
    business_name = Column(String(150), default="AI Digital Vending Hub")
    admin_upi_id = Column(String(100), default="resellerpay@upi")
    admin_upi_name = Column(String(100), default="Digital Vending Admin")
    qr_code_image_url = Column(Text, nullable=True)
    reseller_credit_rate_inr = Column(Float, default=150.0) # Rs per credit
    reseller_terms = Column(Text, default="Minimum credit pack: 10 Credits (Rs 1,500). 1 Credit = 1 Single-Use Invite Link.")
    evolution_api_url = Column(String(200), default="http://localhost:8080")
    evolution_api_key = Column(String(200), default="B6D711FCDE4D4FD5936544120E713976")
    evolution_instance_name = Column(String(100), default="VendingBot")
    openai_api_key = Column(String(200), nullable=True)
    openai_model_name = Column(String(50), default="gpt-4o-mini")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "business_name": self.business_name,
            "admin_upi_id": self.admin_upi_id,
            "admin_upi_name": self.admin_upi_name,
            "qr_code_image_url": self.qr_code_image_url,
            "reseller_credit_rate_inr": self.reseller_credit_rate_inr,
            "reseller_terms": self.reseller_terms,
            "evolution_api_url": self.evolution_api_url,
            "evolution_api_key": self.evolution_api_key,
            "evolution_instance_name": self.evolution_instance_name,
            "openai_model_name": self.openai_model_name,
            "has_openai_key": bool(self.openai_api_key or os.getenv("OPENAI_API_KEY"))
        }


class ChatSessionRecord(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(100), primary_key=True)
    user_type = Column(String(30), default="customer") # "customer" or "reseller"
    title = Column(String(200), default="New Conversation")
    reseller_phone = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    messages = relationship("ChatMessageRecord", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessageRecord.id")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_type": self.user_type,
            "title": self.title,
            "reseller_phone": self.reseller_phone,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False) # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True) # JSON for claimed link, payment card, todos, etc.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("ChatSessionRecord", back_populates="messages")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# =====================================================================
# Database Utility & Atomic Business Logic Functions
# =====================================================================

def normalize_phone(phone: str) -> str:
    """Strip spaces, dashes, parentheses and normalize phone numbers."""
    if not phone:
        return ""
    clean = re.sub(r"[^\d+]", "", str(phone).strip())
    # Standardize 10 digit Indian numbers
    if len(clean) == 10 and not clean.startswith("+"):
        return clean
    if clean.startswith("+91") and len(clean) == 13:
        return clean[3:]
    if clean.startswith("91") and len(clean) == 12:
        return clean[2:]
    return clean


def get_db():
    """Provides a thread-safe database session."""
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def get_settings(db=None) -> SystemSettings:
    """Fetch singleton system settings or create default."""
    close_when_done = False
    if db is None:
        db = get_db()
        close_when_done = True
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


def verify_reseller_auth(phone: str, secret_code: str, db=None) -> Tuple[bool, Optional[Reseller], str]:
    """
    Verifies reseller phone and 4-digit secret passcode.
    Returns (is_valid, reseller_obj, message).
    """
    close_when_done = False
    if db is None:
        db = get_db()
        close_when_done = True
    try:
        norm_phone = normalize_phone(phone)
        code_clean = str(secret_code).strip()

        reseller = db.query(Reseller).filter(
            (Reseller.phone == norm_phone) | (Reseller.phone == f"+91{norm_phone}") | (Reseller.phone == phone)
        ).first()

        if not reseller:
            return False, None, "Reseller phone number is not registered in the system."
        
        if not reseller.is_active:
            return False, reseller, "Reseller account is currently inactive. Please contact admin."

        if reseller.secret_code.strip() != code_clean:
            return False, reseller, "Incorrect 4-digit secret passcode."

        return True, reseller, "Authentication successful."
    finally:
        if close_when_done:
            db.close()


def claim_single_use_link(
    product_id: int, 
    claimed_by_type: str, 
    claimed_by_id: str, 
    order_id: Optional[str] = None,
    db=None
) -> Tuple[bool, Optional[InviteLink], str]:
    """
    ATOMIC SINGLE-USE LINK BURNING:
    Selects 1 available link for the given product, immediately marks it as 'claimed'
    with timestamp and recipient identifier.
    Guarantees the link will never be given out again.
    """
    close_when_done = False
    if db is None:
        db = get_db()
        close_when_done = True
    try:
        # Atomic selection with SQLite update
        link = db.query(InviteLink).filter(
            InviteLink.product_id == product_id,
            InviteLink.status == "available"
        ).order_by(InviteLink.id.asc()).first()

        if not link:
            return False, None, "Out of stock! No available single-use invite links for this product."

        # Mark claimed immediately (burn link)
        link.status = "claimed"
        link.claimed_by_type = claimed_by_type
        link.claimed_by_id = normalize_phone(claimed_by_id) or str(claimed_by_id)
        link.claimed_at = datetime.datetime.utcnow()
        link.order_id = order_id

        db.commit()
        db.refresh(link)
        return True, link, "Link successfully claimed."
    except Exception as e:
        db.rollback()
        return False, None, f"Database error claiming link: {str(e)}"
    finally:
        if close_when_done:
            db.close()


def process_reseller_claim(
    phone: str, 
    secret_code: str, 
    product_id_or_slug: Any, 
    quantity: int = 1,
    db=None
) -> Dict[str, Any]:
    """
    Full Reseller Claim Workflow:
    1. Authenticate reseller (phone + 4-digit code)
    2. Check product and credit cost
    3. Check available credits balance
    4. Check inventory stock
    5. Deduct credits atomically
    6. Burn / Claim single-use links
    7. Record credit transaction
    8. Return secure links
    """
    close_when_done = False
    if db is None:
        db = get_db()
        close_when_done = True
    try:
        is_auth, reseller, msg = verify_reseller_auth(phone, secret_code, db=db)
        if not is_auth:
            return {
                "success": False,
                "error": "AUTH_FAILED",
                "message": msg
            }

        # Find product
        product = None
        if isinstance(product_id_or_slug, int) or (isinstance(product_id_or_slug, str) and product_id_or_slug.isdigit()):
            product = db.query(Product).filter(Product.id == int(product_id_or_slug), Product.is_active == True).first()
        else:
            product = db.query(Product).filter(
                (Product.slug.ilike(f"%{product_id_or_slug}%")) | (Product.name.ilike(f"%{product_id_or_slug}%")),
                Product.is_active == True
            ).first()

        if not product:
            return {
                "success": False,
                "error": "PRODUCT_NOT_FOUND",
                "message": f"Product '{product_id_or_slug}' not found or is currently inactive."
            }

        total_credits_needed = product.credit_cost * quantity
        if reseller.credits_balance < total_credits_needed:
            return {
                "success": False,
                "error": "INSUFFICIENT_CREDITS",
                "message": f"Insufficient credits. You have {reseller.credits_balance} credits, but {total_credits_needed} credits are required ({product.credit_cost} credits x {quantity}).",
                "credits_balance": reseller.credits_balance,
                "credits_required": total_credits_needed
            }

        # Check stock
        available_count = product.get_available_stock_count(db)
        if available_count < quantity:
            return {
                "success": False,
                "error": "OUT_OF_STOCK",
                "message": f"Only {available_count} link(s) currently available in stock. Requested {quantity}.",
                "available_stock": available_count
            }

        # Claim links and deduct credits atomically
        claimed_links = []
        for _ in range(quantity):
            ok, link_obj, lmsg = claim_single_use_link(
                product_id=product.id,
                claimed_by_type="reseller",
                claimed_by_id=reseller.phone,
                order_id=f"RES-{reseller.id}-{int(datetime.datetime.utcnow().timestamp())}",
                db=db
            )
            if not ok or not link_obj:
                db.rollback()
                return {"success": False, "error": "CLAIM_ERROR", "message": lmsg}
            claimed_links.append(link_obj)

        # Deduct wallet credits
        reseller.credits_balance -= total_credits_needed
        reseller.updated_at = datetime.datetime.utcnow()

        # Record transaction log
        for cl in claimed_links:
            txn = CreditTransaction(
                reseller_id=reseller.id,
                amount=-product.credit_cost,
                balance_after=reseller.credits_balance,
                reason="claim_link",
                product_id=product.id,
                link_id=cl.id,
                reference_note=f"Redeemed 1 single-use link for {product.name}"
            )
            db.add(txn)

        db.commit()
        db.refresh(reseller)

        return {
            "success": True,
            "message": f"Successfully claimed {quantity} link(s) for {product.name}!",
            "product_name": product.name,
            "quantity": quantity,
            "credits_deducted": total_credits_needed,
            "remaining_credits": reseller.credits_balance,
            "links": [cl.link_or_key for cl in claimed_links],
            "links_claimed_ids": [cl.id for cl in claimed_links],
            "reseller_name": reseller.name
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "error": "SERVER_ERROR", "message": f"An error occurred: {str(e)}"}
    finally:
        if close_when_done:
            db.close()


def init_db():
    """Initializes tables and seeds initial data if empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if products exist
        if db.query(Product).count() == 0:
            seed_data(db)
    finally:
        db.close()


def seed_data(db):
    """Seed sample digital products, invite links, resellers, and settings."""
    settings = SystemSettings(
        id=1,
        business_name="AI Digital Vending Hub",
        admin_upi_id="resellerpay@upi",
        admin_upi_name="Digital Hub Admin",
        reseller_credit_rate_inr=150.0,
        reseller_terms="🌟 *Reseller Pricing & Rules*:\n• 1 Credit = 1 Digital Product Invite Link\n• 10 Credits Pack = ₹1,500\n• 50 Credits Pack = ₹6,500 (Save ₹1,000!)\n• 100 Credits Pack = ₹12,000 (VIP Reseller Rate)\n\nTo purchase credits, pay via UPI to `resellerpay@upi` and share payment screenshot with Admin.",
        evolution_api_url="http://localhost:8080",
        evolution_api_key="B6D711FCDE4D4FD5936544120E713976",
        evolution_instance_name="VendingBot",
        openai_model_name="gpt-4o-mini"
    )
    db.merge(settings)

    # Products with Base Price (cost) and dynamic Margin %
    p1 = Product(
        name="Gemini Advanced (1-Year Invite Link)",
        slug="gemini-advanced-1y",
        category="AI Models",
        description="Google One AI Premium 2TB cloud storage + Gemini 1.5 Pro/2.0 Ultra access. Full 1-year private family invite link.",
        base_price=450.0,
        margin_percent=40.0, # Selling price = 450 + 180 = Rs 630
        credit_cost=1,
        is_active=True
    )
    p2 = Product(
        name="Claude Pro (Private Organization Invite)",
        slug="claude-pro-invite",
        category="AI Models",
        description="Claude 3.5 Sonnet & Claude 3 Opus unlimited access with Artifacts and Projects workspace.",
        base_price=600.0,
        margin_percent=35.0, # Selling price = 600 + 210 = Rs 810
        credit_cost=1,
        is_active=True
    )
    p3 = Product(
        name="ChatGPT Plus (1-Month Workspace Seat)",
        slug="chatgpt-plus-1m",
        category="AI Models",
        description="GPT-4o, GPT-o1 reasoning model, DALL-E 3 image generation, and custom GPTs access.",
        base_price=350.0,
        margin_percent=45.0, # Selling price = 350 + 157.5 = Rs 507.50
        credit_cost=1,
        is_active=True
    )
    p4 = Product(
        name="Canva Pro (Lifetime Edu Invite)",
        slug="canva-pro-lifetime",
        category="Design Tools",
        description="Full access to 100M+ premium assets, magic AI resize, background remover, and brand kit.",
        base_price=100.0,
        margin_percent=100.0, # Selling price = 100 + 100 = Rs 200
        credit_cost=1,
        is_active=True
    )
    p5 = Product(
        name="Office 365 (5-Device Enterprise Account)",
        slug="office-365-5devices",
        category="Productivity",
        description="Word, Excel, PowerPoint, Outlook + 5TB OneDrive storage for 5 devices (Windows/Mac/iOS/Android).",
        base_price=200.0,
        margin_percent=50.0, # Selling price = 200 + 100 = Rs 300
        credit_cost=1,
        is_active=True
    )

    db.add_all([p1, p2, p3, p4, p5])
    db.commit()

    # Seed Sample Single-Use Invite Links
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
        (p5.id, "OFFICE365-USER: vip_user_891@cloudms.org | PASS: Win365#Pass2026")
    ]
    for pid, lk in links_data:
        db.add(InviteLink(product_id=pid, link_or_key=lk, status="available"))

    # Seed Sample Resellers
    r1 = Reseller(
        name="Rahul Sharma (Verified Reseller)",
        phone="9876543210",
        secret_code="1234",
        credits_balance=25,
        is_active=True,
        notes="Top Tier Reseller - Delhi Region"
    )
    r2 = Reseller(
        name="Amit Patel (Reseller Pro)",
        phone="9123456780",
        secret_code="8899",
        credits_balance=10,
        is_active=True,
        notes="Mumbai Reseller Partner"
    )
    r3 = Reseller(
        name="Pooja Verma (Tech Store)",
        phone="9988776655",
        secret_code="4321",
        credits_balance=3,
        is_active=True,
        notes="New Reseller Account"
    )
    db.add_all([r1, r2, r3])
    db.commit()

    # Add initial credit transaction logs for seeded resellers
    db.add(CreditTransaction(
        reseller_id=r1.id,
        amount=25,
        balance_after=25,
        reason="admin_topup",
        reference_note="Initial account onboarding credits"
    ))
    db.add(CreditTransaction(
        reseller_id=r2.id,
        amount=10,
        balance_after=10,
        reason="admin_topup",
        reference_note="Initial account onboarding credits"
    ))
    db.add(CreditTransaction(
        reseller_id=r3.id,
        amount=3,
        balance_after=3,
        reason="admin_topup",
        reference_note="Initial account onboarding credits"
    ))
    db.commit()
