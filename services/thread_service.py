from __future__ import annotations
from typing import Dict, Any, Optional, List
import logging

from interfaces.threads_interface import ThreadsInterface
from interfaces.messages_interface import MessagesInterface
from interfaces.users_interface import UsersInterface
from interfaces.outfits_interface import OutfitsInterface
from interfaces.outfit_items_interface import OutfitItemsInterface
from services.outfit_generation_service import OutfitGenerationService
import _config
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

    async def route_user_message(
        self, 
        thread_id: str, 
        user_message: str,
        user_intent: Optional[str] = None,
        outfit_id: Optional[str] = None
    ) -> None:
        """Main entry point for styling conversations."""
        try:

            outfit_id_short = outfit_id[:8] if outfit_id else None
            logger.info(f"🧵 User intent: {user_intent}, Outfit ID: {outfit_id_short}")

            # Get user data
            thread = self.threads_interface.get(thread_id)
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
            logger.info(f"CONVERSATION HISTORY: {conversation_history}")

            # Determine intent if not provided
            if not user_intent:
                user_intent = await self.openai_client.conversation_user_intent_flow(
                    user_message=user_message,
                    conversation_history=conversation_history,
                )

            # Generate styling response
            if user_intent in ["GENERATE", "MODIFICATION"]:
                await self._generate_styling_response(
                    thread_id=thread_id,
                    user_data=user_data,
                    user_intent=user_intent,
                    user_message=user_message,
                    conversation_history=conversation_history,
                    outfit_history=outfit_history,
                    outfit_id=outfit_id,    
                )
                
            else:
                # Handle other intents (GENERAL_CHAT, etc.)
                response = await self.openai_client.generate_chat_response_flow(
                    user_data=user_data,
                    conversation_history=conversation_history,
                    thread_id=thread_id,
                )
                
                self.messages_interface.create(
                    thread_id=thread_id,
                    role="assistant",
                    content=response.get("content", ""),
                    metadata={"type": "general_chat"}
                )
                
        except Exception as e:
            logger.error(f"Chat with styling failed: {e}")
            raise

    async def _generate_styling_response(
        self,
        thread_id: str,
        user_data: Dict[str, Any],
        user_intent: str,
        user_message: str,
        conversation_history: List[Dict[str, Any]],
        outfit_history: List[Dict[str, Any]],
        outfit_id: Optional[str] = None,    
    ) -> Dict[str, Any]:
        """Generate a styling response with outfits."""
        try:
            # Add assistant message with metadata about the outfit generation
            assistant_msg_id = self.messages_interface.create(
                thread_id=thread_id,
                role="assistant",
                content="",
                metadata={
                    "type": "styling_response",
                    "model": "outfit_generation_service",
                    "is_modification": user_intent == "MODIFICATION" 
                }
            )

            if user_intent == "MODIFICATION":
                # Existing items for mapping
                existing_items = self.outfit_items_interface.get_by_outfit(outfit_id) if outfit_id else []
                
                # Get minimal modification keywords from LLM
                modified = await self.openai_client.analyze_item_modifications_flow(
                    existing_items=existing_items,
                    user_message=user_message,
                    user_gender=user_data.get("gender"),
                )

                logger.info(f"🧵 Modified items: {modified}")
                
                # Apply modifications (search -> rank -> store updates)
                await self.outfit_generation_service.apply_modifications_to_existing_items(
                    existing_items=existing_items,
                    modified_items=modified,
                    user_data=user_data,
                    thread_id=thread_id,
                )

            else:

                num_outfits = getattr(_config, "NUM_OUTFITS_TO_GENERATE", 1)
                num_items = getattr(_config, "NUM_ITEMS_PER_OUTFIT", 1)

                item_db_ids: List[str] = []
                outfit_ids: List[str] = []

                # Create outfits
                for _ in range(num_outfits):
                    outfit_id = self.outfits_interface.create(
                        message_id=assistant_msg_id,
                        name="",
                        description=""
                    )
                    outfit_ids.append(outfit_id)
                                
                    for _ in range(num_items):
                        item_id = self.outfit_items_interface.create(
                            outfit_id=outfit_id,
                            type="unknown",
                            keywords=""
                        )   

                        item_db_ids.append(item_id)

                # GENERATE: call LLM, parse keywords with early search
                outfit_metadata = await self.openai_client.generate_outfits_flow(
                    item_db_ids=item_db_ids,
                    user_data=user_data,    
                    thread_id=thread_id,
                    conversation_history=conversation_history,
                    outfit_history=outfit_history,
                    streaming_callback=self.outfit_generation_service._process_single_item,
                )

                # Check if outfit_metadata is valid
                if not outfit_metadata or not isinstance(outfit_metadata, dict):
                    logger.error(f"Invalid outfit_metadata received: {outfit_metadata}")
                    raise ValueError("Failed to generate valid outfit metadata")

                # outfits is top level keys in outfit_metadata
                outfit_keys = outfit_metadata.keys()
                outfits = [outfit_metadata[key] for key in outfit_keys]

                # use enumerate to get the index of the outfit
                for index, outfit in enumerate(outfits):
                    outfit_id = outfit_ids[index]
                    self.outfits_interface.update_outfit_metadata(
                        outfit_id=outfit_id,
                        name=outfit.get("name", ""),
                        description=outfit.get("description", ""),
                    )

                    # item key is like item_1, item_2, etc. inside of each outfit
                    # so i think we can just take the keys without name and description
                    item_keys = outfit.keys()
                    item_keys = [key for key in item_keys if key not in ["name", "description"]]
                    items = [outfit[key] for key in item_keys]

                    # item_id is from item_db_ids, calculate outfit index above with index + 1
                    item_ids = [item_db_ids[index * num_items + i] for i in range(num_items)]

                    for item_index, item in enumerate(items):
                        self.outfit_items_interface.update(
                            item_id=item_ids[item_index],
                            type=item.get("type", ""),
                            keywords=item.get("keywords", ""),
                        )

        except Exception as e:
            logger.error(f"Failed to generate styling response: {e}")
            raise
