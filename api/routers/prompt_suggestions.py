from fastapi import APIRouter, HTTPException
import logging
from typing import Dict

from services.prompt_suggestions_service import PromptSuggestionsService
from models import PromptSuggestionsResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prompt-suggestions", tags=["prompt_suggestions"]) 

service = PromptSuggestionsService()

@router.post("/{user_id}/generate", response_model=PromptSuggestionsResponse)
async def generate_prompt_suggestions(user_id: str, ignore_throttle: bool = False):
    try:
        prompts = await service.generate_and_save(user_id, ignore_throttle=ignore_throttle)
        return PromptSuggestionsResponse(success=True, user_id=user_id, prompts=prompts)
    except Exception as e:
        logger.error(f"❌ Error generating prompt suggestions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}") 