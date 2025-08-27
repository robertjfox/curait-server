from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple
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

QUEUE_MULTIPLIER = 3
QUEUE_PULL_COUNT = 1
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

            # Non-blocking: try to generate a creative title from the first message
            asyncio.create_task(self._generate_title_task(thread_id, user_message))

            # Get user data
            thread = self.threads_interface.get(thread_id)

            # get the user data
            user_data = self.users_interface.get_relevant_context(thread["user_id"]) if thread else {}
            
            # Save user message
            self.messages_interface.create(
                thread_id=thread_id,
                role="user",
                content=user_message,
                metadata={"intent": user_intent}
            )

            conversation_history = self.messages_interface.get_conversation_history(thread_id)
            outfit_history = self.outfits_interface.get_thread_outfit_history(thread_id)

            # CREATE: add assistant message with metadata about the outfit generation
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

            # update the cache with the message id... this is all we have to do
            if "more outfits" in user_message.lower():
                use_quque_multiplier = False
                self.threads_interface.update_thread_outfits_with_no_message_id(thread_id, assistant_msg_id, QUEUE_PULL_COUNT)

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


    # -----------------------------
    # Main flow
    # -----------------------------

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
            num_outfits = config.NUM_OUTFITS_TO_GENERATE
            num_items = config.NUM_ITEMS_PER_OUTFIT

            queue_multiplier = QUEUE_MULTIPLIER if use_quque_multiplier else 1

            outfit_ids, item_db_ids = self.outfits_interface.create_outfits_and_items(
                thread_id=thread_id,
                assistant_msg_id=assistant_msg_id,
                num_outfits=num_outfits,
                num_items=num_items,
                queue_multiplier=queue_multiplier,
            )

            logger.info(f"🧵 Created {len(outfit_ids)} outfits and {len(item_db_ids)} items")

            item_ids_deque = deque(item_db_ids)

            # generate the outfits
            new_outfits = await self.openai_client.generate_outfits_flow(
                queue_multiplier=queue_multiplier,
                user_data=user_data,
                conversation_history=conversation_history,  
                outfit_history=outfit_history,      
                on_keyword=lambda kw: asyncio.create_task(
                    self.outfit_generation_service._process_single_item(
                        item_id=item_ids_deque.popleft(),
                        keywords=kw,
                        user_data=user_data,
                        thread_id=thread_id,
                    )
                ),
            )

            # update the outfits with the metadata
            self.outfits_interface.update_multiple_outfits_metadata(
                outfit_metadata=new_outfits,
                outfit_ids=outfit_ids,
                item_db_ids=item_db_ids,    
                num_items=num_items,
            )


            # Generate flatlays for current outfits (fire-and-forget)
            self.openai_client._launch_flatlay_tasks(
                new_outfits.get("outfits", []),
                thread_id=thread_id,
                outfit_ids=outfit_ids,
            )

            logger.info(f"✅ Completed styling response!")

            return new_outfits

        except Exception as e:
            logger.error(f"Failed to generate styling response: {e}")
            raise
