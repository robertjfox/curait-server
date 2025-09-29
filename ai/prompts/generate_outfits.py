import json
from typing import Dict, Any, List, Tuple
from utils.outfit_utils import format_outfit_history
import _config as config
import logging
from typing import Optional

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
    explore_idea_context: Optional[Dict[str, Any]] = None,
    trend_outfits_context: Optional[List[Dict[str, Any]]] = None,
) -> str:
    
    safe_user: Dict[str, Any] = user_data or {}
    # all we care about is age and location
    safe_user = {k: v for k, v in safe_user.items() if k in ["age", "location"]}
    ctx: Dict[str, Any] = user_data.get("context") or {}
    j = lambda o: json.dumps(o or {}, separators=(",", ":"))

    return (
        f"Create {num_outfits} distinct, complete outfit(s) using the structured function.\n"
        f"- Try to keep everything within the EXPLORE IDEA CONTEXT.\n"
        f"- If the OUTFIT HISTORY is empty, use the EXACT TREND OUTFIT EXAMPLES.\n\n"

        + (f"EXPLORE_IDEA_CONTEXT:\n{j(explore_idea_context)}\n\n" if explore_idea_context else "")
        + f"USER_PROFILE:\n{j(safe_user)}\n\n"
        + f"USER_CONTEXT:\n{j(ctx)}\n\n"
        + f"OUTFIT_HISTORY:\n{formatted_outfit_history}\n\n"
        + ("CONVERSATION_HISTORY:\n" + j(conversation_history) + "\n\n" if conversation_history else "")
        + (f"TREND OUTFIT EXAMPLES:\n{j(trend_outfits_context)}\n\n" if trend_outfits_context else "")
    )


def generate_outfit_prompts(
    user_data: Dict[str, Any],
    outfit_history: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]],
    double_batch: bool,
    explore_idea_context: Optional[Dict[str, Any]] = None,
    trend_outfits_context: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    
    user_gender = (user_data or {}).get("gender")
    num_outfits = config.NUM_OUTFITS_IN_GRID * (2 if double_batch else 1)

    formatted_outfit_history = format_outfit_history(outfit_history)

    system_prompt = generate_outfit_system_prompt(user_gender)
    user_prompt = generate_outfit_user_prompt(
        user_data,
        conversation_history,
        formatted_outfit_history,
        num_outfits,
        explore_idea_context,
        trend_outfits_context,
    )

    logger.info(f"[OPENAI] user prompt: {user_prompt}")

    return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
