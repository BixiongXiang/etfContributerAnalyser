"""Shared FastAPI dependencies (injected via Depends())."""

# Re-export get_db so routes can import from one place
from src.models.database import get_db  # noqa: F401
