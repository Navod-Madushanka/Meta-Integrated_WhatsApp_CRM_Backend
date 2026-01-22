import redis
import httpx
import logging
import time
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models import Campaign, Contact, Message, Business
from app.core.security import decrypt_token
from app.core.config import settings

logger = logging.getLogger("celery.worker")

redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
redis_client = redis.Redis(connection_pool=redis_pool)

TIER_THROUGHPUT = {
    "TIER_250": 5, "TIER_1K": 20, "TIER_10K": 50, "TIER_UNLIMITED": 80
}

def get_quota_key(business_id: str):
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return f"quota:{business_id}:{date_str}"

@celery_app.task(name="send_bulk_campaign_task", bind=True, max_retries=3)
def send_bulk_campaign(self, campaign_id: str, business_id: str):
    db: Session = SessionLocal()
    quota_key = get_quota_key(business_id)
    
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        business = db.query(Business).filter(Business.id == business_id).first()
        
        if not campaign or not business:
            return "FAILURE: Missing Entities"

        campaign.status = "Running"
        campaign.started_at = datetime.utcnow()
        db.commit()

        token = decrypt_token(business.meta_access_token)
        tier = business.messaging_tier or "TIER_250"
        delay = 1.0 / TIER_THROUGHPUT.get(tier, 5)

        # --- UPDATED CONTACT FETCHING ---
        # Strictly exclude anyone with 'Opt-out' or 'Blacklisted' status
        query = db.query(Contact).filter(
            Contact.business_id == business_id, 
            Contact.status == "Active" # CRITICAL CHANGE
        )
        if campaign.contact_group_id:
            query = query.filter(Contact.groups.any(id=campaign.contact_group_id))
        contacts = query.all()
        
        sent_count = campaign.total_sent or 0
        failed_count = campaign.total_failed or 0
        meta_url = f"https://graph.facebook.com/{settings.META_APP_VERSION}/{business.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {token}"}

        with httpx.Client(timeout=15.0) as client:
            for contact in contacts:
                # Double-check status inside the loop in case they opted out 
                # while the worker was already running for a large list.
                db.refresh(contact)
                if contact.status != "Active":
                    logger.info(f"Skipping contact {contact.phone_number} - Status: {contact.status}")
                    continue

                exists = db.query(Message).filter_by(campaign_id=campaign_id, contact_id=contact.id).first()
                if exists: continue

                current_usage = redis_client.incr(quota_key)
                if current_usage == 1:
                    redis_client.expire(quota_key, 90000)

                if current_usage > business.daily_quota:
                    campaign.status = "Paused"
                    campaign.status_reason = f"Quota reached."
                    db.commit()
                    return f"PAUSED: Quota reached."

                payload = {
                    "messaging_product": "whatsapp",
                    "to": contact.phone_number,
                    "type": "template",
                    "template": {
                        "name": campaign.template.name,
                        "language": {"code": campaign.template.language or "en_US"},
                        "components": [{
                            "type": "body",
                            "parameters": [{"type": "text", "text": str(contact.name or "Customer")}]
                        }]
                    }
                }

                try:
                    response = client.post(meta_url, json=payload, headers=headers)
                    if response.status_code == 200:
                        res_data = response.json()
                        db.add(Message(
                            business_id=business_id,
                            contact_id=contact.id,
                            campaign_id=campaign_id,
                            meta_message_id=res_data['messages'][0]['id'],
                            status="Sent",
                            direction="Out"
                        ))
                        sent_count += 1
                    elif response.status_code == 429:
                        campaign.status = "Paused"
                        db.commit()
                        return "PAUSED: Meta 429"
                    else:
                        failed_count += 1
                    
                    if sent_count % 10 == 0:
                        db.commit()

                except Exception as e:
                    logger.error(f"Network error: {e}")
                    failed_count += 1

                time.sleep(delay)

        campaign.status = "Completed"
        campaign.completed_at = datetime.utcnow()
        campaign.total_sent = sent_count
        campaign.total_failed = failed_count
        db.commit()
        return f"SUCCESS: {sent_count} sent."

    except Exception as exc:
        db.rollback()
        if campaign:
            campaign.status = "Error"
            db.commit()
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()