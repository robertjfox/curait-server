import openai
import os
import logging
from typing import Dict, Any, List, Optional, Callable
import _config as config
import json
import httpx
from datetime import datetime, timezone
import time

# Prompts
from ai.prompts.generate_outfits import generate_outfit_prompts
from ai.prompts.product_ranking import build_product_ranking_prompt
from ai.prompts.prompt_suggestions import build_prompt_suggestions_messages

# Schemas
from ai.schemas.outfits import generate_outfit_schema
from ai.schemas.prompt_suggestions import generate_prompt_suggestions_schema

# Streaming/Parsing utils
from utils.response_handler_utils import (
    process_streaming_outfit_response,
)

# Models
from _config.model_config import (
    OUTFIT_GENERATION,
    PRODUCT_RANKING,    
    TITLE_GENERATION,       
    PROMPT_SUGGESTIONS,
)

logger = logging.getLogger(__name__)

class OpenAIClient:
    """Simple centralized OpenAI client (direct OpenAI calls; no wrappers)."""
    
    def __init__(self):
        # Configure timeout for OpenAI client using httpx.Timeout
        timeout = httpx.Timeout(
            connect=config.OPENAI_CONNECT_TIMEOUT,
            read=config.OPENAI_READ_TIMEOUT,
            write=config.OPENAI_WRITE_TIMEOUT,
            pool=config.OPENAI_POOL_TIMEOUT
        )
        
        self.client = openai.AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=timeout
        )

    async def generate_outfits_flow(
        self,
        *,
        queue_multiplier: int,
        user_data: Dict[str, Any],
        conversation_history: List[Dict[str, Any]] = [],
        outfit_history: List[Dict[str, Any]] = [],
        on_outfit_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_single_outfit: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        
        schema = generate_outfit_schema(queue_multiplier)
        messages = generate_outfit_prompts(user_data, outfit_history, conversation_history, queue_multiplier)

        start_time = time.time()

        stream = await self.client.chat.completions.create(
            model=OUTFIT_GENERATION["model"],
            messages=messages,
            response_format=schema,
            stream=True,
            stream_options={"include_usage": True},
        )

        res = await process_streaming_outfit_response(
            stream,
            on_outfit_batch=on_outfit_batch,
            on_single_outfit=on_single_outfit,
            start_time=start_time,
            grid_size=config.NUM_OUTFITS_IN_GRID,
        )

        return res

    async def rank_products_flow(
        self,
        *,
        user_data: Dict[str, Any],
        item_context: Dict[str, Any],
        num_results: int,
        grid_image_data_uri: str,
        outfit_row: Dict[str, Any],
    ) -> List[int]:
        """LLM-only ranking: builds messages + tool schema, calls model, returns ratings list."""
        messages = build_product_ranking_prompt(
            user_data=user_data,
            item_context=item_context,
            num_results=num_results,
            grid_image_data_uri=grid_image_data_uri,
            outfit_row=outfit_row,
        )

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

        resp = await self.client.chat.completions.create(
            model=PRODUCT_RANKING["model"],
            messages=messages,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "rank_products"}},
            top_p=1,
        )
        
        resp_obj = resp

        try:
            tc = resp_obj.choices[0].message.tool_calls[0]
            args = json.loads(tc.function.arguments)
            ratings = [int(x) for x in args["ratings"]]
        except Exception as e:
            raise ValueError(f"Failed to parse ratings. Raw: {resp}") from e

        return ratings

    async def generate_title_flow(self, *, first_user_message: str) -> str:
        """Return a short, creative thread title for the first user message."""
        prompt = (
            "Create a concise, catchy title (max 3-5 words) for this conversation. "
            "For context this is a AI virtual stylist application. The title should reflect the user's intent for the styling session."
            "Avoid quotes and punctuation-heavy output.\n\n"
            f"Message: {first_user_message}"
        )
        try:
            response = await self.client.chat.completions.create(
                model=TITLE_GENERATION["model"],
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content or ""
            # Sanitize line breaks / quotes
            return (content.strip().replace("\n", " ").strip().strip('"').strip("'").strip() or "New Thread")
        except Exception:
            return "New Thread"

    async def generate_prompt_suggestions(
        self,
        *,
        user_data: Dict[str, Any],
        first_messages: List[str],
        existing_prompts: List[str] = None,
    ) -> List[str]:
        """Return 4 short, one-sentence prompt suggestions tailored to the user."""
        msgs = build_prompt_suggestions_messages(user_data, first_messages, existing_prompts)
        schema = generate_prompt_suggestions_schema()
        try:
            response = await self.client.chat.completions.create(
                model=PROMPT_SUGGESTIONS["model"],
                messages=msgs,
                response_format=schema,
            )
            content = response.choices[0].message
            # Expect JSON tool output under response_format, similar to other flows
            # The AsyncOpenAI json response embeds content in message.content when using response_format
            parsed = None
            try:
                parsed = json.loads(content.content)
            except Exception:
                # Some SDKs place JSON under message.parsed if using structured mode
                parsed = getattr(content, "parsed", None)
            prompts = (parsed or {}).get("prompts") if isinstance(parsed, dict) else None
            if not prompts or not isinstance(prompts, list):
                raise ValueError("No prompts returned")
            # Sanitize and enforce length/formatting
            cleaned: List[str] = []
            for p in prompts[:4]:
                s = (p or "").strip().replace("\n", " ")
                s = s.strip('"').strip("'").strip()
                if len(s) > 75:
                    # Truncate at word boundary to avoid cutting mid-word
                    s = s[:75].rstrip()
                    # Find last space to avoid cutting mid-word
                    last_space = s.rfind(' ')
                    if last_space > 60:  # Only truncate at word boundary if we have reasonable length
                        s = s[:last_space].rstrip()
                cleaned.append(s)
            while len(cleaned) < 4:
                cleaned.append("Show me versatile outfits for this week")
            return cleaned[:4]
        except Exception as e:
            logger.warning(f"Prompt suggestions failed, falling back: {e}")
            return []


def get_openai_client() -> OpenAIClient:
    """Get an OpenAI client instance."""
    return OpenAIClient() 