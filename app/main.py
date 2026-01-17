from fastapi import FastAPI
from .database import engine, Base

# Create tables in database (only for development; use Alembic later)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Meta-Integrated WhatsApp CRM")

@app.get("/")
def read_root():
    return {"status": "SaaS Engine Running"}