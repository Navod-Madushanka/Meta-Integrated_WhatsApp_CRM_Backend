import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from . import models, schemas, deps
from app.core import security
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/templates", tags=["Templates"])

@router.post("/", response_model=schemas.TemplateOut)
async def create_template(
    template_data: schemas.TemplateCreate, 
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    # 1. Save draft to database with 'Pending' status
    new_template = models.Template(
        business_id=current_user.business_id,
        name=template_data.name,
        # Ensure we store the components list as JSON
        content_json=template_data.model_dump()["components"],
        status="Pending"
    )
    
    try:
        db.add(new_template)
        db.commit()
        db.refresh(new_template)
    except Exception as e:
        db.rollback()
        logger.error(f"Database error saving template draft: {e}")
        raise HTTPException(status_code=500, detail="Failed to save template draft")

    # 2. Retrieve and decrypt Business Access Token
    business = db.query(models.Business).filter(models.Business.id == current_user.business_id).first()
    if not business or business.waba_id == "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Business is not fully onboarded with Meta yet."
        )
    
    decrypted_token = security.decrypt_token(business.meta_access_token)

    # 3. Call Meta's /message_templates API using httpx
    meta_url = f"https://graph.facebook.com/{settings.META_APP_VERSION}/{business.waba_id}/message_templates"
    
    payload = {
        "name": template_data.name,
        "category": template_data.category,
        "language": template_data.language,
        "components": template_data.model_dump()["components"]
    }
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            meta_url, 
            json=payload, 
            headers={"Authorization": f"Bearer {decrypted_token}"}
        )
        
        if response.status_code != 200:
            logger.error(f"Meta Template API Error: {response.text}")
            # Optional: Delete the local draft or mark it as 'Failed' if Meta rejects it
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Meta API Error: {response.json().get('error', {}).get('message', 'Unknown error')}"
            )

        # 4. Update record with Meta's returned template ID
        meta_data = response.json()
        new_template.meta_template_id = meta_data.get("id")
        db.commit()
        db.refresh(new_template)
    
    return new_template