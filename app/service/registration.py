from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Business, User
from pydantic import BaseModel, EmailStr
import bcrypt

router = APIRouter(prefix="/auth", tags=["Onboarding"])

# Pydantic schema for the request body
class BusinessRegisterSchema(BaseModel):
    business_name: str
    owner_email: EmailStr
    password: str

@router.post("/register")
async def register_business(data: BusinessRegisterSchema, db: Session = Depends(get_db)):
    # 1. Check for existing owner
    if db.query(User).filter(User.email == data.owner_email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        # 2. Create the Business record
        # Note: meta_access_token, waba_id, and phone_number_id are NOT NULL.
        # we initialize them as 'PENDING' until the Meta Signup is completed.
        new_business = Business(
            name=data.business_name,
            owner_email=data.owner_email,
            meta_access_token="PENDING_ONBOARDING",
            waba_id="PENDING",
            phone_number_id="PENDING"
        )
        db.add(new_business)
        db.flush()  # Gets the new_business.id (UUID) for the user link

        # 3. Create the Admin User
        hashed_pw = bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        new_user = User(
            business_id=new_business.id,
            email=data.owner_email,
            password_hash=hashed_pw,
            role="Admin"
        )
        db.add(new_user)
        
        db.commit()
        return {
            "status": "success", 
            "business_id": str(new_business.id),
            "message": "Account created. Please link your WhatsApp account next."
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error during registration")