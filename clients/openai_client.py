import openai
import os
import logging
from typing import Dict, Any, List, Optional, Callable, Tuple
import _config as config
import asyncio
import json
import httpx
import base64
import uuid
from PIL import Image

# Google Gemini SDK
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

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
from utils.logging.cost_tracking import cost_logger

logger = logging.getLogger(__name__)

# -----------------------------
# Flatlay image provider selection
# -----------------------------
# Allowed values: "OPENAI" or "GOOGLE" (Gemini API)
FLATLAY_IMAGE_PROVIDER = (os.getenv("FLATLAY_IMAGE_PROVIDER", "GOOGLE").strip().upper())

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
        """Dress the person in _assets/user_full_body.png with the outfit and upload the edited image. Returns the public URL or None."""
        import time
        start_time = time.time()
        outfit_name = outfit.get("name", "Unknown Outfit")
        
        try:
            # Virtual try-on prompt
            edit_prompt = (
                "Dress the person in the provided user image using ONLY the items from this outfit JSON. "
                "Ensure realistic fit, correct layering and occlusion, consistent lighting, and natural shadows. "
                "No text or logos. Keep the background and person identity the same.\n\n"
                f"Outfit JSON:\n{json.dumps(outfit, ensure_ascii=False)}"
            )

            gen_start = time.time()

            image_bytes: Optional[bytes] = None

            if FLATLAY_IMAGE_PROVIDER in ("GOOGLE", "GEMINI", "GOOGLE_GEMINI"):
                # Generate with Google Gemini 2.5 Flash Image, passing the base user image for editing
                if not GEMINI_AVAILABLE:
                    logger.error("Google Gemini SDK not available. Install with: pip install google-genai")
                    return None

                def _call_gemini_vton() -> Optional[bytes]:
                    try:
                        google_api_key = os.getenv("GOOGLE_API_KEY")
                        client = genai.Client(api_key=google_api_key)

                        user_img_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "_assets", "user_full_body.png"))
                        try:
                            base_image = Image.open(user_img_path)
                            resp = client.models.generate_content(
                                model="gemini-2.5-flash-image-preview",
                                contents=[edit_prompt, base_image],
                            )
                        except Exception:
                            # Fallback to text-only if the file isn't available
                            resp = client.models.generate_content(
                                model="gemini-2.5-flash-image-preview",
                                contents=[edit_prompt],
                            )

                        for part in resp.candidates[0].content.parts:
                            if getattr(part, "inline_data", None):
                                return part.inline_data.data
                        return None
                    except Exception as e:
                        logger.warning(f"Gemini image generation error: {e}")
                        return None

                image_bytes = await asyncio.to_thread(_call_gemini_vton)
            else:
                # OpenAI fallback: prompt-based image generation (no edit input)
                response = await self.client.images.generate(
                    model="gpt-image-1",
                    prompt=edit_prompt,
                    size="1024x1024",
                    quality="low",
                    output_format="jpeg",
                    output_compression=30,
                )
                b64 = response.data[0].b64_json if response and getattr(response, 'data', None) else None
                image_bytes = base64.b64decode(b64) if b64 else None
            
            # Track try-on generation cost (reuse flatlay tracker for now)
            cost_logger.track_flatlay_gen(thread_id)
            
            gen_time = time.time() - gen_start
            
            if not image_bytes:
                logger.warning(f"❌ No image data received for '{outfit_name}'")
                return None

            upload_start = time.time()

            # Choose filename and content-type based on bytes signature
            mime_type, ext = self._detect_image_mime_and_ext(image_bytes)
            filename = f"outfit_tryon_{uuid.uuid4().hex}{ext}"
            bucket = (config.model_config.FLATLAY_RENDERING["bucket"] if hasattr(config, 'model_config') else "outfit-flatlay-images")

            supabase = get_supabase_client()
            supabase.storage.from_(bucket).upload(
                path=filename,
                file=image_bytes,
                file_options={"content-type": mime_type},
            )
            public_url = supabase.storage.from_(bucket).get_public_url(filename)
            
            upload_time = time.time() - upload_start
            total_time = time.time() - start_time
            logger.info(f"✅ Try-on complete for '{outfit_name}': {gen_time:.2f}s gen + {upload_time:.2f}s upload = {total_time:.2f}s total")
            
            return public_url
        except Exception as e:
            total_time = time.time() - start_time
            logger.warning(f"❌ Try-on generation failed for '{outfit_name}' after {total_time:.2f}s: {e}")
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
        thread_id: Optional[str] = None,
    ) -> None:
        
        schema = generate_outfit_schema(queue_multiplier)
        messages = generate_outfit_prompts(user_data, outfit_history, conversation_history, queue_multiplier)

        stream = await self.client.chat.completions.create(
            model=OUTFIT_GENERATION["model"],
            messages=messages,
            response_format=schema,
            stream=True,
            stream_options={"include_usage": True},
        )

        outfits_full_json, usage = await process_streaming_outfit_response(
            stream,
            on_keyword=on_keyword,
        )

        # Track cost using usage from final stream chunk if available
        if usage and thread_id:
            # Create a lightweight object interface for calculate_openai_cost_cents
            class _UsageWrapper:
                def __init__(self, model: str, usage_obj: Any):
                    self.model = OUTFIT_GENERATION["model"]
                    self.usage = usage_obj
            from utils.logging.cost_tracking import cost_logger, calculate_openai_cost_cents
            wrapper = _UsageWrapper(OUTFIT_GENERATION["model"], usage)
            cents = calculate_openai_cost_cents(wrapper)
            if cents:
                cost_logger.track_outfit_gen(thread_id, cost_cents=cents)

        return outfits_full_json

    async def rank_products_flow(
        self,
        *,
        user_data: Dict[str, Any],
        item_context: Dict[str, Any],
        num_results: int,
        grid_image_data_uri: str,
        thread_id: Optional[str] = None,
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
        
        # Track ranking cost
        cost_logger.track_ranking(thread_id, response=resp)
        
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
        thread_id: Optional[str] = None,
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
        
        # Note: VTON cost tracking disabled for now as requested
        
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

    # -----------------------------
    # Internal helpers
    # -----------------------------
    # (Removed _generate_flatlay_image_bytes; generation now inlined in _generate_flatlay_and_upload)

    @staticmethod
    def _detect_image_mime_and_ext(image_bytes: bytes) -> Tuple[str, str]:
        """Best-effort sniffing of image mime and extension from header bytes."""
        if not image_bytes:
            return ("image/jpeg", ".jpg")
        header = image_bytes[:12]
        # JPEG
        if header.startswith(b"\xFF\xD8"):
            return ("image/jpeg", ".jpg")
        # PNG
        if header.startswith(b"\x89PNG"):
            return ("image/png", ".png")
        # WEBP: RIFF....WEBP
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return ("image/webp", ".webp")
        return ("image/jpeg", ".jpg")


# Convenience function


def get_openai_client() -> OpenAIClient:
    """Get an OpenAI client instance."""
    return OpenAIClient() 