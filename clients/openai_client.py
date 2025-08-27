import openai
import os
import logging
from typing import Dict, Any, List, Optional, Callable
import _config as config
import asyncio
import json
import httpx
import base64
import uuid

# Prompts
from ai.prompts.generate_outfits import generate_outfit_prompts
from ai.prompts.product_ranking_binary import build_product_ranking_prompt
from ai.prompts.conversation_decisions import generate_outfit_decision_prompt, generate_chat_system_prompt
from ai.prompts.virtual_tryon import generate_virtual_tryon_prompt

# Schemas
from ai.schemas.outfits import generate_outfit_schema
from ai.schemas.conversation_decision import generate_conversation_user_intent_schema

# Streaming/Parsing utils
from utils.response_handler_utils import (
    process_streaming_outfit_response,
)

# Models
from _config.model_config import (
    OUTFIT_GENERATION,
    PRODUCT_RANKING,
    CHAT_MODEL,
    CONVERSATION_DECISION,
    VIRTUAL_TRY_ON,
    TITLE_GENERATION,       
)
from clients.supabase_client import get_supabase_client
from interfaces.outfits_interface import OutfitsInterface

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

    # -----------------------------
    # Flatlay rendering helpers (non-blocking)
    # -----------------------------

    async def _generate_flatlay_and_upload(self, outfit: Dict[str, Any], *, thread_id: Optional[str] = None) -> Optional[str]:
        """Generate a flatlay image for a single outfit and upload it. Returns the public URL or None."""
        import time
        start_time = time.time()
        outfit_name = outfit.get("name", "Unknown Outfit")
        
        try:
            prompt = (
                "Create a high-quality, photorealistic flatlay image on a clean white background. "
                "Arrange the outfit items aesthetically with subtle, natural shadows and no text. "
                "Really try to fit everything in the frame. You can overlap items slightly, but not too much."
                "Use only the items listed. If colors or materials are specified, respect them.\n\n"
                f"Outfit JSON:\n{json.dumps(outfit, ensure_ascii=False)}"
            )

            gen_start = time.time()
            
            # Call OpenAI directly
            response = await self.client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1024",
                quality="low",
                output_format="jpeg",
                output_compression=40,
            )
            
            gen_time = time.time() - gen_start
            
            b64 = response.data[0].b64_json if response and getattr(response, 'data', None) else None
            if not b64:
                logger.warning(f"❌ No image data received for '{outfit_name}'")
                return None
            image_bytes = base64.b64decode(b64)

            upload_start = time.time()
            filename = f"outfit_flatlay_{uuid.uuid4().hex}.jpg"
            bucket = (config.model_config.FLATLAY_RENDERING["bucket"] if hasattr(config, 'model_config') else "outfit-flatlay-images")

            supabase = get_supabase_client()
            supabase.storage.from_(bucket).upload(
                path=filename,
                file=image_bytes,
                file_options={"content-type": "image/jpeg"},
            )
            public_url = supabase.storage.from_(bucket).get_public_url(filename)
            
            upload_time = time.time() - upload_start
            total_time = time.time() - start_time
            logger.info(f"✅ Flatlay complete for '{outfit_name}': {gen_time:.2f}s gen + {upload_time:.2f}s upload = {total_time:.2f}s total")
            
            return public_url
        except Exception as e:
            total_time = time.time() - start_time
            logger.warning(f"❌ Flatlay generation failed for '{outfit_name}' after {total_time:.2f}s: {e}")
            return None

    def _launch_flatlay_tasks(
        self,
        outfits: List[Dict[str, Any]],
        *,
        thread_id: Optional[str] = None,
        outfit_ids: Optional[List[str]] = None,
    ) -> List[asyncio.Task]:
        """Spawn background tasks to render flatlays for outfits. Updates JSON and DB when available. Returns task handles."""
        outfits_interface = OutfitsInterface()

        async def _task(ix: int, outfit: Dict[str, Any], outfit_id: Optional[str]) -> None:
            try:
                url = await self._generate_flatlay_and_upload(outfit, thread_id=thread_id)
                if not url:
                    return
                # Update in-memory structure
                outfit["default_rendering_url"] = url
                # Persist if we have an outfit_id
                if outfit_id:
                    try:
                        outfits_interface.update_default_rendering_url(outfit_id, url)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Flatlay task error for outfit {ix}: {e}")

        tasks: List[asyncio.Task] = []
        for i, outfit in enumerate(outfits):
            oid = outfit_ids[i] if outfit_ids and i < len(outfit_ids) else None
            tasks.append(asyncio.create_task(_task(i, outfit, oid)))
        return tasks

    # -----------------------------
    # High-level flows (simple APIs)
    # -----------------------------

    async def generate_outfits_flow(
        self,
        *,
        queue_multiplier: int,
        user_data: Dict[str, Any],
        conversation_history: List[Dict[str, Any]] = [],
        outfit_history: List[Dict[str, Any]] = [],
        on_keyword: Optional[Callable[[str], Any]] = None,
    ) -> None:
        
        schema = generate_outfit_schema(queue_multiplier)
        messages = generate_outfit_prompts(user_data, outfit_history, conversation_history, queue_multiplier)

        stream = await self.client.chat.completions.create(
            model=OUTFIT_GENERATION["model"],
            messages=messages,
            response_format=schema,
            stream=True,
        )

        outfits_full_json = await process_streaming_outfit_response(
            stream,
            on_keyword=on_keyword,
        )

        return outfits_full_json

    async def rank_products_flow(
        self,
        *,
        user_data: Dict[str, Any],
        item_context: Dict[str, Any],
        num_results: int,
        grid_image_data_uri: str,
    ) -> List[int]:
        """LLM-only ranking: builds messages + tool schema, calls model, returns ratings list."""
        messages = build_product_ranking_prompt(
            user_data,
            item_context,
            num_results,
            grid_image_data_uri=grid_image_data_uri,
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

    async def generate_chat_response_flow(
        self,
        *,
        conversation_history: List[Dict[str, str]],
        user_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        system_prompt = generate_chat_system_prompt(user_data, {})
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history[-10:])
        response = await self.client.chat.completions.create(
            model=CHAT_MODEL["model"],
            messages=messages,
        )
        return {"content": (response.choices[0].message.content or ""), "model": CHAT_MODEL["model"]}

    async def conversation_user_intent_flow(
        self,
        *,
        user_message: str,
        conversation_history: List[Dict[str, str]],
    ) -> str:
        recent_messages = conversation_history[-5:] if conversation_history else []
        prompt = generate_outfit_decision_prompt(user_message, recent_messages, {})
        result = await self.client.chat.completions.create(
            model=CONVERSATION_DECISION["model"],
            messages=[{"role": "user", "content": prompt}],
            response_format=generate_conversation_user_intent_schema(),
        )
        try:
            decision_data = json.loads((result.choices[0].message.content or "{}"))
            return decision_data.get("decision", "CHAT")
        except Exception:
            return "CHAT"

    async def virtual_tryon_flow(
        self,
        *,
        image: Any,
        gender: Optional[str] = None,
        user_data: Optional[Dict[str, Any]] = None, 
    ) -> Any:
        """Build prompt and call image edit API for virtual try-on. Returns raw API response for caller to process image bytes/URL."""
        prompt = generate_virtual_tryon_prompt(
            gender=(gender or "female"),
            user_data=user_data,
        )
        response = await self.client.images.edit(
            model=VIRTUAL_TRY_ON["model"],
            image=image,
            prompt=prompt,
            size=VIRTUAL_TRY_ON["size"],
            quality=VIRTUAL_TRY_ON["quality"],
            input_fidelity=VIRTUAL_TRY_ON["input_fidelity"],
            n=VIRTUAL_TRY_ON["n"],
        )
        return response

    async def generate_title_flow(self, *, first_user_message: str) -> str:
        """Return a short, creative thread title for the first user message."""
        prompt = (
            "Create a concise, catchy title (max 3-5 words) for this conversation. "
            "For context this is a AI virtual stylist application. The title should relect that."
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
            return (content.strip().replace("\n", " ").strip().strip('"').strip("'") or "New Thread")
        except Exception:
            return "New Thread"


# Convenience function

def get_openai_client() -> OpenAIClient:
    """Get an OpenAI client instance."""
    return OpenAIClient() 