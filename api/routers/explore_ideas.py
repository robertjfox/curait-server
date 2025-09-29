from fastapi import APIRouter, HTTPException, Query, Body
import logging

from clients.supabase_client import get_supabase_client
from services.explore_ideas_service import ExploreIdeasService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/explore-ideas", tags=["explore_ideas"])

service = ExploreIdeasService()

@router.post("/generate-ideas", response_model=dict)
async def generate_explore_ideas(
    trend_outfit_id: str = Query(..., description="ID of the trend outfit to base the explore ideas on")
):
    try:
        logger.info(f"[API] /api/explore-ideas/generate-ideas trend_outfit_id={trend_outfit_id}")
        result = await service.generate_explore_ideas(trend_outfit_id=trend_outfit_id)
        logger.info(f"[API] explore ideas generation completed created={result.get('created')}")
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[API] Failed to generate explore ideas: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate explore ideas")


@router.post("/trend-outfit-variation", response_model=dict)
async def generate_trend_outfit_variation(
    trend_outfit_id: str = Query(..., description="Trend outfit ID to generate additional variations for"),
    num_to_generate: int = Query(1, description="Number of variations to generate", ge=1, le=10)
):
    try:
        logger.info(f"[API] /api/explore-ideas/trend-outfit-variation trend_outfit_id={trend_outfit_id} num_to_generate={num_to_generate}")
        result = await service.generate_trend_outfit_variations(trend_outfit_id=trend_outfit_id, num_to_generate=num_to_generate)
        logger.info(f"[API] trend outfit variations completed created={result.get('created')}")
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[API] Failed to generate trend outfit variations: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate trend outfit variations")


@router.post("/analyze-trend-outfit", response_model=dict)
async def analyze_trend_outfit(
    image_url: str = Body(..., embed=True, description="Source image URL to analyze"),
    source_id: str = Body(..., embed=True, description="Source ID for the trend outfit")
):
    try:
        logger.info("[API] /api/explore-ideas/analyze-trend-outfit")
        outfit = await service.analyze_trend_outfit(image_url=image_url, source_id=source_id)
        return {"success": True, "trend_outfit": outfit}
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"[API] Invalid analyze request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] Failed to analyze trend outfit: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze trend outfit")


# very simply returns an map of all the unique source_ids on the trend_outfits table. keep all the logic right here
# fetch from supabase right here, no other deps
@router.get("/source-ids", response_model=dict)
async def get_source_ids():
    try:
        logger.info("[API] /api/explore-ideas/source-ids")
        supabase = get_supabase_client()
        res = supabase.table("trend_outfits").select("source_id").execute()
        source_ids = [row["source_id"] for row in res.data]

        logger.info(f"[API] Found {len(source_ids)} source ids")
        logger.info(f"[API] Source ids: {source_ids}")

        # remove any None values
        return {"success": True, "source_ids": source_ids}
    except Exception as e:
        logger.error(f"[API] Failed to get source ids: {e}")
        raise HTTPException(status_code=500, detail="Failed to get source ids")


