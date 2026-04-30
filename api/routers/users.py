from fastapi import APIRouter, HTTPException
import logging
from pydantic import BaseModel

from interfaces import db, aexec
from models.users import UserUpdate
from clients.openai_client import get_openai_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])


class StyleBrandChipsRequest(BaseModel):
	gender: str | None = None
	location: str | None = None
	job: str | None = None
	body_shape: str | None = None
	fit_preference: str | None = None
	lifestyle_occasions: list[str] = []
	daily_dress_code: str | None = None
	color_comfort: list[str] = []
	style_avoids: list[str] = []
	budget_preference: str | None = None


@router.post("/guest", response_model=dict)
async def create_guest_user():
	"""Create an anonymous guest user."""
	try:
		user = await aexec(db.users.create_guest)
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
		user = await aexec(db.users.get, user_id)
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
		user = await aexec(db.users.update, user_id, updates)
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
			body_shape=request.body_shape,
			fit_preference=request.fit_preference,
			lifestyle_occasions=request.lifestyle_occasions,
			daily_dress_code=request.daily_dress_code,
			color_comfort=request.color_comfort,
			style_avoids=request.style_avoids,
			budget_preference=request.budget_preference,
		)
		return {"success": True, "brands": brands}
	except Exception as e:
		logger.error(f"❌ Error generating style brand chips: {e}")
		raise HTTPException(status_code=500, detail=f"Brand chips failed: {e}")
