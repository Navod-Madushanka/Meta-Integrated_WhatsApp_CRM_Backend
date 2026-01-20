import pytest
import uuid
import json
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from main import app
from app.models import Business, User
from app.core.config import settings
from app.core.security import decrypt_token

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@patch("httpx.AsyncClient.post")
@patch("httpx.AsyncClient.get")
def test_meta_callback_success(mock_get, mock_post):
    # Register business
    reg_res = client.post("/auth/register", json={
        "business_name": "Test SaaS",
        "owner_email": "test@example.com",
        "password": "securepassword123"
    })
    biz_id = reg_res.json()["business_id"]

    # 1. Mock Token Exchange Response
    # We use MagicMock for the response itself, and only AsyncMock for the client call
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "access_token": "EAAG_FAKE_TOKEN_123",
        "whatsapp_business_account_id": "WABA_ID_999"
    }

    # 2. Mock Phone ID Fetch Response
    mock_phone_resp = MagicMock()
    mock_phone_resp.status_code = 200
    mock_phone_resp.json.return_value = {
        "data": [{"id": "PHONE_ID_555"}]
    }
    
    mock_get.side_effect = [mock_token_resp, mock_phone_resp]

    # 3. Mock Webhook Subscription (POST)
    mock_sub_resp = MagicMock()
    mock_sub_resp.status_code = 200
    mock_sub_resp.json.return_value = {"success": True}
    mock_post.return_value = mock_sub_resp

    response = client.post(f"/auth/meta-callback/{biz_id}", json={"code": "valid_meta_code_123"})

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    
    # Verify DB
    db = TestingSessionLocal()
    biz = db.query(Business).filter(Business.id == biz_id).first()
    assert biz.waba_id == "WABA_ID_999"
    assert decrypt_token(biz.meta_access_token) == "EAAG_FAKE_TOKEN_123"
    db.close()

@patch("httpx.AsyncClient.post")
@patch("httpx.AsyncClient.get")
def test_meta_callback_subscription_fails(mock_get, mock_post):
    reg_res = client.post("/auth/register", json={
        "business_name": "Sub Fail Biz",
        "owner_email": "fail-sub@example.com",
        "password": "password123"
    })
    biz_id = reg_res.json()["business_id"]

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "access_token": "TOKEN",
        "whatsapp_business_account_id": "WABA_ID"
    }
    
    mock_phone_resp = MagicMock()
    mock_phone_resp.status_code = 200
    mock_phone_resp.json.return_value = {"data": []}
    
    mock_get.side_effect = [mock_token_resp, mock_phone_resp]

    # Mock FAILED Webhook Subscription
    mock_sub_resp = MagicMock()
    mock_sub_resp.status_code = 400
    mock_sub_resp.text = "Subscription Error"
    mock_post.return_value = mock_sub_resp

    response = client.post(f"/auth/meta-callback/{biz_id}", json={"code": "some_code"})

    assert response.status_code == 424
    assert "Failed to initialize Meta Webhook subscription" in response.json()["detail"]