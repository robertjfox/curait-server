import openai
import os
import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable
import _config
import asyncio
import json
import httpx

# Prompts
from ai.prompts.generate_outfits import generate_outfit_system_prompt, generate_outfit_user_prompt
from ai.prompts.modify_items import generate_outfit_modification_prompt
from ai.prompts.product_ranking_binary import build_product_ranking_prompt
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

def get_product_ranking_tool(num_results: int) -> List[Dict[str, Any]]:
    return [{
  "type": "function",
  "function": {
    "name": "rank_products",
    "description": "Return 1..10 ratings for each index 0..N-1.",
    "parameters": {
      "type": "object",
      "properties": {
        "ratings": {
          "type": "array",
          "items": {"type": "integer", "minimum": 1, "maximum": 10},
          "minItems": num_results, "maxItems": num_results
        }
      },
      "required": ["ratings"],
      "additionalProperties": False
    }
  }
}]

class OpenAIClient:
    """Simple centralized OpenAI client with unified cost tracking."""
    
    def __init__(self):
        # Configure timeout for OpenAI client using httpx.Timeout
        timeout = httpx.Timeout(
            connect=_config.OPENAI_CONNECT_TIMEOUT,
            read=_config.OPENAI_READ_TIMEOUT,
            write=_config.OPENAI_WRITE_TIMEOUT,
            pool=_config.OPENAI_POOL_TIMEOUT
        )
        
        self.client = openai.AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=timeout
        )
    
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
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
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
                error_msg = str(e).lower()
                is_retryable = any(keyword in error_msg for keyword in [
                    "timeout", "connection", "peer closed", "incomplete", "network"
                ])
                
                if attempt < max_retries - 1 and is_retryable:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"OpenAI chat completion attempt {attempt + 1} failed with retryable error: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"OpenAI chat completion failed after {attempt + 1} attempts: {e}")
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
        item_db_ids: List[str],
        user_data: Dict[str, Any],
        thread_id: Optional[str] = None,
        conversation_history: List[Dict[str, Any]] = [],
        streaming_callback: Callable[[str, str], None] = None,
        outfit_history: List[Dict[str, Any]] = [],
    ) -> None:
        num_outfits = getattr(_config, "NUM_OUTFITS_TO_GENERATE", 1)
        num_items = getattr(_config, "NUM_ITEMS_PER_OUTFIT", 1)
        clothing_items = getattr(_config, "CLOTHING_ITEMS", [])
        gender = (user_data or {}).get("gender")

        # Schema + prompts
        schema = generate_outfit_schema(num_outfits, num_items, clothing_items)
        system_prompt = generate_outfit_system_prompt(num_items, clothing_items, gender)
        user_prompt = generate_outfit_user_prompt(user_data, num_outfits, conversation_history, outfit_history)

        logger.info(f"SYSTEM PROMPT: {system_prompt}")
        logger.info(f"USER PROMPT: {user_prompt}")
        
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
        original_callback = streaming_callback
        
        streaming_callback = lambda keywords, item_id: original_callback(
            item_id=item_id,
            keywords=keywords,
            user_data=user_data,
            thread_id=thread_id,
        )

        # Process stream and parse
        outfit_metadata = await process_streaming_outfit_response(
            stream_result["stream"],
            item_db_ids=item_db_ids,
            _process_single_item_cb=streaming_callback,
        )


        return outfit_metadata

    async def analyze_item_modifications_flow(
        self,
        *,
        existing_items: List[Dict[str, Any]],
        user_message: str,
        user_gender: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """LLM to propose updated search keywords per item needing modification."""
        prompt = generate_outfit_modification_prompt(existing_items, user_message, user_gender)

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
        """LLM-only ranking: builds messages + tool schema, calls model, returns ratings list."""
        # Messages (set {"detail":"low"} inside build_product_ranking_prompt)
        messages = build_product_ranking_prompt(
            user_data,
            item_context,
            num_results,
            grid_image_data_uri=grid_image_data_uri,
        )

        

        # Tool schema sized to N
        tools = [{
            "type": "function",
            "function": {
                "name": "rank_products",
                "description": "Return 1..10 ratings for each product index 0..N-1.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ratings": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1, "maximum": 10},
                            "minItems": num_results, "maxItems": num_results
                        }
                    },
                    "required": ["ratings"],
                },
            },
        }]

        resp = await self.chat_completion(
                model=PRODUCT_RANKING["model"],
                messages=messages,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "rank_products"}},
                # temperature=0,
                top_p=1,
                # max_completion_tokens = 1000,
                stream=False,
                thread_id=thread_id,
                category="ranking",
                timeout=timeout or getattr(_config, "RANKING_TIMEOUT", None),
            )
        
        resp_obj = resp["response"] if isinstance(resp, dict) and "response" in resp else resp

        try:
            tc = resp_obj.choices[0].message.tool_calls[0]
            args = json.loads(tc.function.arguments)
            ratings = [int(x) for x in args["ratings"]]
        except Exception as e:
            raise ValueError(f"Failed to parse ratings. Raw: {resp}") from e

        logger.info(f"PRODUCT RANKING RATINGS: {ratings}")
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