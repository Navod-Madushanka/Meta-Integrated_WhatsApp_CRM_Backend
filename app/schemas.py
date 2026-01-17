from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from datetime import datetime

# --- Business Schemas ---
class BusinessBase(BaseModel):
    name: str
    owner_email: EmailStr
    waba_id: str
    phone_number_id: str
    subscription_plan: Optional[str] = "Basic"

class BusinessCreate(BusinessBase):
    meta_access_token: str

class BusinessOut(BusinessBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    messaging_tier: str
    created_at: datetime

# --- User Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    business_id: UUID
    role: Optional[Literal["Admin", "Manager", "Agent"]] = "Agent"

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    email: EmailStr
    role: str
    created_at: datetime

# --- Contact & Group Schemas ---
class ContactBase(BaseModel):
    phone_number: str
    name: Optional[str] = None
    tags: Optional[List[str]] = []
    status: Optional[Literal["Active", "Opt-out"]] = "Active"

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

# --- Template Schemas ---
class TemplateBase(BaseModel):
    name: str
    content_json: Dict[str, Any]

class TemplateCreate(TemplateBase):
    business_id: UUID

class TemplateOut(TemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    meta_template_id: Optional[str] = None
    status: Literal["Pending", "Approved", "Rejected"] = "Pending"
    created_at: datetime

# --- Campaign & Message Schemas ---
class CampaignCreate(BaseModel):
    business_id: UUID
    name: Optional[str] = None
    template_id: Optional[UUID] = None
    scheduled_at: Optional[datetime] = None

class CampaignOut(CampaignCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    total_contacts: int
    created_at: datetime

class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    contact_id: UUID
    campaign_id: Optional[UUID] = None
    meta_message_id: Optional[str] = None
    direction: Literal["In", "Out"]
    status: str = "Sent"
    timestamp: datetime

# --- Media & Webhook Schemas ---
class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    file_name: Optional[str] = None
    media_url: Optional[str] = None
    meta_media_id: Optional[str] = None
    mime_type: Optional[str] = None
    created_at: datetime

class WebhookLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: Optional[UUID] = None
    payload: Dict[str, Any]
    received_at: datetime