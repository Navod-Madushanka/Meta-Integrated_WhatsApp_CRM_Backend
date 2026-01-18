import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Database and Models
from app.database import engine, Base
from app.models import Business, User, Contact, Template, Message, WebhookLog # Ensure models are loaded

# Routes
from app.routes import auth, webhooks

# 1. Setup Logging for production tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# 2. Database Initialization
# Note: In production, you will use Alembic for migrations.
# This line creates tables automatically if they don't exist.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Meta-Integrated WhatsApp CRM",
    description="SaaS Backend for WhatsApp Cloud API Onboarding and Bulk Messaging",
    version="1.0.0"
)

# 3. CORS Configuration (Essential for Production)
# Replace "*" with your actual frontend domain in production (e.g., https://crm.yourdomain.com)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Include Routers
# Phase 2: Auth and Onboarding Logic
app.include_router(auth.router)

# Phase 2.5: Webhook Listener for Meta Events & Opt-outs
app.include_router(webhooks.router)

@app.get("/")
def read_root():
    return {
        "status": "SaaS Engine Running",
        "docs": "/docs",
        "health": "healthy"
    }