import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Database and Models
from app.database import engine, Base
# IMPORTANT: Ensure your folder is named 'routers' or 'routes' consistently
# from app.routers import auth, webhooks, templates, campaigns
from app.routes import auth, webhooks, templates, campaigns 

# 1. Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# 2. Database Initialization
# Creates tables defined in your PDF schema (businesses, users, templates, etc.)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Meta-Integrated WhatsApp CRM",
    description="SaaS Backend for WhatsApp Cloud API Onboarding and Bulk Messaging",
    version="1.0.0"
)

# 3. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Change to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Include Routers
# Phase 1 & 2: Auth, Registration, and Meta Onboarding
app.include_router(auth.router)

# Phase 2.5: Webhook Listener (Message statuses & Opt-outs)
app.include_router(webhooks.router)

# Phase 3 & 4: Template & Campaign Management
app.include_router(templates.router)
app.include_router(campaigns.router)

@app.get("/")
def read_root():
    return {
        "status": "SaaS Engine Running",
        "docs": "/docs",
        "health": "healthy",
        "active_modules": ["Auth", "Webhooks", "Templates", "Campaigns"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)