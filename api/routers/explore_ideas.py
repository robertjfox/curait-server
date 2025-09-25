from fastapi import APIRouter, HTTPException, Query
from typing import Literal
import logging

from services.explore_ideas_service import ExploreIdeasService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/explore-ideas", tags=["explore_ideas"])

service = ExploreIdeasService()


@router.post("/generate-research", response_model=dict)
async def generate_trend_research(
    gender: Literal["male", "female"] = Query(..., description="Target gender")
):
    try:
        logger.info(f"[API] /api/explore-ideas/generate-research gender={gender}")
        result = await service.generate_and_save_trend_research(gender=gender)
        logger.info("[API] deep research completed successfully")
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[API] Failed to generate trend research: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate trend research")


@router.post("/generate-ideas", response_model=dict)
async def generate_explore_ideas(
    gender: Literal["male", "female"] = Query(..., description="Target gender")
):
    try:
        logger.info(f"[API] /api/explore-ideas/generate-ideas gender={gender}")
        result = await service.generate_explore_ideas(gender=gender)
        logger.info(f"[API] explore ideas generation completed created={result.get('created')}")
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[API] Failed to generate explore ideas: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate explore ideas")


