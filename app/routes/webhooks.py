import logging
import hmac
import hashlib
import json
from fastapi import APIRouter, Request, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.models import WebhookLog, Contact, Message, Business
from app.core.config import settings

# Setup logging for production auditing
logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/webhooks", tags=["Meta Webhooks"])

def verify_signature(payload: bytes, signature: str) -> bool:
    """
    Validates that the request actually came from Meta using your App Secret.
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

def process_webhook_payload(payload: dict):
    """
    Background Task: Handles database logic asynchronously.
    Uses its own SessionLocal to avoid session closure errors.
    """
    db = SessionLocal()
    try:
        # 1. Log the raw payload for audit purposes
        new_log = WebhookLog(payload=payload)
        db.add(new_log)
        
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                # A. HANDLE INCOMING MESSAGES
                for msg in value.get("messages", []):
                    try:
                        wamid = msg.get("id")
                        sender_phone = msg.get("from")
                        msg_body = msg.get("text", {}).get("body", "").strip()

                        # --- IDEMPOTENCY CHECK ---
                        # Prevents duplicate entries if Meta retries the webhook
                        existing_msg = db.query(Message).filter(Message.meta_message_id == wamid).first()
                        if existing_msg:
                            logger.info(f"Duplicate message ignored: {wamid}")
                            continue

                        # Identify Business
                        phone_id = value.get("metadata", {}).get("phone_number_id")
                        biz = db.query(Business).filter(Business.phone_number_id == phone_id).first()
                        if not biz:
                            continue

                        # Find or Create Contact
                        contact = db.query(Contact).filter(
                            Contact.business_id == biz.id,
                            Contact.phone_number == sender_phone
                        ).first()

                        if not contact:
                            contact = Contact(business_id=biz.id, phone_number=sender_phone, name="New Contact")
                            db.add(contact)
                            db.flush()

                        # Handle STOP Opt-out
                        if msg_body.upper() == "STOP":
                            contact.status = "Opt-out"
                            logger.info(f"Contact {sender_phone} opted out.")

                        # Store message history
                        new_msg = Message(
                            business_id=biz.id,
                            contact_id=contact.id,
                            direction="In",
                            status="Delivered",
                            meta_message_id=wamid
                        )
                        db.add(new_msg)
                    except Exception as msg_err:
                        logger.error(f"Error processing message: {msg_err}")

                # B. HANDLE STATUS UPDATES (Sent -> Delivered -> Read)
                for stat in value.get("statuses", []):
                    try:
                        meta_msg_id = stat.get("id")
                        new_status = stat.get("status")

                        message_record = db.query(Message).filter(
                            Message.meta_message_id == meta_msg_id
                        ).first()
                        
                        if message_record:
                            message_record.status = new_status.capitalize()
                    except Exception as stat_err:
                        logger.error(f"Error updating message status: {stat_err}")

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Background task failed: {e}")
    finally:
        db.close()

# 1. WEBHOOK VERIFICATION (GET HANDSHAKE)
@router.get("")
async def verify_meta_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == settings.META_WEBHOOK_VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    raise HTTPException(status_code=403, detail="Verification failed")

# 2. WEBHOOK LISTENER (POST PAYLOADS)
@router.post("")
async def handle_whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    # Security Check (Must stay synchronous)
    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)

    # Schedule database work to happen in the background
    background_tasks.add_task(process_webhook_payload, payload)

    # Respond to Meta immediately to prevent timeouts
    return {"status": "success"}