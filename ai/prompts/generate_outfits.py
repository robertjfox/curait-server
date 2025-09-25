import json
from typing import Dict, Any, List, Tuple
from utils.outfit_utils import format_outfit_history
import _config as config
import logging

logger = logging.getLogger(__name__)

# --- Helpers (internal only) ---
def _gender_gate(user_gender: str) -> Tuple[str, str]:
    g = (user_gender or "").strip().lower()
    kw = "mens" if g == "male" else "womens" if g == "female" else "mens|womens"
    label = user_gender or "unspecified"
    return kw, label

def generate_outfit_system_prompt(user_gender: str = None) -> str:
    gender_kw, gender_label = _gender_gate(user_gender)

    return (
        "You are an expert fashion stylist returning ONLY a structured function call.\n"
        "Goal: brainstorm shoppable, realistic outfits that feel fresh and wearable.\n\n"

        "PRIORITIES:\n"
        "- Fit the session context (occasion, dress code, activity, weather, mood).\n"
        "- Keep looks non-repetitive (vs. outfit history).\n\n"
        "- Trend data is meant to be guiding, but always make the situational context THE MOST IMPORTANT FACTOR IN TERMS OF DIRECTION.\n\n"

        "COMPOSITION RULES:\n"
        f"- 3-5 items per outfit.\n"
        f"- Each item.type ∈ [{', '.join(config.CLOTHING_ITEMS)}]; no duplicate roles per outfit.\n"
        "- Practical combos only (e.g., no blazer+shorts; no dress+skirt together; no shorts with winter coat).\n"
        "- Cohesive palette and sensible layering for the weather.\n\n"
        "- Max 1 accessory per outfit. Accessories should be belts, glasses, bags, etc. Nothing uncommon.\n"

        "GENDER RULES:\n"
        f"- User gender='{gender_label}'. All items must suit this gender.\n"
        f"- Shopping keywords MUST start with '{gender_kw}'. Never include another gender.\n\n"

        "KEYWORDS FORMAT (STRICT):\n"
        f"- ORDER: 1) Gender: {gender_kw}  2) Color  3) Noun  4) Material (opt)  5) Fit (opt)\n"
        "- SPACE-DELIMITED ONLY. No commas, quotes, or special chars.\n"
        "- ALWAYS include a simple color in the keywords. Dont make the colors TOO SPECIFIC.\n"
        "- Color should be in the format color:navy, color:beige, color:black etc.\n"
        "- Only gender+color+noun are required; material/fit optional and kept broad.\n"
        "- Tops: fit and sleeve length helpful (e.g., long sleeve).\n"
        "- Bottoms: fit and cut/length helpful (e.g., wide leg, cropped).\n"
        "- No brands. ~6–12 tokens total. Keep queries broad enough for search.\n"

        "- DONT be vague. A jacket needs more description than just 'jacket'. A sweatshirt should be hooded, crewneck, zip etc. A shirt should be button up, t shirt, polo, etc. These are just examples. Use your BEST judgement without being TOO SPECIFIC. \n\n"
    )

def generate_outfit_user_prompt(
    user_data: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    formatted_outfit_history: str,
    num_outfits: int,
) -> str:
    safe_user: Dict[str, Any] = user_data or {}
    profile: Dict[str, Any] = {k: v for k, v in safe_user.items() if k != "context"}
    ctx: Dict[str, Any] = safe_user.get("context") or {}
    j = lambda o: json.dumps(o or {}, separators=(",", ":"))

    return (
        f"Create {num_outfits} distinct, complete outfit(s) using the structured function.\n"
        "- Avoid repeating items from this thread; keep options fresh.\n"
        "- Follow the ORIGINAL MESSAGE and MOST RECENT MESSAGE closely. This is the primary instruction.\n\n"
        "- But make sure you take into accouunt the instructions from the CONVERSATION_HISTORY.\n\n"
        "- If OUTFIT_HISTORY has feedback, use it to improve and refine the direction of the outfits.\n\n"
        "- Try to generate FRESH and TRENDY and UNIQUE outfits and ideas, not just variations of the same outfits.\n\n"
        "- If there are EXAMPLE OUTFITS, Create variations of them. \n\n"
        "- If the OUTFIT HISTORY IS EMPTY, USE THE EXACT EXAMPLE OUTFITS!!!!"

        "USER_PROFILE:\n" + j(profile) + "\n\n"

        "USER_CONTEXT:\n" + j(ctx) + "\n\n"

        "CONVERSATION_HISTORY:\n" + j(conversation_history) + "\n\n"

        "OUTFIT_HISTORY:\n" + formatted_outfit_history + "\n\n"
    )

def format_convo_history(conversation_history: List[Dict[str, Any]]) -> str:
    """Format conversation history into a readable string, filtering out empty messages."""
    lines: List[str] = []
    
    if not conversation_history:
        return ""
    
    # Process all messages except the most recent one
    messages_to_process = conversation_history[:-1] if len(conversation_history) > 1 else []
    
    counter = 1
    for msg in messages_to_process:
        role = msg.get("role", "")
        content = str(msg.get("content", "")).strip()
        
        # Skip messages with blank content or "more outfits"
        if not content or content.lower() == "more outfits":
            continue
            
        if role == "user":
            if counter == 1:
                lines.append("ORIGINAL MESSAGE")
            lines.append(f"{counter}. {content}")
            counter += 1
    
    # Add most recent message separately
    if conversation_history:
        most_recent = conversation_history[-1]
        most_recent_role = most_recent.get("role", "")
        most_recent_content = str(most_recent.get("content", "")).strip()
        
        if most_recent_role == "user" and most_recent_content and most_recent_content.lower() != "more outfits":
            if lines:
                lines.append("")
            lines.append("MOST RECENT MESSAGE:")
            lines.append(most_recent_content)
    
    return "\n".join(lines)

def generate_outfit_prompts(
    user_data: Dict[str, Any],
    outfit_history: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]],
    queue_multiplier: int,
) -> Tuple[str, str]:
    
    convo_history = format_convo_history(conversation_history)

    user_gender = (user_data or {}).get("gender")
    num_outfits = config.NUM_OUTFITS_IN_GRID * queue_multiplier

    formatted_outfit_history = format_outfit_history(outfit_history)

    system_prompt = generate_outfit_system_prompt(user_gender)
    user_prompt = generate_outfit_user_prompt(
        user_data, 
        convo_history,
        formatted_outfit_history, 
        num_outfits,
    )

    return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
