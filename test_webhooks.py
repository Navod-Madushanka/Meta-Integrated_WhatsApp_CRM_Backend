import pytest
import hmac
import hashlib
import json
import time
from fastapi.testclient import TestClient
from main import app 
from app.core.config import settings
from app.database import SessionLocal, Base, engine
from app.models import Message, Business, Contact

client = TestClient(app)

# --- Helper: Generate Meta-style Signature ---
def generate_signature(payload_bytes: bytes):
    """Generates the X-Hub-Signature-256 header needed to pass verify_signature."""
    mac = hmac.new(
        settings.META_CLIENT_SECRET.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    )
    return f"sha256={mac.hexdigest()}"

# --- DATABASE SETUP FOR TESTING ---
@pytest.fixture(autouse=True)
def setup_db():
    """Initializes a clean test database before each test and cleans up after."""
    # 1. Clean up existing tables to ensure a fresh state (Fixes UniqueViolation)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    # 2. Seed required dummy business data
    test_biz = Business(
        name="Test Biz",
        owner_email="test@example.com",
        meta_access_token="fake_token",
        waba_id="fake_waba",
        phone_number_id="YOUR_PHONE_ID"
    )
    db.add(test_biz)
    db.commit()
    db.close()
    
    yield
    # Optional: cleanup after tests
    # Base.metadata.drop_all(bind=engine)

# --- 1. Test Webhook Verification (GET) ---
def test_verify_webhook_success():
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": settings.META_WEBHOOK_VERIFY_TOKEN,
        "hub.challenge": "123456789"
    }
    response = client.get("/webhooks", params=params)
    assert response.status_code == 200
    assert response.text == "123456789"

# --- 2. Test Automated STOP Opt-out ---
def test_handle_stop_opt_out():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "YOUR_PHONE_ID"},
                    "messages": [{
                        "from": "15551234567",
                        "id": "wamid.OPT_OUT_1",
                        "text": {"body": "STOP"},
                        "type": "text"
                    }]
                },
                "change_field": "messages"
            }]
        }]
    }
    body_bytes = json.dumps(payload).encode('utf-8')
    headers = {"X-Hub-Signature-256": generate_signature(body_bytes)}
    
    response = client.post("/webhooks", content=body_bytes, headers=headers)
    assert response.status_code == 200

    time.sleep(0.2)
    
    db = SessionLocal()
    contact = db.query(Contact).filter(Contact.phone_number == "15551234567").first()
    assert contact is not None
    assert contact.status == "Opt-out"
    db.close()

# --- 3. Test Idempotency (Duplicate Prevention) ---
def test_webhook_idempotency():
    unique_wamid = "wamid.IDEMPOTENCY_999"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "YOUR_PHONE_ID"},
                    "messages": [{
                        "from": "15550008888",
                        "id": unique_wamid,
                        "text": {"body": "Idempotency Test"},
                        "type": "text"
                    }]
                },
                "change_field": "messages"
            }]
        }]
    }
    
    body_bytes = json.dumps(payload).encode('utf-8')
    headers = {"X-Hub-Signature-256": generate_signature(body_bytes)}
    
    client.post("/webhooks", content=body_bytes, headers=headers)
    client.post("/webhooks", content=body_bytes, headers=headers)
    
    time.sleep(0.2)
    
    db = SessionLocal()
    message_count = db.query(Message).filter(Message.meta_message_id == unique_wamid).count()
    db.close()
    assert message_count == 1

# --- 4. Test Status Update Sync ---
def test_webhook_status_update():
    db = SessionLocal()
    biz = db.query(Business).filter(Business.phone_number_id == "YOUR_PHONE_ID").one()
    
    # Check if contact exists to prevent UniqueViolation
    test_contact = db.query(Contact).filter(
        Contact.business_id == biz.id, 
        Contact.phone_number == "15550009999"
    ).first()

    if not test_contact:
        test_contact = Contact(
            business_id=biz.id,
            phone_number="15550009999",
            name="Status Test User"
        )
        db.add(test_contact)
        db.flush() 

    # Create the original message record
    test_msg = Message(
        business_id=biz.id,
        contact_id=test_contact.id,
        direction="Out",
        status="Sent",
        meta_message_id="wamid.STATUS_TEST_001"
    )
    db.add(test_msg)
    db.commit()

    # Meta Status Update Payload
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "statuses": [{
                        "id": "wamid.STATUS_TEST_001",
                        "status": "read",
                        "timestamp": "1600000000",
                        "recipient_id": "15550009999"
                    }]
                },
                "change_field": "messages"
            }]
        }]
    }
    
    body_bytes = json.dumps(payload).encode('utf-8')
    headers = {"X-Hub-Signature-256": generate_signature(body_bytes)}
    client.post("/webhooks", content=body_bytes, headers=headers)

    time.sleep(0.2) 

    db.refresh(test_msg)
    assert test_msg.status == "Read" 
    db.close()