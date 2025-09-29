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

# Schemas
from ai.schemas.outfits import generate_outfit_schema, generate_single_outfit_schema, generate_trend_outfit_analysis_schema
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
    THREAD_RESEARCH,
    EXPLORE_IDEAS,
    TREND_OUTFIT_VARIATIONS,        
)

from ai.prompts.explore_ideas import (
    build_explore_ideas_input,
    build_trend_outfit_variation_prompt,
    build_trend_outfit_analysis_messages,
)
from ai.schemas.explore_ideas import generate_explore_ideas_schema

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
        user_data: Dict[str, Any],
        conversation_history: List[Dict[str, Any]] = [],
        outfit_history: List[Dict[str, Any]] = [],
        explore_idea_context: Optional[Dict[str, Any]] = None,
        trend_outfits_context: Optional[List[Dict[str, Any]]] = None,
        on_outfit_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_single_outfit: Optional[Callable[[Dict[str, Any]], None]] = None,
        double_batch: bool,
    ) -> None:
        
        schema = generate_outfit_schema(double_batch)
        messages = generate_outfit_prompts(user_data, outfit_history, conversation_history, double_batch, explore_idea_context, trend_outfits_context)

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

    async def generate_trend_outfit_variations(
        self,
        *,
        gender: str,
        explore_title: str,
        explore_description: str,
        base_outfit_items: List[Dict[str, str]],
        desired_count: int,
        previous_outfit_variations: List[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate additional trend outfit variations aligned with an explore idea."""

        messages = build_trend_outfit_variation_prompt(
            gender=gender,
            explore_title=explore_title,
            explore_description=explore_description,
            base_outfit_items=base_outfit_items,
            desired_count=desired_count,
            previous_outfit_variations=previous_outfit_variations,
        )

        logger.info(f"[OPENAI] trend outfit variation messages: {messages}")

        schema = generate_outfit_schema(double_batch=False, num_outfits_override=desired_count)

        try:
            response = await self.client.chat.completions.create(
                model=TREND_OUTFIT_VARIATIONS["model"],
                messages=messages,
                response_format=schema,
            )
        except Exception as e:
            logger.error(f"[OPENAI] trend outfit variation request failed: {e}")
            return []

        try:
            content = (response.choices[0].message.content or "").strip()
            payload = json.loads(content)

            logger.info(f"[OPENAI] trend outfit variation response: {payload}")

            outfits = payload.get("outfits") or []
            if len(outfits) > desired_count:
                outfits = outfits[:desired_count]
            return outfits
        except Exception as e:
            logger.error(f"[OPENAI] failed to parse variation response: {e}")
            return []

    async def analyze_trend_outfit_image(
        self,
        *,
        image_url: str,
    ) -> Dict[str, Any] | None:
        """Use GPT vision model to extract outfit data from a reference image."""

        messages = build_trend_outfit_analysis_messages(image_url=image_url)
        schema = generate_trend_outfit_analysis_schema()

        try:
            response = await self.client.chat.completions.create(
                model=TREND_OUTFIT_VARIATIONS["model"],
                messages=messages,
                response_format=schema,
            )
        except Exception as e:
            logger.error(f"[OPENAI] trend outfit analysis failed: {e}")
            return None

        try:
            content = (response.choices[0].message.content or "").strip()
            payload = json.loads(content)
            return payload
        except Exception as e:
            logger.error(f"[OPENAI] failed to parse trend outfit analysis: {e}")
            return None

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
                "description": "Return 0..1 ratings for each product index 0..N-1.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ratings": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0, "maximum": 1},
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

    async def generate_thread_research(
        self,
        *,
        user_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Produce concise, wearable-oriented research for this user/session.

        Returns a JSON-friendly dict. If model doesn't return JSON, falls back to {"text": str}.
        """
        profile = {k: v for k, v in (user_data or {}).items() if k != "context"}
        ctx = (user_data or {}).get("context") or {}

        instructions = (
            "You are an expert fashion trend analyst and stylist. Create comprehensive style guidance that balances current trends with the user's personal context. "
            "Focus on what's trending now in 2025 while considering what the user would realistically wear and feel confident in. "
            "Include both mainstream and emerging trends, but filter them through the user's lifestyle and preferences.\n\n"
            "Respond ONLY as strict JSON with keys: {\n"
            "  \"wear_vibes\": [short strings],             // trending style directions and aesthetics to explore\n"
            "  \"workhorse_items\": [short strings],        // reliable trending pieces they will actually wear\n"
            "  \"no_gos\": [short strings],                 // trends to avoid due to fit, climate, or lifestyle constraints\n"
            "  \"colors\": [short strings],                 // trending color palettes and seasonal hues\n"
            "  \"fit_notes\": [short strings],              // current silhouette trends, proportions, and styling approaches\n"
            "  \"trends_quicktake\": [short strings]        // key 2025 fashion trends that align with their profile\n"
            "}"
        )

        messages = [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": json.dumps({
                    "profile": profile,
                    "context": ctx,
                }, separators=(",", ":")),
            },
        ]

        try:
            response = await self.client.chat.completions.create(
                model=THREAD_RESEARCH["model"],
                messages=messages,
                top_p=1,
            )
            content = (response.choices[0].message.content or "").strip()
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            # Fallback to text blob
            return {"text": content}
        except Exception as e:
            logger.warning(f"Thread research generation failed: {e}")
            return {"text": ""}

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

    async def generate_explore_ideas(self, *, gender: str, outfit_items: List[Dict[str, str]], source_img_url: str = None) -> Dict[str, Any]:
        """Generate a simple explore idea title and description from outfit items."""
        from datetime import datetime
        
        prompt = build_explore_ideas_input(
            gender=gender,
            date_iso=datetime.now().isoformat(),
            outfit_items=outfit_items,
            source_img_url=source_img_url,
        )

        try:
            # Handle both string and list formats for messages
            messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt

            response = await self.client.chat.completions.create(
                model=EXPLORE_IDEAS["model"],
                messages=messages,
                response_format=generate_explore_ideas_schema(),
            )
            
            content = (response.choices[0].message.content or "").strip()
            return json.loads(content) or None
            
        except Exception as e:
            logger.warning(f"[EXPLORE_IDEA] failed to generate explore ideas: {e}")
            return None

def get_openai_client() -> OpenAIClient:
    """Get an OpenAI client instance."""
    return OpenAIClient() 