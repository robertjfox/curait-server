from __future__ import annotations
from typing import Dict, Any, Optional, List
import logging

from interfaces.threads_interface import ThreadsInterface
from interfaces.messages_interface import MessagesInterface
from interfaces.users_interface import UsersInterface
from interfaces.outfits_interface import OutfitsInterface
from interfaces.outfit_items_interface import OutfitItemsInterface
from services.outfit_generation_service import OutfitGenerationService

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

            logger.info(f"🧵 Routing user message: {user_message}")
            logger.info(f"🧵 User intent: {user_intent}")
            logger.info(f"🧵 Outfit ID: {outfit_id}")

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
                    outfit_id=outfit_id
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
        outfit_id: Optional[str] = None
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
                    current_outfit_items=existing_items,
                    user_message=user_message,
                    user_gender=user_data.get("gender"),
                )
                
                # Apply modifications (search -> rank -> store updates)
                await self.outfit_generation_service.apply_modifications_to_existing_items(
                    outfit_id=outfit_id,
                    modified_items=modified,
                    user_data=user_data,
                    thread_id=thread_id,
                )

            else:
                # GENERATE: call LLM, parse keywords with early search
                await self.openai_client.generate_outfits_flow(
                    user_data=user_data,
                    thread_id=thread_id,
                    message_id=assistant_msg_id,
                    outfit_generation_service=self.outfit_generation_service,
                )
                

        except Exception as e:
            logger.error(f"Failed to generate styling response: {e}")
            raise
