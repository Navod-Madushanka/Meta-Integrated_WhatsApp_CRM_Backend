import logging
from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Campaign, User, Template, ContactGroup
from app import schemas, models
from app.routes.deps import get_current_user
from app.workers.campaign_worker import send_bulk_campaign

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

@router.post("/", response_model=schemas.CampaignOut)
async def create_campaign(
    campaign_in: schemas.CampaignCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Creates a campaign draft in the database.
    Users must select a valid template and (optionally) a contact group.
    """
    # 1. Verify the template exists and belongs to the business
    template = db.query(models.Template).filter(
        models.Template.id == campaign_in.template_id,
        models.Template.business_id == current_user.business_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # 2. Verify contact group if provided
    if campaign_in.contact_group_id:
        group = db.query(models.ContactGroup).filter(
            models.ContactGroup.id == campaign_in.contact_group_id,
            models.ContactGroup.business_id == current_user.business_id
        ).first()
        if not group:
            raise HTTPException(status_code=404, detail="Contact group not found")

    # 3. Create campaign record
    new_campaign = models.Campaign(
        business_id=current_user.business_id,
        name=campaign_in.name,
        template_id=campaign_in.template_id,
        contact_group_id=campaign_in.contact_group_id,
        scheduled_at=campaign_in.scheduled_at,
        status="Draft"
    )
    
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    return new_campaign

@router.post("/{campaign_id}/send")
async def trigger_campaign_send(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Trigger the background worker to start sending messages.
    This moves the process from the API to the Celery/Redis queue.
    """
    campaign = db.query(models.Campaign).filter(
        models.Campaign.id == campaign_id,
        models.Campaign.business_id == current_user.business_id
    ).first()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status == "Sent":
        raise HTTPException(status_code=400, detail="Campaign has already been processed")

    # Update status to indicate it's in the queue
    campaign.status = "Queued"
    db.commit()

    # --- TASK 14 INTEGRATION ---
    # Trigger Celery worker (Passing strings for UUIDs for JSON serialization)
    send_bulk_campaign.delay(str(campaign.id), str(current_user.business_id))

    return {"status": "success", "message": "Bulk send task has been queued."}

@router.get("/", response_model=List[schemas.CampaignOut])
async def list_campaigns(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Fetch all campaigns for the logged-in business."""
    return db.query(models.Campaign).filter(
        models.Campaign.business_id == current_user.business_id
    ).all()