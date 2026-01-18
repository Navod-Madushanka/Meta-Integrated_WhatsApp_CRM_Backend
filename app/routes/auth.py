import httpx
import logging
import uuid  # Added import
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Business
from app.core.config import settings
from app.core.security import encrypt_token, Hasher
from pydantic import BaseModel, EmailStr

# set up logging
logger = logging.getLogger("unicorn.error")
router = APIRouter(prefix="/auth", tags=["onboarding"])

class RegisterSchema(BaseModel):
    business_name: str
    owner_email: EmailStr
    password: str

@router.post("/register")
async def register(data: RegisterSchema, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.owner_email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    try:
        pending_token = encrypt_token("PENDING_ONBOARDING")

        new_biz = Business(
            name=data.business_name,
            owner_email=data.owner_email,
            meta_access_token=pending_token, 
            waba_id="PENDING",
            phone_number_id="PENDING",
            messaging_tier="TIER_250"
        )
        db.add(new_biz)
        db.flush()

        new_user = User(
            business_id = new_biz.id,
            email = data.owner_email,
            password_hash = Hasher.get_password_hash(data.password),
            role = "admin"
        )

        db.add(new_user)
        db.commit()

        return {"business_id": str(new_biz.id), "status": "ready for meta signup"}
    except Exception as e:
        db.rollback()
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed")
    
@router.post("/meta-callback/{business_id}")
async def meta_onboarding_callback(
    business_id: uuid.UUID, # FIXED: Changed from str to uuid.UUID
    code: str, 
    db: Session = Depends(get_db)
):
    # business_id is now a UUID object, compatible with SQLAlchemy/Postgres UUID types
    biz = db.query(Business).filter(Business.id == business_id).first()
    if not biz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business record not found")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/oauth/access_token"
        token_res = await client.get(token_url, params={
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_CLIENT_SECRET,
            "code": code,
        })

        if token_res.status_code != 200:
            logger.error(f"Meta Token Exchange Error: {token_res.text}")
            raise HTTPException(status_code=400, detail="Failed to exchange Meta code")
        
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        waba_id = token_data.get("whatsapp_business_account_id")
        phone_id = token_data.get("phone_number_id")

        if not phone_id:
            phone_res = await client.get(
                f"https://graph.facebook.com/{settings.META_API_VERSION}/{waba_id}/phone_numbers",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if phone_res.status_code == 200:
                phones = phone_res.json().get("data", [])
                if phones:
                    phone_id = phones[0].get("id")
            
        sub_url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{waba_id}/subscribed_apps"
        sub_res = await client.post(
            sub_url,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        if sub_res.status_code != 200:
            logger.error(f"Meta Subscription Error: {sub_res.text}")
            raise HTTPException(status_code=500, detail="Webhook link failed")
        
        try:
            biz.meta_access_token = encrypt_token(access_token)
            biz.waba_id = waba_id
            biz.phone_number_id = phone_id if phone_id else "RECOVERY_FAILED"
            db.commit()
            return {"status": "SUCCESS", "waba_id": waba_id}
        except Exception as e:
            db.rollback()
            logger.error(f"Final DB Update Failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Database update failed")