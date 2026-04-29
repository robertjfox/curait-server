import openai
import os
import logging
from typing import Dict, Any, List, Optional, Callable
import _config as config
import json
import httpx
import time

# Prompts
from ai.prompts.generate_outfits import generate_outfit_prompts
from ai.prompts.product_ranking_binary import build_product_ranking_prompt
from ai.prompts.prompt_suggestions import build_prompt_suggestions_messages
from ai.prompts.remix_outfit import build_remix_outfit_messages

# Schemas
from ai.schemas.outfits import generate_outfit_schema
from ai.schemas.prompt_suggestions import generate_prompt_suggestions_schema
from ai.schemas.remix_outfit import generate_remix_outfit_schema

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
    STYLE_BRAND_CHIPS,
)

logger = logging.getLogger(__name__)


def model_request_options(
    model_config: Dict[str, Any],
    *,
    include_reasoning_effort: bool = True,
) -> Dict[str, Any]:
    options: Dict[str, Any] = {}
    if include_reasoning_effort and model_config.get("reasoning_effort"):
        options["reasoning_effort"] = model_config["reasoning_effort"]
    return options


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
        user_data: Dict[str, Any],
        conversation_history: List[Dict[str, Any]] = [],
        outfit_history: List[Dict[str, Any]] = [],
        on_outfit_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_single_outfit: Optional[Callable[[Dict[str, Any]], None]] = None,
        double_batch: bool,
    ) -> None:
        
        schema = generate_outfit_schema(double_batch)
        messages = generate_outfit_prompts(user_data, outfit_history, conversation_history, double_batch)

        start_time = time.time()

        stream = await self.client.chat.completions.create(
            model=OUTFIT_GENERATION["model"],
            messages=messages,
            response_format=schema,
            stream=True,
            stream_options={"include_usage": True},
            **model_request_options(OUTFIT_GENERATION),
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
        products: List[Dict[str, Any]],
        num_results: int,
        grid_image_data_uri: str,
        outfit_row: Dict[str, Any],
    ) -> List[int]:
        """LLM-only ranking: builds messages + JSON schema, calls model, returns ratings list."""
        messages = build_product_ranking_prompt(
            user_data=user_data,
            item_context=item_context,
            products=products,
            num_results=num_results,
            grid_image_data_uri=grid_image_data_uri,
            outfit_row=outfit_row,
        )

        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "rank_products",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "ratings": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0, "maximum": 3},
                            "minItems": num_results, "maxItems": num_results
                        }
                    },
                    "required": ["ratings"],
                    "additionalProperties": False,
                },
            },
        }

        resp = await self.client.chat.completions.create(
            model=PRODUCT_RANKING["model"],
            messages=messages,
            response_format=schema,
            top_p=1,
            **model_request_options(PRODUCT_RANKING),
        )
        
        resp_obj = resp

        try:
            content = resp_obj.choices[0].message.content or "{}"
            args = json.loads(content)
            ratings = [int(x) for x in args["ratings"]]
            if len(ratings) != num_results:
                raise ValueError(f"Expected {num_results} ratings, got {len(ratings)}")
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
                **model_request_options(TITLE_GENERATION),
            )
            content = response.choices[0].message.content or ""
            # Sanitize line breaks / quotes
            return (content.strip().replace("\n", " ").strip().strip('"').strip("'").strip() or "New Thread")
        except Exception:
            return "New Thread"

    async def generate_remix_outfit_flow(
        self,
        *,
        user_data: Dict[str, Any],
        existing_outfit: Dict[str, Any],
        existing_items: List[Dict[str, Any]],
        feedback: str,
    ) -> Dict[str, Any]:
        """Return one revised outfit plan with keep/change item decisions."""
        messages = build_remix_outfit_messages(
            user_data=user_data,
            existing_outfit=existing_outfit,
            existing_items=existing_items,
            feedback=feedback,
        )
        schema = generate_remix_outfit_schema()

        response = await self.client.chat.completions.create(
            model=OUTFIT_GENERATION["model"],
            messages=messages,
            response_format=schema,
            **model_request_options(OUTFIT_GENERATION),
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        if not isinstance(parsed.get("items"), list):
            raise ValueError("Remix planner returned no items")
        return parsed

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
            # Clean, split concatenations, and format prompts for consistency
            cleaned: List[str] = []

            def normalize_and_split(raw: Any) -> List[str]:
                text = str(raw or "")
                # Unify common concatenation delimiters into a single token
                delimiters = [
                    "」「",  # Japanese quote separator
                    "」 「",
                    "\n",
                    "\r",
                    " | ",
                    " • ",
                    " · ",
                ]
                for d in delimiters:
                    text = text.replace(d, "||")
                # Also split isolated Japanese quotes if model wrapped each item
                text = text.replace("「", "").replace("」", "")

                parts = []
                for piece in text.split("||"):
                    s = piece.strip().strip('"').strip("'").strip()
                    if not s:
                        continue
                    # Collapse internal whitespace
                    s = " ".join(s.split())
                    # Remove trailing punctuation that violates guidance
                    s = s.rstrip(".!?,;:").strip()
                    # Enforce max length softly
                    if len(s) > 90:
                        s = s[:90].rstrip()
                    parts.append(s)
                return parts

            for p in prompts:
                for candidate in normalize_and_split(p):
                    if candidate and candidate not in cleaned:
                        cleaned.append(candidate)

            # Ensure we return exactly 4
            if len(cleaned) < 4:
                cleaned.extend(["Show me versatile outfits for this week"] * (4 - len(cleaned)))
            return cleaned[:4]
        except Exception as e:
            logger.warning(f"Prompt suggestions failed, falling back: {e}")
            return []

    async def generate_style_brand_chips(
        self,
        *,
        gender: str,
        location: str,
        job: str | None = None,
    ) -> List[str]:
        """Generate brand chips that infer style context during onboarding."""
        fallback = [
            "Uniqlo",
            "COS",
            "J.Crew",
            "Todd Snyder",
            "Aritzia",
            "Nike",
            "Adidas",
            "Ralph Lauren",
            "Everlane",
            "Levi's",
            "Zara",
            "The Row",
        ]
        prompt = (
            "Generate exactly 18 fashion brand chips for a personal styling onboarding flow.\n"
            "The brands should infer the user's style taste. Mix accessible, mid-market, premium, "
            "streetwear, classic, and contemporary brands. Use real brand names only. "
            "No explanations, no categories, no duplicates.\n\n"
            f"Gender: {gender or 'unspecified'}\n"
            f"Location: {location or 'unspecified'}\n"
            f"Job: {job or 'unspecified'}"
        )
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "style_brand_chips",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "brands": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 18,
                            "maxItems": 18,
                        }
                    },
                    "required": ["brands"],
                    "additionalProperties": False,
                },
            },
        }

        try:
            response = await self.client.chat.completions.create(
                model=STYLE_BRAND_CHIPS["model"],
                messages=[
                    {"role": "system", "content": "You are a fashion taste profiler."},
                    {"role": "user", "content": prompt},
                ],
                response_format=schema,
                **model_request_options(STYLE_BRAND_CHIPS),
            )
            content = response.choices[0].message.content or ""
            parsed = json.loads(content)
            brands = parsed.get("brands")
            if not isinstance(brands, list):
                raise ValueError("No brands returned")

            cleaned: List[str] = []
            for brand in brands:
                value = str(brand or "").strip()
                if value and value not in cleaned:
                    cleaned.append(value)
            return (cleaned + fallback)[:18]
        except Exception as e:
            logger.warning(f"Style brand chips failed, falling back: {e}")
            return fallback

def get_openai_client() -> OpenAIClient:
    """Get an OpenAI client instance."""
    return OpenAIClient() 