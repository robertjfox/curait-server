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

        "PRIORITY RULES:\n"
        "- The user's latest request is the primary source of truth for occasion, activity, weather, and formality.\n"
        "- The user's context is the taste lens: choose outfits and items that feel like this specific person would actually wear them.\n"
        "- Honor the user's fit_and_silhouette_guidance literally. If the user prefers loose, relaxed, oversized, or baggy fits, pick silhouettes that match (relaxed, oversized, wide-leg, slouchy) and reflect that in keywords. Do the same for slim/tailored preferences. Never put a loose-fit user in skinny/slim/fitted pieces.\n"
        "- Never ignore the stated activity, occasion, dress code, or setting in the latest request.\n"
        "- If style context conflicts with the latest request, adapt the user's vibe to the request instead of abandoning either one.\n"
        "- Do not make everyone generically polished or smart casual. Only use dressier pieces when the request or user context supports it.\n"
        "- For athletic or active requests (run club, gym, workout, hike, sport), create functional athletic outfits with appropriate performance pieces and footwear. Do not style them as casual cafe, office, or smart casual looks unless explicitly asked.\n\n"

        "COMPOSITION RULES:\n"
        f"- 3-5 items per outfit.\n"
        f"- Each item.type ∈ [{', '.join(config.CLOTHING_ITEMS)}]; no duplicate roles per outfit.\n"
        "- Practical combos only (e.g., no blazer+shorts; no dress+skirt together; no shorts with winter coat).\n"
        "- Cohesive palette and sensible layering for the weather.\n\n"
        "- Do not include hats, bags, jewelry, glasses, belts, or other accessories for now.\n"
        "- Focus on main clothing items and shoes.\n\n"

        "GENDER RULES:\n"
        f"- User gender='{gender_label}'. All items must suit this gender.\n"
        f"- Shopping keywords MUST start with '{gender_kw}'. Never include another gender.\n\n"

        "KEYWORDS FORMAT (STRICT):\n"
        f"- ORDER: 1) Gender: {gender_kw}  2) Color  3) Noun  4) Material (opt)  5) Fit (opt)\n"
        "- SPACE-DELIMITED ONLY. No commas, quotes, or special chars.\n"
        "- ALWAYS include a simple color in the keywords. Dont make the colors TOO SPECIFIC.\n"
        "- Color should be in the format color:navy, color:beige, color:black etc.\n"
        "- Only gender+color+noun are required; material/fit optional and kept broad.\n"
        "- Tops: fit and sleeve length helpful (e.g., relaxed long sleeve, oversized tee).\n"
        "- Bottoms: fit and cut/length helpful (e.g., wide leg, cropped, baggy, relaxed).\n"
        "- When user context specifies a fit preference, the matching fit token (e.g., relaxed, loose, oversized, baggy, slim, tailored) MUST appear in tops and bottoms keywords.\n"
        "- No brands. ~6–12 tokens total. Keep queries broad enough for search, but include natural vibe descriptors when useful.\n"

        "- DONT be vague. A jacket needs more description than just 'jacket'. A sweatshirt should be hooded, crewneck, zip etc. A shirt should be button up, t shirt, polo, etc. These are just examples. Use your BEST judgement without being TOO SPECIFIC. \n\n"
    )

def generate_outfit_user_prompt(
    user_data: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    formatted_outfit_history: str,
    num_outfits: int,
) -> str:
    
    safe_user: Dict[str, Any] = user_data or {}
    safe_user = {k: v for k, v in safe_user.items() if k in ["age", "location"]}
    ctx: Dict[str, Any] = user_data.get("context") or {}
    j = lambda o: json.dumps(o or {}, separators=(",", ":"))

    latest_user_request = ""
    for message in reversed(conversation_history or []):
        if message.get("role") == "user" and message.get("content"):
            latest_user_request = message["content"]
            break

    return (
        f"Create {num_outfits} distinct, complete outfit(s) using the structured function.\n\n"
        + f"LATEST_USER_REQUEST:\n{latest_user_request}\n\n"
        + "Treat LATEST_USER_REQUEST as mandatory for the moment being styled. "
        + "Treat USER_CONTEXT as the user's taste and vibe. It should quietly shape item choices, silhouette, formality, footwear, and palette. "
        + "Do not treat it as a checklist, but do not ignore it or default to generic outfits.\n\n"
        + f"USER_PROFILE:\n{j(safe_user)}\n\n"
        + f"USER_CONTEXT:\n{j(ctx)}\n\n"
        + f"OUTFIT_HISTORY:\n{formatted_outfit_history}\n\n"
        + ("CONVERSATION_HISTORY:\n" + j(conversation_history) + "\n\n" if conversation_history else "")
    )


def generate_outfit_prompts(
    user_data: Dict[str, Any],
    outfit_history: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]],
    double_batch: bool,
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
    )

    logger.info(f"[OPENAI] user prompt: {user_prompt}")

    return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
