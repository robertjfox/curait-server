import json
from typing import Dict, Any, List, Tuple
from utils.outfit_utils import format_outfit_history
import _config as config
import logging

logger = logging.getLogger(__name__)

# --- Helpers (internal only) ---
def _gender_gate(user_gender: str) -> Tuple[str, str]:
    g = (user_gender or "").strip().lower()
    kw = "men's" if g == "male" else "women's" if g == "female" else "men's|women's"
    label = user_gender or "unspecified"
    return kw, label


def generate_outfit_system_prompt(num_outfits: int, user_gender: str = None, queue_multiplier: int = 1) -> str:
    gender_kw, gender_label = _gender_gate(user_gender)

    num_outfits_to_generate = num_outfits * queue_multiplier

    return (
        "You are an expert fashion stylist returning ONLY a structured function call.\n"
        "Goal: brainstorm shoppable, realistic outfits that feel fresh and wearable.\n\n"

        "PRIORITIES:\n"
        "- Fit the session context (occasion, dress code, activity, weather, mood).\n"
        "- Respect BODY_CONTEXT constraints and the user's style baseline.\n"
        "- Keep looks cohesive, practical, and non-repetitive (vs. outfit history).\n\n"

        "COMPOSITION RULES:\n"
        f"- Exactly {num_outfits_to_generate} items per outfit.\n"
        f"- Each item.type ∈ [{', '.join(config.CLOTHING_ITEMS)}]; no duplicate roles per outfit.\n"
        "- Practical combos only (e.g., no blazer+shorts; no dress+skirt together; no shorts with winter coat).\n"
        "- No HATS!. NO BELTS!. Only use an accessory if you cant think of anything else.\n"
        '- NO ACCESSORIES FOR MEN! PERIOD.'
        "- Cohesive palette and sensible layering for the weather.\n\n"

        "GENDER RULES:\n"
        f"- User gender='{gender_label}'. All items must suit this gender.\n"
        f"- Shopping keywords MUST start with '{gender_kw}'. Never include another gender.\n\n"

        "KEYWORDS FORMAT (STRICT):\n"
        f"- ORDER: 1) Gender: {gender_kw}  2) Color  3) Noun  4) Material (opt)  5) Fit (opt)\n"
        "- SPACE-DELIMITED ONLY. No commas, quotes, or special chars.\n"
        "- Use common color words (e.g., 'green' not 'sage').\n"
        "- ALWAYS include a simple color in the keywords.\n"
        "- Only gender+color+noun are required; material/fit optional and kept broad.\n"
        "- Tops: fit and sleeve length helpful (e.g., long sleeve).\n"
        "- Bottoms: fit and cut/length helpful (e.g., wide leg, cropped).\n"
        "- No brands. ~6–12 tokens total. Keep queries broad enough for search.\n"
        "- Women's keywords should be slightly more general than men's.\n\n"

        "META:\n"
        "- Provide a creative outfit name (not literal) and a one-sentence description of why it fits the context.\n"
    )


def generate_outfit_user_prompt(
    user_data: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    most_recent_message: Dict[str, Any],
    outfit_history: List[Dict[str, Any]],
    num_outfits: int,
) -> str:
    safe_user: Dict[str, Any] = user_data or {}
    profile: Dict[str, Any] = {k: v for k, v in safe_user.items() if k != "context"}
    ctx: Dict[str, Any] = safe_user.get("context") or {}
    j = lambda o: json.dumps(o or {}, separators=(",", ":"))

    return (
        f"Create {num_outfits} distinct, complete outfit(s) using the structured function.\n"
        "- If conversation/location/weather conflicts with profile, the conversation WINS.\n"
        "- Use destination from conversation for weather; profile location is just background vibe.\n"
        "- Treat profile/context as baseline for fit, proportions, coverage, comfort, colors, constraints.\n"
        "- Avoid repeating items from this thread; keep options fresh but practical.\n"
        "- Follow the MOST RECENT MESSAGE closely. This is the primary instruction.\n\n"

        "USER_PROFILE:\n" + j(profile) + "\n\n"
        "BODY_CONTEXT:\n" + j((ctx or {}).get('body_context')) + "\n\n"
        "LIFESTYLE_CONTEXT:\n" + j((ctx or {}).get('lifestyle_context')) + "\n\n"
        "STYLE_CONTEXT:\n" + j((ctx or {}).get('style_context')) + "\n\n"
        "CONVERSATION_HISTORY:\n" + j(conversation_history) + "\n\n"

        "MOST_RECENT_MESSAGE:\n" + j(most_recent_message) + "\n\n"

        "OUTFIT_HISTORY:\n" + j(format_outfit_history(outfit_history)) + "\n\n"
        "Return via the provided function schema ONLY."
    )


def format_convo_history(conversation_history: List[Dict[str, Any]]) -> str:
    """Format conversation history into a readable string, filtering out empty messages."""
    lines: List[str] = []
    
    if not conversation_history:
        return ""
    
    # Exclude the most recent message
    messages_to_process = conversation_history[:-1] if len(conversation_history) > 0 else []
    
    for msg in messages_to_process:
        role = msg.get("role", "")
        content = str(msg.get("content", "")).strip()
        
        # Skip messages with blank content
        if not content or content == "more outfits":
            continue
            
        if role == "user":
            lines.append(f"user: {content}")
        elif role == "assistant":
            lines.append(f"agent: {content}")
    
    return "\n".join(lines)


def generate_outfit_prompts(
    user_data: Dict[str, Any],
    outfit_history: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]],
    queue_multiplier: int,
) -> Tuple[str, str]:
    
    convo_history = format_convo_history(conversation_history)
    most_recent_message = conversation_history[-1] if conversation_history else None

    user_gender = (user_data or {}).get("gender")
    num_outfits = config.NUM_OUTFITS_TO_GENERATE * queue_multiplier

    system_prompt = generate_outfit_system_prompt(num_outfits, user_gender)
    user_prompt = generate_outfit_user_prompt(
        user_data, 
        convo_history,
        most_recent_message,
        outfit_history, 
        num_outfits,
    )

    # logger.info(f"🧵 System prompt: {system_prompt}")
    # logger.info(f"🧵 User prompt: {user_prompt}")

    return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
