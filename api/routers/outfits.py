from fastapi import APIRouter, HTTPException
import logging
from pydantic import BaseModel

from services.outfit_generation_service import get_outfit_generation_service
from interfaces import db, aexec

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/outfits", tags=["outfits"])


class RemixOutfitRequest(BaseModel):
	feedback: str


class SavedOutfitRequest(BaseModel):
	saved: bool


@router.get("/saved/by-user/{user_id}", response_model=dict)
async def list_saved_outfits(user_id: str):
	try:
		outfits = await aexec(db.outfits.list_saved_for_user, user_id)
		return {"success": True, "outfits": outfits}
	except Exception as e:
		logger.error(f"❌ Error listing saved outfits for user {user_id}: {str(e)}")
		raise HTTPException(status_code=500, detail="Failed to list saved outfits")


@router.patch("/{outfit_id}/saved", response_model=dict)
async def set_outfit_saved(outfit_id: str, request: SavedOutfitRequest):
	try:
		outfit = await aexec(db.outfits.set_saved, outfit_id, request.saved)
		if not outfit:
			raise HTTPException(status_code=404, detail="Outfit not found")
		return {"success": True, "outfit": outfit}
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Error updating saved state for outfit {outfit_id}: {str(e)}")
		raise HTTPException(status_code=500, detail="Failed to update saved state")


@router.post("/{outfit_id}/search-and-rank", response_model=dict)
async def search_and_rank_outfit(outfit_id: str):
	logger.info(f"Searching/ranking outfit {outfit_id}")
	try:
		result = await get_outfit_generation_service().search_and_rank_for_outfit(
			outfit_id=outfit_id,
		)
		if not result.get("success", False) and result.get("message") == "Outfit not found":
			raise HTTPException(status_code=404, detail="Outfit not found")
		return {"success": True, **result}
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Error searching/ranking outfit {outfit_id}: {str(e)}")
		raise HTTPException(status_code=500, detail=f"Failed to process outfit {outfit_id}")


@router.post("/{outfit_id}/remix", response_model=dict)
async def remix_outfit(outfit_id: str, request: RemixOutfitRequest):
	logger.info(f"Remixing outfit {outfit_id}")
	try:
		result = await get_outfit_generation_service().remix_outfit(
			outfit_id=outfit_id,
			feedback=request.feedback,
		)
		if not result.get("success", False):
			message = result.get("message") or "Remix failed"
			if message == "Outfit not found":
				raise HTTPException(status_code=404, detail=message)
			raise HTTPException(status_code=400, detail=message)
		return result
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Error remixing outfit {outfit_id}: {str(e)}")
		raise HTTPException(status_code=500, detail=f"Failed to remix outfit {outfit_id}")
