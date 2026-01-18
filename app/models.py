import uuid
from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP, Integer, Table, CheckConstraint, UniqueConstraint, Index, JSON, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# --- SQLite Compatibility Type Decorator ---
class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise uses String(36).
    """
    impl = UUID(as_uuid=True)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'sqlite':
            return dialect.type_descriptor(String(36))
        else:
            return dialect.type_descriptor(UUID(as_uuid=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == 'sqlite':
            return str(value) # Converts UUID object to string for SQLite
        return value

# --- Multi-DB Compatibility Helpers ---
CompatibleUUID = GUID()
CompatibleJSON = JSONB().with_variant(JSON, "sqlite")
CompatibleArray = ARRAY(Text).with_variant(Text, "sqlite")

# --- Association Tables ---
contact_group_assignments = Table(
    "contact_group_assignments",
    Base.metadata,
    Column("contact_id", CompatibleUUID, ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", CompatibleUUID, ForeignKey("contact_groups.id", ondelete="CASCADE"), primary_key=True),
)

# --- Core Models ---

class Business(Base):
    __tablename__ = "businesses"

    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    owner_email = Column(String(255), unique=True, nullable=False)
    meta_access_token = Column(Text, nullable=False) 
    waba_id = Column(String(100), nullable=False)
    phone_number_id = Column(String(100), nullable=False)
    messaging_tier = Column(String(50), server_default="TIER_250")
    subscription_plan = Column(String(50), server_default="Basic")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="business", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="business", cascade="all, delete-orphan")
    templates = relationship("Template", back_populates="business", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="business", cascade="all, delete-orphan")
    media_assets = relationship("MediaAsset", back_populates="business", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    business_id = Column(CompatibleUUID, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(20), server_default="Agent") 
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="users")

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    business_id = Column(CompatibleUUID, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    phone_number = Column(String(20), nullable=False)
    name = Column(String(255))
    tags = Column(CompatibleArray) 
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
    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    business_id = Column(CompatibleUUID, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    group_name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    contacts = relationship("Contact", secondary=contact_group_assignments, back_populates="groups")
    __table_args__ = (UniqueConstraint('business_id', 'group_name'),)

class Template(Base):
    __tablename__ = "templates"
    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    business_id = Column(CompatibleUUID, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    meta_template_id = Column(String(100)) 
    name = Column(String(255), nullable=False)
    content_json = Column(CompatibleJSON, nullable=False) 
    status = Column(String(20), server_default="Pending") 
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="templates")
    campaigns = relationship("Campaign", back_populates="template")

    __table_args__ = (
        CheckConstraint("status IN ('Pending', 'Approved', 'Rejected')"),
    )

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    business_id = Column(CompatibleUUID, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(CompatibleUUID, ForeignKey("templates.id", ondelete="SET NULL"))
    name = Column(String(255))
    total_contacts = Column(Integer, server_default="0")
    scheduled_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="campaigns")
    template = relationship("Template", back_populates="campaigns")
    messages = relationship("Message", back_populates="campaign")

class Message(Base):
    __tablename__ = "messages"
    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    business_id = Column(CompatibleUUID, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(CompatibleUUID, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(CompatibleUUID, ForeignKey("campaigns.id", ondelete="SET NULL"))
    meta_message_id = Column(String(255), unique=True)
    direction = Column(String(10), nullable=False) 
    status = Column(String(20), server_default="Sent") 
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business")
    contact = relationship("Contact", back_populates="messages")
    campaign = relationship("Campaign", back_populates="messages")

    __table_args__ = (
        CheckConstraint("direction IN ('In', 'Out')"),
        Index('idx_messages_tracking', 'business_id', 'meta_message_id'),
    )

class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    business_id = Column(CompatibleUUID, ForeignKey("businesses.id", ondelete="CASCADE"))
    payload = Column(CompatibleJSON, nullable=False) 
    received_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class MediaAsset(Base):
    __tablename__ = "media_assets"
    id = Column(CompatibleUUID, primary_key=True, default=uuid.uuid4)
    business_id = Column(CompatibleUUID, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String(255))
    media_url = Column(Text) 
    meta_media_id = Column(String(255)) 
    mime_type = Column(String(50))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    business = relationship("Business", back_populates="media_assets")