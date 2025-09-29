from __future__ import annotations
import logging
import asyncio

from interfaces.threads_interface import ThreadsInterface
from interfaces.users_interface import UsersInterface
from clients.openai_client import get_openai_client

logger = logging.getLogger(__name__)
class ThreadService:
    """Simplified service for managing conversational styling threads."""
    
    def __init__(self):
        # Core thread management
        self.threads_interface = ThreadsInterface()
        self.users_interface = UsersInterface()
        self.openai_client = get_openai_client()

    async def _generate_thread_research_task(self, thread_id: str) -> None:
        """Fire-and-forget: compute research and store under thread.research."""
        try:
            thread = self.threads_interface.get(thread_id)
            user_id = (thread or {}).get("user_id") if thread else None
            user_data = self.users_interface.get_relevant_context(user_id) if user_id else {}
            research_obj = await self.openai_client.generate_thread_research(user_data=user_data)
            # store under dedicated column (as text)
            self.threads_interface.update_research(thread_id, research_obj)
        except Exception as e:
            logger.warning(f"Failed to generate/store thread research: {e}")

    async def _generate_title_task(self, thread_id: str, first_user_message: str) -> None:
        """Fire-and-forget: generate a short title and update thread when ready."""
        try:
            title = await self.openai_client.generate_title_flow(first_user_message=first_user_message)
            self.threads_interface.update_title(thread_id, title)
        except Exception as e:
            logger.warning(f"Failed to generate title: {e}")

    async def route_user_message(
        self,
        thread_id: str,
        user_message: str,
    ) -> None:
        """Main entry point for styling conversations - only adds comments now."""
        try:
            logger.info(f"User message: {user_message}")

            # Generate title if needed
            thread = self.threads_interface.get(thread_id)
            thread_title = thread.get("title", "Thread Title") if thread else "Thread Title"

            if not thread_title or thread_title == "Thread Title":
                asyncio.create_task(self._generate_title_task(thread_id, user_message))

            # The ONLY function: add the comment
            self.threads_interface.add_comment(thread_id, user_message)

        except Exception as e:
            logger.error(f"Failed to add comment: {e}")
            raise



