import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from main import app
from app.models import Business, User

# 1. Setup a temporary SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 2. Dependency override to use the test database
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    """Create and drop tables for each test run."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

# --- THE TESTS ---

def test_register_new_business():
    """Checks successful registration."""
    payload = {
        "business_name": "Test Company",
        "owner_email": "test@example.com",
        "password": "securepassword123"
    }
    response = client.post("/auth/register", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "business_id" in data
    assert data["status"] == "ready for meta signup"
    
    # Verify UUID format
    try:
        uuid.UUID(data["business_id"])
    except ValueError:
        pytest.fail("business_id is not a valid UUID")

def test_register_duplicate_email():
    """Ensures duplicate email blocks are working."""
    payload = {
        "business_name": "Duplicate Co",
        "owner_email": "dup@example.com",
        "password": "password123"
    }
    # First registration
    client.post("/auth/register", json=payload)
    
    # Second registration with same email
    response = client.post("/auth/register", json=payload)
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

def test_meta_callback_business_not_found():
    """
    Checks if the system correctly identifies a missing business 
    using a valid UUID format.
    """
    fake_id = uuid.uuid4() # Generate a real UUID object
    response = client.post(f"/auth/meta-callback/{fake_id}?code=test_code")
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Business record not found"