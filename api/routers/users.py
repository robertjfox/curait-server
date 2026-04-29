from fastapi import APIRouter, HTTPException
import logging
from pydantic import BaseModel

from interfaces.users_interface import UsersInterface
from models.users import UserUpdate
from clients.openai_client import get_openai_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])

users_interface = UsersInterface()


class StyleBrandChipsRequest(BaseModel):
    gender: str | None = None
    location: str | None = None
    job: str | None = None


@router.post("/guest", response_model=dict)
async def create_guest_user():
    """Create an anonymous guest user.

    Used by the web app on first visit to provision a persistent identity
    without requiring signup. Runs server-side with the service-role key so
    it bypasses any RLS policies on the `users` table.
    """
    try:
        user = users_interface.create_guest()
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=500, detail="Guest user missing id")
        logger.info(f"👤 Created guest user {user_id[:8]}")
        return {"success": True, "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating guest user: {e}")
        raise HTTPException(status_code=500, detail=f"Guest creation failed: {e}")


@router.get("/{user_id}", response_model=dict)
async def get_user(user_id: str):
    """Fetch a user profile."""
    try:
        user = users_interface.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"User fetch failed: {e}")


@router.patch("/{user_id}", response_model=dict)
async def update_user(user_id: str, request: UserUpdate):
    """Update a guest/user profile with onboarding context."""
    try:
        updates = request.model_dump(exclude_unset=True)
        user = users_interface.update(user_id, updates)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"User update failed: {e}")


@router.post("/style-brand-chips", response_model=dict)
async def generate_style_brand_chips(request: StyleBrandChipsRequest):
    """Generate onboarding brand chips from basic user context."""
    try:
        brands = await get_openai_client().generate_style_brand_chips(
            gender=request.gender or "",
            location=request.location or "",
            job=request.job,
        )
        return {"success": True, "brands": brands}
    except Exception as e:
        logger.error(f"❌ Error generating style brand chips: {e}")
        raise HTTPException(status_code=500, detail=f"Brand chips failed: {e}")
