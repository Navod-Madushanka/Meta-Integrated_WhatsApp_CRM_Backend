import pytest
from fastapi.testclient import TestClient
from main import app  # Adjust based on your main file location
from app.core.config import settings
import hmac
import hashlib
import json

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

# --- 1. Test Webhook Verification (GET) ---
def test_verify_webhook_success():
    """Simulates Meta's initial handshake verification."""
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": settings.META_WEBHOOK_VERIFY_TOKEN,
        "hub.challenge": "123456789"
    }
    response = client.get("/webhooks", params=params)
    assert response.status_code == 200
    assert response.text == "123456789"

def test_verify_webhook_invalid_token():
    """Ensures verification fails with the wrong token."""
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "WRONG_TOKEN",
        "hub.challenge": "123456789"
    }
    response = client.get("/webhooks", params=params)
    assert response.status_code == 403

# --- 2. Test Receiving a Message (POST) ---
def test_handle_incoming_message_success():
    """Simulates receiving a 'Hello' message from a customer."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "12345", "phone_number_id": "PENDING"}, # Matches your default biz
                    "contacts": [{"profile": {"name": "John Doe"}, "wa_id": "15551234567"}],
                    "messages": [{
                        "from": "15551234567",
                        "id": "wamid.HBgLMTU1NTEyMzQ1NjcVAgIAEhggOTY4MUMzQ0Y5RjM0MDhC",
                        "timestamp": "1665010684",
                        "text": {"body": "Hello there!"},
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
    assert response.json() == {"status": "success"}

# --- 3. Test Automated STOP Opt-out ---
def test_handle_stop_opt_out():
    """Simulates a user texting 'STOP' and being opted out automatically."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "PENDING"},
                    "messages": [{
                        "from": "15551234567",
                        "id": "wamid.OPT_OUT_TEST_ID",
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