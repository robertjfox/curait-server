from fastapi import APIRouter, HTTPException
import logging

from models import ThreadCreateRequest, ThreadChatRequest
from services.thread_service import ThreadService
from services.prompt_suggestions_service import PromptSuggestionsService
from interfaces.threads_interface import ThreadsInterface

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])

thread_service = ThreadService()
prompt_suggestions_service = PromptSuggestionsService()
threads_interface = ThreadsInterface()


@router.post("/create", response_model=dict)
async def create_thread(request: ThreadCreateRequest):
    """Create a new conversation thread."""
    try:
        thread_id = threads_interface.create(
            user_id=request.user_id,
        )

        logger.info(f"🧵 Created thread {thread_id[:6]}")

        if not thread_id:
            raise HTTPException(status_code=500, detail="Failed to create thread")

        # Fire-and-forget: compute initial research and store on thread.context
        try:
            import asyncio
            asyncio.create_task(thread_service._generate_thread_research_task(thread_id))
        except Exception:
            pass

        # Fire-and-forget: generate prompt suggestions for the user
        try:
            import asyncio
            asyncio.create_task(
                prompt_suggestions_service.generate_and_save(
                    request.user_id,
                    ignore_throttle=True,
                )
            )
        except Exception:
            pass

        return {
            "success": True,
            "thread_id": thread_id
        }
        
    except Exception as e:
        logger.error(f"❌ Error creating thread: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Thread creation failed: {str(e)}")


@router.post("/{thread_id}/chat")
async def chat_in_thread(thread_id: str, request: ThreadChatRequest):
    try:
        await thread_service.route_user_message(
            thread_id=thread_id,
            user_message=request.message,
        )
        
        return {
            "success": True,
            "thread_id": thread_id,
        }
        
    except HTTPException:
        raise HTTPException(status_code=400, detail="Invalid request")
    except Exception as e:
        logger.error(f"❌ Error in thread chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


 