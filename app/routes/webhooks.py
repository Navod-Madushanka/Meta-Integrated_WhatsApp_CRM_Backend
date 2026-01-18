import logging
import hmac
import hashlib
import json
from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import WebhookLog, Contact, Message, Business
from app.core.config import settings

# Setup logging for production auditing
logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/webhooks", tags=["Meta Webhooks"])

def verify_signature(payload: bytes, signature: str) -> bool:
    """
    Validates that the request actually came from Meta using your App Secret.
    Prevents 'spoofing' where attackers send fake opt-outs[cite: 125].
    """
    if not signature:
        return False
    
    sha_type, signature_hash = signature.split('=') if '=' in signature else (None, None)
    if sha_type != 'sha256':
        return False

    mac = hmac.new(
        settings.META_CLIENT_SECRET.encode('utf-8'), 
        msg=payload, 
        digestmod=hashlib.sha256
    )
    return hmac.compare_digest(mac.hexdigest(), signature_hash)

# 1. WEBHOOK VERIFICATION (GET HANDSHAKE)
@router.get("")
async def verify_meta_webhook(request: Request):
    """
    Meta sends a GET request to verify your endpoint during setup[cite: 112].
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    # Uses the VERIFY_TOKEN you set in the Meta Dashboard
    if mode == "subscribe" and token == settings.META_WEBHOOK_VERIFY_TOKEN:
        logger.info("Webhook Verified Successfully")
        return int(challenge)
    
    logger.warning("Webhook Verification Failed: Invalid Token")
    raise HTTPException(status_code=403, detail="Verification failed")

# 2. EVENT LISTENER (POST DATA)
@router.post("")
async def handle_whatsapp_events(request: Request, db: Session = Depends(get_db)):
    """
    Receives real-time updates: messages, delivery receipts, and opt-outs[cite: 99].
    """
    signature = request.headers.get("X-Hub-Signature-256")
    raw_body = await request.body()
    
    if not verify_signature(raw_body, signature):
        logger.error("Invalid Webhook Signature - Request Rejected")
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(raw_body)

    # AUDIT: Log the raw payload for compliance [cite: 59, 124]
    try:
        new_log = WebhookLog(payload=payload)
        db.add(new_log)
        db.commit() 
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to log webhook: {e}")

    entries = payload.get("entry", [])
    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id")

            # Identify the tenant (Business) [cite: 10, 102]
            biz = db.query(Business).filter(Business.phone_number_id == phone_number_id).first()
            if not biz:
                continue

            # A. HANDLE INCOMING MESSAGES (Compliance & Opt-out) 
            messages = value.get("messages", [])
            for msg in messages:
                try:
                    sender_phone = msg.get("from")
                    text_body = msg.get("text", {}).get("body", "").strip().upper()

                    # Find or create contact to ensure foreign key integrity [cite: 21, 51]
                    contact = db.query(Contact).filter(
                        Contact.phone_number == sender_phone, 
                        Contact.business_id == biz.id
                    ).first()

                    if not contact:
                        contact = Contact(
                            business_id=biz.id,
                            phone_number=sender_phone,
                            name=value.get("contacts", [{}])[0].get("profile", {}).get("name", "Unknown")
                        )
                        db.add(contact)
                        db.flush()

                    # COMPLIANCE: Automated Opt-out Management [cite: 26, 126]
                    if text_body == "STOP":
                        contact.status = "Opt-out"
                        logger.info(f"Contact {sender_phone} opted out for Business {biz.id}")
                    
                    # Store message history [cite: 48, 53]
                    new_msg = Message(
                        business_id=biz.id,
                        contact_id=contact.id,
                        direction="In",
                        status="Delivered",
                        meta_message_id=msg.get("id")
                    )
                    db.add(new_msg)
                except Exception as msg_err:
                    logger.error(f"Error processing message: {msg_err}")

            # B. HANDLE STATUS UPDATES (Sent -> Delivered -> Read) [cite: 53, 123]
            statuses = value.get("statuses", [])
            for stat in statuses:
                try:
                    meta_msg_id = stat.get("id")
                    new_status = stat.get("status")

                    message_record = db.query(Message).filter(
                        Message.meta_message_id == meta_msg_id
                    ).first()
                    
                    if message_record:
                        # Ensures status matches schema (Sent, Delivered, Read) [cite: 53, 103]
                        message_record.status = new_status.capitalize()
                except Exception as stat_err:
                    logger.error(f"Error updating message status: {stat_err}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Final commit failed: {e}")

    return {"status": "success"}