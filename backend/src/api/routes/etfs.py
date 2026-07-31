"""GET /api/etfs — list supported ETFs with metadata."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db

router = APIRouter()


@router.get("/etfs")
async def list_etfs(db: AsyncSession = Depends(get_db)):
    """Return all supported ETFs with last-update metadata."""
    # TODO: implement — query etfs table
    return []
