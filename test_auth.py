import pytest
import uuid
import json
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

from app.database import Base, get_db
from main import app
from app.models import Business, User
from app.core.config import settings
from app.core.security import decrypt_token

# 1. Setup a temporary SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 2. Dependency override to use the test database
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    """Create and drop tables for each test run."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

# --- REGISTRATION & LOGIN TESTS ---

def test_register_new_business():
    """Checks successful registration."""
    payload = {
        "business_name": "Test Company",
        "owner_email": "test@example.com",
        "password": "securepassword123"
    }
    response = client.post("/auth/register", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "business_id" in data
    assert data["status"] == "ready for meta signup"

def test_login_success():
    """Tests successful login and JWT generation."""
    email = "login_test@example.com"
    password = "testpassword123"
    client.post("/auth/register", json={
        "business_name": "Login Test Biz",
        "owner_email": email,
        "password": password
    })

    login_payload = {"username": email, "password": password}
    response = client.post("/auth/login", data=login_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    
    # Verify multi-tenancy claims in JWT
    token = data["access_token"]
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == email
    assert "business_id" in payload

# --- META OAUTH EXCHANGE TESTS ---

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
@patch("httpx.AsyncClient.post")
async def test_meta_callback_success(mock_post, mock_get):
    """
    Tests Step 7: Successful code exchange, encryption, and webhook subscription.
    Ensures that .json() returns a dict, not a coroutine.
    """
    # 1. Register a business to get a real ID
    reg_res = client.post("/auth/register", json={
        "business_name": "Meta Test Biz",
        "owner_email": "meta@example.com",
        "password": "password123"
    })
    biz_id = reg_res.json()["business_id"]

    # 2. Setup Mocks for Meta API
    # Mock Token Exchange Response
    mock_token_resp = AsyncMock()
    mock_token_resp.status_code = 200
    # Use MagicMock for .json() so it returns a dict immediately
    mock_token_resp.json = MagicMock(return_value={
        "access_token": "EAAG_FAKE_TOKEN_123",
        "whatsapp_business_account_id": "WABA_ID_999"
    })

    # Mock Phone Number Fetch Response
    mock_phone_resp = AsyncMock()
    mock_phone_resp.status_code = 200
    mock_phone_resp.json = MagicMock(return_value={
        "data": [{"id": "PHONE_ID_555"}]
    })

    # Mock Webhook Subscription Response
    mock_sub_resp = AsyncMock()
    mock_sub_resp.status_code = 200

    # Assign side effects to the mocks
    mock_get.side_effect = [mock_token_resp, mock_phone_resp]
    mock_post.return_value = mock_sub_resp

    # 3. Trigger Callback
    callback_payload = {"code": "meta_auth_code_from_frontend"}
    response = client.post(f"/auth/meta-callback/{biz_id}", json=callback_payload)

    # 4. Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["waba_id"] == "WABA_ID_999"

    # 5. Verify Database Encryption and multi-tenancy
    db = TestingSessionLocal()
    biz = db.query(Business).filter(Business.id == biz_id).first()
    assert biz.waba_id == "WABA_ID_999"
    assert biz.phone_number_id == "PHONE_ID_555"
    
    # Verify sensitive token is encrypted
    decrypted = decrypt_token(biz.meta_access_token)
    assert decrypted == "EAAG_FAKE_TOKEN_123"
    db.close()

def test_meta_callback_invalid_code():
    """Ensures failure if Meta rejects the code."""
    reg_res = client.post("/auth/register", json={
        "business_name": "Fail Biz",
        "owner_email": "fail@example.com",
        "password": "password123"
    })
    biz_id = reg_res.json()["business_id"]

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_resp.text = "Error validating verification code"
        mock_get.return_value = mock_resp

        response = client.post(f"/auth/meta-callback/{biz_id}", json={"code": "bad_code"})
        
        assert response.status_code == 400
        assert "Meta code exchange failed" in response.json()["detail"]

def test_meta_callback_business_not_found():
    """Checks behavior with non-existent business UUID."""
    fake_id = uuid.uuid4() 
    response = client.post(f"/auth/meta-callback/{fake_id}", json={"code": "test_code"})
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Business record not found"