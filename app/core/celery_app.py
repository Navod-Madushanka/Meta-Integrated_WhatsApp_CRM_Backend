import logging
from celery import Celery
from celery.signals import after_setup_logger
from app.core.config import settings

# --- 1. Initialize Celery ---
# We name the main app 'worker'.
# broker: The URL where messages are sent (Redis).
# backend: The URL where task results are stored (Redis).
celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# --- 2. Configuration ---
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # This ensures Celery finds your tasks in the workers directory
    include=["app.workers.campaign_worker"],
    # Best practice: discourage the worker from hanging on lost connections
    broker_connection_retry_on_startup=True
)

# --- 3. Logging Setup ---
logger = logging.getLogger(__name__)

@after_setup_logger.connect
def setup_celery_logger(logger, *args, **kwargs):
    """
    Configures the Celery worker logging format to match 
    your FastAPI uvicorn logs.
    """
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("Celery worker logger initialized.")

# --- 4. Debug Task (Optional) ---
@celery_app.task(bind=True)
def debug_task(self):
    """A simple task to verify the worker is connected to Redis."""
    logger.info(f"Request: {self.request!r}")
    return "Worker is healthy"

if __name__ == "__main__":
    celery_app.start()