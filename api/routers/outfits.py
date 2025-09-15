from fastapi import APIRouter, HTTPException
import logging

from services.outfit_generation_service import OutfitGenerationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/outfits", tags=["outfits"])

service = OutfitGenerationService()


@router.post("/{outfit_id}/search-and-rank", response_model=dict)
async def search_and_rank_outfit(outfit_id: str):

    logger.info(f"Searching/ranking outfit {outfit_id}")

    try:
        result = await service.search_and_rank_for_outfit(outfit_id=outfit_id)
        if not result.get("success", False) and result.get("message") == "Outfit not found":
            raise HTTPException(status_code=404, detail="Outfit not found")
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error searching/ranking outfit {outfit_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process outfit {outfit_id}") 