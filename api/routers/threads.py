from fastapi import APIRouter, HTTPException
import logging

from models import ThreadCreateRequest, ThreadChatRequest
from services.thread_service import ThreadService
from interfaces.threads_interface import ThreadsInterface

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])

thread_service = ThreadService()
threads_interface = ThreadsInterface()


@router.post("/create", response_model=dict)
async def create_thread(request: ThreadCreateRequest):
    """Create a new conversation thread."""
    try:
        thread_id = threads_interface.create(
            user_id=request.user_id,
        )

        if not thread_id:
            raise HTTPException(status_code=500, detail="Failed to create thread")

        logger.info(f"🧵 Created thread {thread_id}")
        
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
        logger.info(f"🧵 Chatting in thread {thread_id}")
        logger.info(f"🧵 Request: {request}")

        await thread_service.route_user_message(
            thread_id=thread_id,
            user_message=request.message,
            user_intent=request.user_intent,
            outfit_id=request.outfit_id
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


 