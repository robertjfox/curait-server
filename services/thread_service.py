from __future__ import annotations
from typing import Dict, Any, Optional, List, Callable
import logging
from collections import deque
import asyncio

from interfaces.threads_interface import ThreadsInterface
from interfaces.messages_interface import MessagesInterface
from interfaces.users_interface import UsersInterface
from interfaces.outfits_interface import OutfitsInterface
from interfaces.outfit_items_interface import OutfitItemsInterface
from services.outfit_generation_service import OutfitGenerationService
import _config as config
from clients.openai_client import get_openai_client
from clients.gemini_client import get_gemini_client

logger = logging.getLogger(__name__)
class ThreadService:
    """Simplified service for managing conversational styling threads."""
    
    def __init__(self):
        # Core thread/message management
        self.threads_interface = ThreadsInterface()
        self.messages_interface = MessagesInterface()
        self.users_interface = UsersInterface()
        self.outfits_interface = OutfitsInterface()
        self.outfit_items_interface = OutfitItemsInterface()
        # Single service that handles the full outfit flow
        self.outfit_generation_service = OutfitGenerationService()
        self.openai_client = get_openai_client()
        self.gemini_client = get_gemini_client()

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

    async def _process_single_outfit_with_callback(
        self,
        *,
        outfit: Dict[str, Any],
        register_callback: Callable[[Dict[str, Any], str], None],
        assistant_msg_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        outfit_count: int = 0,
        use_quque_multiplier: bool = True,
    ) -> None:
        """Process a single outfit and register it with the callback when complete."""
        try:
            outfit_id = await self.outfit_generation_service.process_single_outfit(
                outfit=outfit,
                assistant_msg_id=assistant_msg_id,
                thread_id=thread_id,
                outfit_count=outfit_count,
                use_quque_multiplier=use_quque_multiplier,
            )
            # Register the completed outfit with its ID
            register_callback(outfit, outfit_id)
        except Exception as e:
            logger.error(f"Failed to process outfit with callback: {e}")

    async def route_user_message(
        self, 
        thread_id: str, 
        user_message: str,
    ) -> None:
        """Main entry point for styling conversations."""
        try:

            thread = self.threads_interface.get(thread_id)
            thread_title = thread.get("title", "Thread Title")
            user_id = thread.get("user_id") if thread else None

            if not thread_title or thread_title == "Thread Title":
                asyncio.create_task(self._generate_title_task(thread_id, user_message))

            user_data = self.users_interface.get_relevant_context(user_id) if user_id else {}
            # Parse thread.research to a Python object to pass separately
            research_raw = (thread or {}).get("research") if thread else None
            thread_research_obj: Any = None
            if research_raw:
                if isinstance(research_raw, str):
                    try:
                        import json as _json
                        thread_research_obj = _json.loads(research_raw)
                    except Exception:
                        thread_research_obj = {"text": research_raw}
                elif isinstance(research_raw, dict):
                    thread_research_obj = research_raw
                else:
                    thread_research_obj = {"text": str(research_raw)}

            self.messages_interface.create(
                thread_id=thread_id,
                role="user",
                content=user_message,
            )

            conversation_history = self.messages_interface.get_conversation_history(thread_id)

            outfit_history = self.outfits_interface.get_thread_outfit_history(thread_id)

            assistant_msg_id = self.messages_interface.create(
                thread_id=thread_id,
                role="assistant",
                content="",
                metadata={
                    "type": "styling_response",
                    "model": "outfit_generation_service",
                }
            )

            use_quque_multiplier = True

            if "more outfits" in user_message.lower():
                use_quque_multiplier = False
                self.threads_interface.update_thread_outfits_with_no_message_id(thread_id, assistant_msg_id, 3)

            else:
                self.threads_interface.delete_thread_outfits_with_no_message_id(thread_id)

            queue_multiplier = config.QUEUE_MULTIPLIER if use_quque_multiplier else 1

            await self.openai_client.generate_outfits_flow(
                queue_multiplier=queue_multiplier,
                user_data=user_data,
                conversation_history=conversation_history,  
                outfit_history=outfit_history,
                thread_research=thread_research_obj,
                on_single_outfit=lambda outfit, register_callback, outfit_count: asyncio.create_task(
                    self._process_single_outfit_with_callback(
                        outfit=outfit,
                        register_callback=register_callback,
                        assistant_msg_id=assistant_msg_id,
                        thread_id=thread_id,
                        outfit_count=outfit_count,
                        use_quque_multiplier=use_quque_multiplier
                    )
                ),
                on_outfit_batch=lambda outfits, outfit_ids: self.gemini_client.launch_flatlay_task(
                    outfits=outfits,
                    outfit_ids=outfit_ids,
                    user_id=user_id,
                    thread_id=thread_id,
                ),
            )

            return {"success": True}
                
        except Exception as e:
            logger.error(f"Chat with styling failed: {e}")
            raise


