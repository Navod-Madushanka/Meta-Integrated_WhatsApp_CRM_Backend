import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Database and Models
from app.database import engine, Base
# Ensure all models are loaded so create_all() knows what tables to build
from app.models import Business, User, Contact, Template, Message, WebhookLog 

# Routes
# Added templates router for Phase 4
from app.routes import auth, webhooks, templates, campaigns

# 1. Setup Logging for production tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# 2. Database Initialization
# Automatically creates tables in PostgreSQL/SQLite based on models.py
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Meta-Integrated WhatsApp CRM",
    description="SaaS Backend for WhatsApp Cloud API Onboarding and Bulk Messaging",
    version="1.0.0"
)

# 3. CORS Configuration
# Essential for allowing your React frontend to communicate with this API
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

# Phase 4: Template & Campaign Management
# This enables the POST /templates/ endpoint
app.include_router(templates.router)

app.include_router(campaigns.router)

@app.get("/")
def read_root():
    return {
        "status": "SaaS Engine Running",
        "docs": "/docs",
        "health": "healthy",
        "active_modules": ["Auth", "Webhooks", "Templates"]
    }