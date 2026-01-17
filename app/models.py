import uuid
from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP, Integer, Table, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# --- Association Tables ---
# Manages many-to-many relationship between Contacts and Groups
contact_group_assignments = Table(
    "contact_group_assignments",
    Base.metadata,
    Column("contact_id", UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", UUID(as_uuid=True), ForeignKey("contact_groups.id", ondelete="CASCADE"), primary_key=True),
)

# --- Core Models ---

class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    owner_email = Column(String(255), unique=True, nullable=False)
    meta_access_token = Column(Text, nullable=False) 
    waba_id = Column(String(100), nullable=False)
    phone_number_id = Column(String(100), nullable=False)
    messaging_tier = Column(String(50), server_default="TIER_250")
    subscription_plan = Column(String(50), server_default="Basic")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relationships with cascade deletes for clean multi-tenant management
    users = relationship("User", back_populates="business", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="business", cascade="all, delete-orphan")
    templates = relationship("Template", back_populates="business", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="business", cascade="all, delete-orphan")
    media_assets = relationship("MediaAsset", back_populates="business", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(20), server_default="Agent") 
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="users")

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    phone_number = Column(String(20), nullable=False)
    name = Column(String(255))
    tags = Column(ARRAY(Text))
    status = Column(String(20), server_default="Active") 
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    business = relationship("Business", back_populates="contacts")
    groups = relationship("ContactGroup", secondary=contact_group_assignments, back_populates="contacts")
    messages = relationship("Message", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('Active', 'Opt-out')"),
        UniqueConstraint('business_id', 'phone_number'),
        Index('idx_contacts_business_status', 'business_id', 'status'),
    )

class ContactGroup(Base):
    __tablename__ = "contact_groups"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    group_name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    contacts = relationship("Contact", secondary=contact_group_assignments, back_populates="groups")

    __table_args__ = (UniqueConstraint('business_id', 'group_name'),)

class Template(Base):
    __tablename__ = "templates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    meta_template_id = Column(String(100)) 
    name = Column(String(255), nullable=False)
    content_json = Column(JSONB, nullable=False) 
    status = Column(String(20), server_default="Pending") 
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="templates")
    campaigns = relationship("Campaign", back_populates="template")

    __table_args__ = (
        CheckConstraint("status IN ('Pending', 'Approved', 'Rejected')"),
    )

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(UUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL"))
    name = Column(String(255))
    total_contacts = Column(Integer, server_default="0")
    scheduled_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="campaigns")
    template = relationship("Template", back_populates="campaigns")
    messages = relationship("Message", back_populates="campaign")

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"))
    meta_message_id = Column(String(255), unique=True)
    direction = Column(String(10), nullable=False) 
    status = Column(String(20), server_default="Sent") 
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business")
    contact = relationship("Contact", back_populates="messages")
    campaign = relationship("Campaign", back_populates="messages")

    __table_args__ = (
        CheckConstraint("direction IN ('In', 'Out')"),
        # Optimized composite index for real-time webhook status updates
        Index('idx_messages_tracking', 'business_id', 'meta_message_id'),
    )

class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"))
    payload = Column(JSONB, nullable=False) 
    received_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class MediaAsset(Base):
    __tablename__ = "media_assets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String(255))
    media_url = Column(Text) 
    meta_media_id = Column(String(255)) 
    mime_type = Column(String(50))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="media_assets")