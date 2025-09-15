from __future__ import annotations
from typing import Dict, Any, Optional, List
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
        user_intent: Optional[str] = None,  
    ) -> None:
        """Main entry point for styling conversations."""
        try:

            thread = self.threads_interface.get(thread_id)
            thread_title = thread.get("title", "Thread Title")

            # if the thread has no title, or its "Thread Title" generate one
            if not thread_title or thread_title == "Thread Title":
                asyncio.create_task(self._generate_title_task(thread_id, user_message))

            user_data = self.users_interface.get_relevant_context(thread["user_id"]) if thread else {}

            self.messages_interface.create(
                thread_id=thread_id,
                role="user",
                content=user_message,
                metadata={"intent": user_intent}
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
                self.threads_interface.update_thread_outfits_with_no_message_id(thread_id, assistant_msg_id, 1)

            else:
                self.threads_interface.delete_thread_outfits_with_no_message_id(thread_id)

            await self._generate_styling_response(
                thread_id=thread_id,
                user_data=user_data,
                conversation_history=conversation_history,
                outfit_history=outfit_history,
                assistant_msg_id=assistant_msg_id,
                use_quque_multiplier=use_quque_multiplier,
            )
                
        except Exception as e:
            logger.error(f"Chat with styling failed: {e}")
            raise


    async def _generate_styling_response(
        self,
        thread_id: str,
        user_data: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        outfit_history: List[Dict[str, Any]],
        assistant_msg_id: str = None,
        use_quque_multiplier: bool = False,
    ) -> Dict[str, Any]:
        """Generate a styling response with outfits."""
        try:
            queue_multiplier = config.QUEUE_MULTIPLIER if use_quque_multiplier else 1

            res = await self.openai_client.generate_outfits_flow(
                queue_multiplier=queue_multiplier,
                user_data=user_data,
                conversation_history=conversation_history,  
                outfit_history=outfit_history,
                on_outfits=lambda outfits: asyncio.create_task(
                    self.outfit_generation_service.process_multiple_outfits(
                        outfits=outfits,
                        thread_id=thread_id,
                        user_gender=user_data.get("gender"),
                        assistant_msg_id=assistant_msg_id,
                    )
                ),
            )
                        
            return {"success": True}

        except Exception as e:
            logger.error(f"Failed to generate styling response: {e}")
            raise
