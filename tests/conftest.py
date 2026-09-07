"""
Test bootstrap: point the app at a throw-away SQLite file *before* importing it,
so the module-level engine in `database.py` never touches the real database.
"""
import os
import sys
import tempfile
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmpdir = tempfile.mkdtemp(prefix="vending_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{pathlib.Path(_tmpdir, 'test.db').as_posix()}"
os.environ["ADMIN_API_KEY"] = "test-admin-key-0123456789"
os.environ["APP_ENV"] = "development"
os.environ["OPENAI_API_KEY"] = ""          # force the rule-based engine in tests
os.environ["AGENT_WORKSPACE_DIR"] = str(pathlib.Path(_tmpdir, "ws"))
os.environ["RATE_LIMIT_CHAT_PER_MIN"] = "0"  # disabled
os.environ["RATE_LIMIT_ADMIN_LOGIN_PER_MIN"] = "0"
os.environ["RESELLER_MAX_FAILED_ATTEMPTS"] = "3"
os.environ["RESELLER_LOCKOUT_MINUTES"] = "15"

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
import database as dbm  # noqa: E402

ADMIN = {"X-Admin-Token": os.environ["ADMIN_API_KEY"]}


@pytest.fixture(scope="session")
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db():
    session = dbm.get_db()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def admin_headers():
    return dict(ADMIN)


@pytest.fixture()
def client_headers():
    return {"X-Client-Id": "web_pytest_client_001"}


@pytest.fixture()
def fresh_product(db):
    """A product with 3 fresh links, isolated per test."""
    import uuid
    # Name deliberately avoids generic words ("product", "test") that the rule engine keys on.
    slug = f"zephyr-suite-{uuid.uuid4().hex[:8]}"
    # reseller_price=100 -> a ₹500 wallet buys exactly 5 links
    product = dbm.Product(name=f"Zephyr Suite {slug}", slug=slug, base_price=100.0, margin_percent=50.0, reseller_price=100.0)
    db.add(product)
    db.commit()
    for i in range(3):
        db.add(dbm.InviteLink(product_id=product.id, link_or_key=f"https://example.com/{slug}/{i}", status="available"))
    db.commit()
    db.refresh(product)
    return product


@pytest.fixture()
def fresh_reseller(db, fresh_product):
    """A reseller with a ₹500 INR wallet (= 5 links of `fresh_product` at ₹100 each)."""
    import uuid
    phone = "7" + uuid.uuid4().int.__str__()[:9]
    reseller = dbm.Reseller(name="Test Reseller", phone=phone, secret_code="4321", currency="INR")
    db.add(reseller)
    db.commit()
    db.refresh(reseller)
    dbm.adjust_reseller_wallet(db, reseller, 500.0, reason="admin_topup", note="test grant")
    db.refresh(reseller)
    return reseller
