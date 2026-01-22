from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from datetime import datetime

# --- 1. Template Component Validation ---
# This ensures content_json strictly follows Meta's required structure
# [cite: 244]
class TemplateComponent(BaseModel):
    type: Literal["HEADER", "BODY", "FOOTER", "BUTTONS"]
    format: Optional[Literal["TEXT", "IMAGE", "VIDEO", "DOCUMENT"]] = None
    text: Optional[str] = None
    buttons: Optional[List[Dict[str, Any]]] = None

# --- 2. Business & Onboarding Schemas ---
class BusinessBase(BaseModel):
    name: str
    owner_email: EmailStr

class BusinessRegisterRequest(BaseModel):
    """Initial signup schema used in register.py"""
    business_name: str
    owner_email: EmailStr
    password: str

class BusinessOnboardingUpdate(BaseModel):
    """Used for Process 1: Automated Onboarding after Meta callback"""
    meta_access_token: str
    waba_id: str
    phone_number_id: str

class BusinessOut(BusinessBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    waba_id: Optional[str] = None
    phone_number_id: Optional[str] = None
    messaging_tier: str = "TIER_250"
    subscription_plan: str = "Basic"

# --- 3. User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    role: str = "Agent"

class UserCreate(UserBase):
    password: str
    business_id: UUID

class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    created_at: datetime

# --- 4. Contact Schemas ---
class ContactBase(BaseModel):
    phone_number: str
    name: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Literal["Active", "Opt-out"] = "Active"

class ContactCreate(ContactBase):
    business_id: UUID

class ContactOut(ContactBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    created_at: datetime

class ContactGroupBase(BaseModel):
    group_name: str
    description: Optional[str] = None

class ContactGroupOut(ContactGroupBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    created_at: datetime

# --- 5. Template Schemas ---
# This section implements the Template Builder API requirements
class TemplateBase(BaseModel):
    name: str # [cite: 156]
    category: Literal["MARKETING", "UTILITY", "AUTHENTICATION"] = "MARKETING"
    language: str = "en_US"
    # [cite_start]Validates structure to prevent Meta rejection [cite: 244]
    components: List[TemplateComponent]

class TemplateCreate(TemplateBase):
    """Used for the POST /templates/ endpoint"""
    pass 

class TemplateOut(TemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    meta_template_id: Optional[str] = None
    status: Literal["Pending", "Approved", "Rejected"] = "Pending"
    created_at: datetime

# --- 6. Campaign & Message Schemas ---
class CampaignCreate(BaseModel):
    business_id: UUID
    name: str
    template_id: UUID
    contact_group_id: Optional[UUID] = None
    scheduled_at: Optional[datetime] = None

class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    contact_id: UUID
    direction: Literal["In", "Out"]
    status: str
    timestamp: datetime

class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    name: str
    template_id: UUID
    contact_group_id: Optional[UUID] = None
    status: str
    scheduled_at: Optional[datetime] = None
    created_at: datetime