import httpx
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models import User, Business
from app.core.config import settings
from app.core.security import encrypt_token, Hasher, create_access_token

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/auth", tags=["onboarding"])

# --- SCHEMAS ---

class RegisterSchema(BaseModel):
    business_name: str
    owner_email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    business_id: str

class MetaCallbackSchema(BaseModel):
    code: str

# --- ROUTES ---

@router.post("/register")
async def register(data: RegisterSchema, db: Session = Depends(get_db)):
    """Registers a new business and an admin user with placeholder Meta credentials."""
    if db.query(User).filter(User.email == data.owner_email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Email already registered"
        )
    
    try:
        # Initial placeholder setup for Step 1
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
            business_id=new_biz.id,
            email=data.owner_email,
            password_hash=Hasher.get_password_hash(data.password),
            role="Admin"
        )

        db.add(new_user)
        db.commit()

        return {"business_id": str(new_biz.id), "status": "ready for meta signup"}
    except Exception as e:
        db.rollback()
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Registration failed"
        )

@router.post("/login", response_model=TokenResponse)
async def login(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticates a user and returns a JWT access token for the dashboard."""
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not Hasher.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": user.email, "business_id": str(user.business_id)}
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "business_id": str(user.business_id)
    }

@router.post("/meta-callback/{business_id}")
async def meta_onboarding_callback(
    business_id: uuid.UUID, 
    payload: MetaCallbackSchema,
    db: Session = Depends(get_db)
):
    """
    Step 7 & 8: Exchanges Meta code, fetches Phone ID, and subscribes to webhooks.
    Includes updated Step 8 verification for production reliability.
    """
    biz = db.query(Business).filter(Business.id == business_id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business record not found")
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Exchange Code for Permanent Access Token
        token_url = f"https://graph.facebook.com/{settings.META_APP_VERSION}/oauth/access_token"
        
        token_res = await client.get(token_url, params={
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_CLIENT_SECRET,
            "code": payload.code,
        })

        if token_res.status_code != 200:
            logger.error(f"Meta Token Exchange Error: {token_res.text}")
            raise HTTPException(status_code=400, detail="Meta code exchange failed")
        
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        waba_id = token_data.get("whatsapp_business_account_id")

        if not waba_id:
            logger.error(f"WABA ID missing in Meta response for business {business_id}")
            raise HTTPException(status_code=400, detail="WABA ID not found in Meta response")

        # 2. Fetch Phone Number ID (Required for sending messages)
        phone_id = None
        phone_res = await client.get(
            f"https://graph.facebook.com/{settings.META_APP_VERSION}/{waba_id}/phone_numbers",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if phone_res.status_code == 200:
            phones = phone_res.json().get("data", [])
            if phones:
                # Selecting the first available number linked to this WABA
                phone_id = phones[0].get("id")
        else:
            logger.warning(f"Could not fetch phone numbers for WABA {waba_id}: {phone_res.text}")

        # 3. Step 8: Subscribe App to the WABA (Crucial for Webhook Routing)
        # This tells Meta to send incoming messages to our system's webhook URL.
        sub_url = f"https://graph.facebook.com/{settings.META_APP_VERSION}/{waba_id}/subscribed_apps"
        sub_res = await client.post(
            sub_url,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        # Update: Verify the subscription was successful before saving to DB
        if sub_res.status_code != 200:
            logger.error(f"Webhook Subscription Failed for WABA {waba_id}: {sub_res.text}")
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY, 
                detail="Failed to initialize Meta Webhook subscription."
            )

        # 4. Secure Storage of Credentials
        try:
            biz.meta_access_token = encrypt_token(access_token)
            biz.waba_id = waba_id
            biz.phone_number_id = phone_id if phone_id else "PENDING_PHONE_ID"
            db.commit()
            
            logger.info(f"Business {business_id} initialized: WABA {waba_id}, Phone {phone_id}")
            return {
                "status": "SUCCESS", 
                "waba_id": waba_id, 
                "phone_number_id": phone_id
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Database Update Failed for {business_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to save Meta credentials to database")