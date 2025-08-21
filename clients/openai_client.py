import openai
import os
import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable
import _config
import asyncio
import json

# Prompts
from ai.prompts.generate_outfits import generate_outfit_system_prompt, generate_outfit_user_prompt
from ai.prompts.modify_items import generate_outfit_modification_prompt
from ai.prompts.product_ranking import build_product_ranking_prompt
from ai.prompts.conversation_decisions import generate_outfit_decision_prompt, generate_chat_system_prompt
from ai.prompts.virtual_tryon import generate_virtual_tryon_prompt

# Schemas
from ai.schemas.outfits import generate_outfit_schema
from ai.schemas.modify_items import get_outfit_modification_schema
from ai.schemas.ranking import generate_product_ratings_schema
from ai.schemas.conversation_decision import generate_conversation_user_intent_schema

# Streaming/Parsing utils
from utils.response_handler_utils import (
    process_streaming_outfit_response,
    parse_final_outfit_json,
)

# Models
from _config.model_config import (
    OUTFIT_GENERATION,
    ITEM_MODIFICATION,
    PRODUCT_RANKING,
    CHAT_MODEL,
    CONVERSATION_DECISION,
    VIRTUAL_TRY_ON,
)

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Simple centralized OpenAI client with unified cost tracking."""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def _extract_tracking_params(self, kwargs: Dict[str, Any]) -> tuple[Optional[str], str]:
        """Extract tracking parameters from kwargs."""
        thread_id = kwargs.pop('thread_id', None)
        category = kwargs.pop('category', 'chat')
        return thread_id, category
    
    def _track_cost_safely(self, thread_id: Optional[str], category: str, response: Any) -> None:
        """Safely track OpenAI costs with error handling."""
        try:
            _config.cost_logger.track_openai(
                thread_id=thread_id,
                category=category,
                response=response
            )
        except Exception as e:
            logger.warning(f"Failed to log OpenAI cost: {e}")
    
    async def _make_openai_call(
        self, 
        openai_method: Callable[..., Awaitable[Any]], 
        operation_name: str,
        default_category: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Generic method to make OpenAI calls with unified error handling and cost tracking."""
        try:
            # Extract tracking parameters
            thread_id, category = self._extract_tracking_params(kwargs)
            if category == 'chat':  # Use default category if still default
                category = default_category
            
            # Make the OpenAI call
            response = await openai_method(**kwargs)
            
            # Track cost
            self._track_cost_safely(thread_id, category, response)
            
            return {"response": response}
            
        except Exception as e:
            logger.error(f"OpenAI {operation_name} failed: {e}")
            raise

    async def chat_completion(self, **kwargs) -> Dict[str, Any]:
        """Make a chat completion call with cost tracking."""
        try:
            # Extract tracking parameters
            thread_id, category = self._extract_tracking_params(kwargs)
            stream = kwargs.pop('stream', False)
            
            if stream:
                # Return streaming response without cost tracking (tracked elsewhere)
                response = await self.client.chat.completions.create(stream=True, **kwargs)
                return {
                    "stream": response,
                    "thread_id": thread_id,
                    "category": category
                }
            else:
                # Normal non-streaming response
                response = await self.client.chat.completions.create(**kwargs)
                
                # Track cost
                self._track_cost_safely(thread_id, category, response)
                
                return {
                    "content": response.choices[0].message.content or "",
                    "response": response,
                }
                
        except Exception as e:
            logger.error(f"OpenAI chat completion failed: {e}")
            raise
    
    async def image_edit(self, **kwargs) -> Dict[str, Any]:
        """Make an image edit call with cost tracking."""
        return await self._make_openai_call(
            self.client.images.edit,
            "image edit",
            "image_edit",
            **kwargs
        )

    # -----------------------------
    # High-level flows (simple APIs)
    # -----------------------------

    async def generate_outfits_flow(
        self,
        *,
        user_data: Dict[str, Any],
        thread_id: Optional[str] = None,
        message_id: Optional[str] = None,
        outfit_generation_service: Any = None,
    ) -> None:
        """End-to-end outfit generation with streaming, JSON parsing, and struct formatting."""

        num_outfits = getattr(_config, "NUM_OUTFITS_TO_GENERATE", 1)
        num_items = getattr(_config, "NUM_ITEMS_PER_OUTFIT", 1)

        logger.info(f"🔍 Generating outfits for thread {thread_id}")
        logger.info(f"🔍 User data: {user_data}")
        logger.info(f"🔍 Num outfits: {num_outfits}")
        logger.info(f"🔍 Num items: {num_items}")
        logger.info(f"🔍 Message ID: {message_id}")

        # Create blank DB records upfront to get IDs
        item_db_ids: Dict[str, str] = {}

        for outfit_num in range(1, num_outfits + 1):
            logger.info(f"🔧 Creating outfit {outfit_num} for message {message_id}")
            outfit_id = outfit_generation_service.outfits_interface.create(
                message_id=message_id,
                name="",
                description=""
            )
            
            if not outfit_id:
                logger.error(f"❌ Failed to create outfit {outfit_num} - outfit_id is None")
                continue
                
            logger.info(f"✅ Created outfit {outfit_num} with ID: {outfit_id}")
            
            for item_num in range(1, num_items + 1):
                logger.debug(f"🔧 Creating item {item_num} for outfit {outfit_id}")
                item_id = outfit_generation_service.outfit_items_interface.create(
                    outfit_id=outfit_id,
                    type="unknown",
                    keywords=""
                )   

                if not item_id:
                    logger.error(f"❌ Failed to create item {item_num} for outfit {outfit_id} - item_id is None")
                    continue
                    
                logger.debug(f"✅ Created item {item_num} with ID: {item_id}")
                item_db_ids[f"outfit_{outfit_num}:item_{item_num}"] = item_id

        logger.info(f"📊 Created {len(item_db_ids)} outfit items total: {list(item_db_ids.keys())}")
        
        if not item_db_ids:
            logger.error("❌ No outfit items were created successfully - aborting outfit generation")
            return

        # Schema + prompts
        schema = generate_outfit_schema(num_outfits, num_items, getattr(_config, "CLOTHING_ITEMS", []))
        system_prompt = generate_outfit_system_prompt(num_items, getattr(_config, "CLOTHING_ITEMS", []), (user_data or {}).get("gender"))
        user_prompt = generate_outfit_user_prompt(user_data, num_outfits)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # OpenAI (streaming)
        stream_result = await self.chat_completion(
            model=OUTFIT_GENERATION["model"],
            messages=messages,
            response_format=schema,
            thread_id=thread_id,
            category="outfit_generation",
            stream=True,
        )

        # Create early search callback with item IDs if we have them
        early_search_callback = lambda keywords: outfit_generation_service.process_keywords_with_item_ids(
            item_db_ids=item_db_ids,
            keywords=keywords,
            user_data=user_data,
            thread_id=thread_id,
        )

        # Process stream and parse
        full_content = await process_streaming_outfit_response(
            stream_result["stream"],
            num_outfits,
            num_items,
            early_search_callback=early_search_callback,
        )

        outfits_data = parse_final_outfit_json(full_content)

        await outfit_generation_service.update_outfits_with_final_data(
            item_db_ids=item_db_ids,
            parsed_outfits=outfits_data
        )

    async def analyze_item_modifications_flow(
        self,
        *,
        current_outfit_items: List[Dict[str, Any]],
        user_message: str,
        user_gender: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """LLM to propose updated search keywords per item needing modification."""
        prompt = generate_outfit_modification_prompt(current_outfit_items, user_message, user_gender)

        result = await self.chat_completion(
            model=ITEM_MODIFICATION["model"],
            messages=[{"role": "user", "content": prompt}],
            response_format=get_outfit_modification_schema(),
            thread_id=None,
            category="item_modification",
        )

        modification_data = json.loads(result["content"]) if result.get("content") else {}

        modifications = modification_data.get("modifications", [])

        modified_items: List[Dict[str, Any]] = []

        for mod in modifications:
            item_type = mod.get("type", "")
            new_keywords = mod.get("new_keywords", "")
            reasoning = mod.get("reasoning", "")
            modified_items.append({
                "type": item_type,
                "keywords": new_keywords,
                "search_results": [],
                "modification_reasoning": reasoning,
            })
            
        return modified_items

    async def rank_products_flow(
        self,
        *,
        user_data: Dict[str, Any],
        item_context: Dict[str, Any],
        num_results: int,
        grid_image_data_uri: str,
        thread_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> List[int]:
        """LLM-only ranking: builds messages + schema, calls model, returns ratings list."""
        messages = build_product_ranking_prompt(
            user_data,
            item_context,
            num_results,
            grid_image_data_uri=grid_image_data_uri,
        )
        response_schema = generate_product_ratings_schema(num_results)

        coro = self.chat_completion(
            model=PRODUCT_RANKING["model"],
            messages=messages,
            response_format=response_schema,
            thread_id=thread_id,
            category="ranking",
            timeout=timeout or getattr(_config, "RANKING_TIMEOUT", None),
        )
        result = await (asyncio.wait_for(coro, timeout=timeout) if timeout else coro)

        text = result.get("content", "")
        try:
            data = json.loads(text)
        except Exception:
            import re
            m = re.search(r"\{.*\}", text, re.DOTALL)
            data = json.loads(m.group(0)) if m else None
        if not isinstance(data, dict) or not isinstance(data.get("ratings"), list):
            raise ValueError("Failed to parse ratings from ranking response")
        ratings = [int(x) for x in data["ratings"]]
        if len(ratings) != num_results:
            raise ValueError("Ratings length mismatch")
        return ratings

    async def generate_chat_response_flow(
        self,
        *,
        conversation_history: List[Dict[str, str]],
        user_data: Dict[str, Any],
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        system_prompt = generate_chat_system_prompt(user_data, {})
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history[-10:])
        result = await self.chat_completion(
            model=CHAT_MODEL["model"],
            messages=messages,
            thread_id=thread_id,
            category="thread_chat",
        )
        return {"content": result.get("content", ""), "model": CHAT_MODEL["model"]}

    async def conversation_user_intent_flow(
        self,
        *,
        user_message: str,
        conversation_history: List[Dict[str, str]],
    ) -> str:

        recent_messages = conversation_history[-5:] if conversation_history else []
        prompt = generate_outfit_decision_prompt(user_message, recent_messages, {})
        result = await self.chat_completion(
            model=CONVERSATION_DECISION["model"],
            messages=[{"role": "user", "content": prompt}],
            response_format=generate_conversation_user_intent_schema(),
            thread_id=None,
            category="conversation_decision",
        )
        try:
            decision_data = json.loads(result.get("content", "{}"))
            return decision_data.get("decision", "CHAT")
        except Exception:
            return "CHAT"

    async def virtual_tryon_flow(
        self,
        *,
        image: Any,
        gender: Optional[str] = None,
        user_data: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
    ) -> Any:
        """Build prompt and call image edit API for virtual try-on. Returns raw API response for caller to process image bytes/URL."""
        prompt = generate_virtual_tryon_prompt(
            gender=(gender or "female"),
            user_data=user_data,
        )
        result = await self.image_edit(
            model=VIRTUAL_TRY_ON["model"],
            image=image,
            prompt=prompt,
            size=VIRTUAL_TRY_ON["size"],
            quality=VIRTUAL_TRY_ON["quality"],
            input_fidelity=VIRTUAL_TRY_ON["input_fidelity"],
            n=VIRTUAL_TRY_ON["n"],
            thread_id=thread_id,
            category="vton",
        )
        return result["response"]


# Convenience function
def get_openai_client() -> OpenAIClient:
    """Get an OpenAI client instance."""
    return OpenAIClient() 