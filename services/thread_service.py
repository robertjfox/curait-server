from __future__ import annotations
import logging
import asyncio

from interfaces.threads_interface import ThreadsInterface
from services.outfit_generation_service import OutfitGenerationService
from clients.openai_client import get_openai_client
from utils.background_tasks import spawn

logger = logging.getLogger(__name__)


class ThreadService:
    """Service for managing conversational styling threads.

    Every user message:
      1. is appended to the thread's comments JSONB array
      2. kicks off outfit generation (fire-and-forget).
    Clients observe generated outfits + ranking results via Supabase realtime.
    """

    def __init__(self):
        self.threads_interface = ThreadsInterface()
        self.outfit_service = OutfitGenerationService()
        self.openai_client = get_openai_client()

    async def _generate_title_task(self, thread_id: str, first_user_message: str) -> None:
        """Fire-and-forget: generate a short title and update thread when ready."""
        try:
            title = await self.openai_client.generate_title_flow(first_user_message=first_user_message)
            self.threads_interface.update_title(thread_id, title)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Failed to generate title: {e}")

    async def _generate_outfits_task(self, thread_id: str) -> None:
        """Fire-and-forget: generate outfits for this thread in the background."""
        try:
            await self.outfit_service.generate_outfits_for_thread(thread_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Background outfit generation failed for {thread_id}: {e}")

    async def aclose(self) -> None:
        await self.outfit_service.aclose()

    async def route_user_message(self, thread_id: str, user_message: str) -> None:
        """Append a user message to a thread and trigger outfit generation."""
        logger.info(f"User message ({thread_id[:6]}): {user_message}")

        thread = self.threads_interface.get(thread_id)
        thread_title = thread.get("title") if thread else None

        if not thread_title or thread_title == "Thread Title":
            spawn(
                self._generate_title_task(thread_id, user_message),
                name=f"generate-title:{thread_id[:6]}",
            )

        self.threads_interface.add_comment(thread_id, user_message)

        spawn(
            self._generate_outfits_task(thread_id),
            name=f"generate-outfits:{thread_id[:6]}",
        )
