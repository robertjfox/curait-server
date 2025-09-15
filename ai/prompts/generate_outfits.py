import json
from typing import Dict, Any, List, Tuple
from utils.outfit_utils import format_outfit_history
import _config as config
import os
import logging

logger = logging.getLogger(__name__)

# --- Helpers (internal only) ---
def _gender_gate(user_gender: str) -> Tuple[str, str]:
    g = (user_gender or "").strip().lower()
    kw = "men's" if g == "male" else "women's" if g == "female" else "men's|women's"
    label = user_gender or "unspecified"
    return kw, label


def _load_trend_research(user_gender: str = None) -> str:
    """Load adjacent trend research markdown based on user gender."""
    current_dir = os.path.dirname(__file__)
    
    # Determine which file to load based on gender
    g = (user_gender or "").strip().lower()
    if g == "male":
        filename = "trend_research_male.md"
    elif g == "female":
        filename = "trend_research_female.md"
    else:
        # Default to male if gender is unspecified
        filename = "trend_research_male.md"
    
    candidate_path = os.path.join(current_dir, filename)
    if os.path.exists(candidate_path):
        try:
            with open(candidate_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            logger.exception(f"Failed to read {filename}")
    return ""


def generate_outfit_system_prompt(user_gender: str = None) -> str:
    gender_kw, gender_label = _gender_gate(user_gender)

    trend_block = _load_trend_research(user_gender)
    trend_section = (
        "\nCURRENT TREND RESEARCH (GUIDANCE ONLY, NOT RULES):\n" + trend_block + "\n\n"
    ) if trend_block else ""

    return (
        "You are an expert fashion stylist returning ONLY a structured function call.\n"
        "Goal: brainstorm shoppable, realistic outfits that feel fresh and wearable.\n\n"

        + trend_section +

        "PRIORITIES:\n"
        "- Fit the session context (occasion, dress code, activity, weather, mood).\n"
        "- Keep looks non-repetitive (vs. outfit history).\n\n"
        "- Trend data is meant to be guiding, but always make the situational context THE MOST IMPORTANT FACTOR IN TERMS OF DIRECTION.\n\n"

        "COMPOSITION RULES:\n"
        f"- Exactly 4 items per outfit.\n"
        f"- Each item.type ∈ [{', '.join(config.CLOTHING_ITEMS)}]; no duplicate roles per outfit.\n"
        "- Practical combos only (e.g., no blazer+shorts; no dress+skirt together; no shorts with winter coat).\n"
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

        "- DONT be vague. A jacket needs more description than just 'jacket'. A sweatshirt should be hooded, crewneck, zip etc. A shirt should be button up, t shirt, polo, etc. These are just examples. Use your BEST judgement without being TOO SPECIFIC. \n\n"
    )


def generate_outfit_user_prompt(
    user_data: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    most_recent_message: Dict[str, Any],
    formatted_outfit_history: str,
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
        "- But make sure you take into accouunt the instructions from the CONVERSATION_HISTORY, unless the user has changed their mind.\n\n"
        "- If OUTFIT_HISTORY has feedback, use it to improve the future outfits.\n\n"

        "USER_PROFILE:\n" + j(profile) + "\n\n"

        "USER_CONTEXT:\n" + j(ctx) + "\n\n"

        "CONVERSATION_HISTORY:\n" + j(conversation_history) + "\n\n"

        "MOST_RECENT_MESSAGE:\n" + j(most_recent_message) + "\n\n"

        "OUTFIT_HISTORY:\n" + formatted_outfit_history + "\n\n"
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
    
    # filter out all the messages that are just "more outfits"
    conversation_history = [msg for msg in conversation_history if msg.get("content") != "more outfits"]

    # or if content is blank
    conversation_history = [msg for msg in conversation_history if msg.get("content") != ""]

    most_recent_message = conversation_history[-1] if conversation_history else None

    user_gender = (user_data or {}).get("gender")
    num_outfits = config.NUM_OUTFITS_IN_GRID * queue_multiplier

    formatted_outfit_history = format_outfit_history(outfit_history)

    # logger.info(f"🧵 Formatted outfit history: {formatted_outfit_history}")

    system_prompt = generate_outfit_system_prompt(user_gender)
    user_prompt = generate_outfit_user_prompt(
        user_data, 
        convo_history,
        most_recent_message,
        formatted_outfit_history, 
        num_outfits,
    )

    # logger.info(f"🧵 System prompt: {system_prompt}")
    # logger.info(f"🧵 User prompt: {user_prompt}")

    return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
