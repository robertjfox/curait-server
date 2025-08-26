import json
from typing import Dict, Any, List, Tuple
from utils.outfit_utils import format_outfit_history


def generate_outfit_system_prompt(num_items: int, clothing_items: List[str], user_gender: str = None) -> str:
    g = (user_gender or "").lower()
    gender_kw = "men's" if g == "male" else "women's" if g == "female" else "men's|women's"

    return (
        "You are an expert fashion stylist generating shoppable, realistic outfits via a structured function call. "
        "Users come to you because they want to brainstorm ideas for their next outfit. "
        
        "Generate outfits that:\n"
        "- Primarily suit the specified occasion, dress code, activity, weather, and mood in the SESSION CONTEXT\n"
        "- Respect the user's body type and practical constraints from BODY_CONTEXT\n"
        "- Align with their overall style and preferences\n"
        "- Create cohesive, wearable looks they'll love without being repetitive\n\n"
        "- Dont repeat items within a batch of outfits. Try to be original and not repeat from outfit history.\n"
        "- Dont be afraid to use stripes, patterns, textures if appropriate.\n"
        "- Are PRACTICAL to the context of the the user's desired input in the conversation\n\n"

        "GLOBAL RULES:\n"
        f"- Exactly {num_items} items per outfit; each item.type ∈ [{', '.join(clothing_items)}]; no duplicate roles.\n"
        "- Practical combos only (e.g., no blazer+shorts; no blazer with a special-occasion dress).\n"
        "- Cohesive palette and sensible layering for weather.\n"
        "- NO ACCESSORIES - focus only on core clothing items.\n\n"

        "GENDER RULES:\n"
        f"- Gender gate: user gender='{user_gender or 'unspecified'}'. All items must suit this gender.\n"
        f"- Shopping keywords MUST start with '{gender_kw}'.\n"
        "- Never include items intended for another gender.\n\n"

        "KEYWORDS FORMAT (CRITICAL - FOLLOW EXACTLY):\n"
        f"- ORDER: 1. Gender: {gender_kw}, 2. Color, 3. Noun, 4. Material (optional) , 5. Fit (optional), 6. Type-specific trait (optional).\n"
        "- SPACE-DELIMITED ONLY: Use spaces between words, NEVER use commas, quotes, or special characters.\n"
        "- I REPEAT - SPACE DELIMITED INDIVIDUAL WORDS. THIS IS SUPER IMPORTANT\n"
        "- Use color names that are not obscure or too specific (e.g. 'green' instead of 'sage').\n\n"
        "- Do not be TOO specific with the material, fit, or style keywords. We do not want to limit the search results."
        "- For tops, always include sleeve length\n"
        "- For bottoms, always include fit\n"
        "- No brands. ~9–12 tokens total.\n"

        "METADATA RULES:\n"
        "- Each outfit should have a creative name. Dont be too literal. Be more creative here\n"
        "- Each outfit has a description that in a single sentence or two describes why the outfit is appropriate for the conversation context\n"

        "EXAMPLE SITUATIONS (NOT EXCLUSIVE):\n"
        "- Wedding guest: Opt for breathable fabrics and lighter colors for outdoor summer or florals for a spring garden, even if user prefers darker or minimalist styles.\n"
        "- Casual party: Choose relaxed fits and comfortable materials for evening events or weather-appropriate layers for a rooftop setting, regardless of user's usual formal or sleeveless preferences.\n"
        "- Business setting: Select structured, professional pieces for formal meetings or conservative, polished looks for presentations, irrespective of user's casual or bohemian tendencies.\n"
        "- Social outings: For brunch dates, opt for approachable, comfortable styling, and for coffee dates, choose comfortable, approachable pieces, even if user leans towards high-fashion or glamorous evening wear.\n\n"
    )


def generate_outfit_user_prompt(
    user_data: Dict[str, Any],
    num_outfits: int,
    conversation_history: List[Dict[str, Any]],
    outfit_history: List[Dict[str, Any]]
) -> str:
    # Minified background to save tokens
    safe_user: Dict[str, Any] = user_data or {}
    profile: Dict[str, Any] = {k: v for k, v in safe_user.items() if k != "context"}
    ctx: Dict[str, Any] = (safe_user.get("context") or {}) if isinstance(safe_user.get("context"), dict) else {}
    j = lambda o: json.dumps(o or {}, separators=(",", ":"))

    return (
        f"Create {num_outfits} complete, distinct outfit(s) using the structured function.\n"
        "- When conversation/location/weather info conflicts with profile, the conversation (thread) WINS.\n"
        "- Use conversation-derived destination for weather, not the profile location. Profile location is just to give a vibe on where they are from.\n"
        "- Treat profile/context as baseline for fit, proportions, coverage, comfort, color lean, and constraints.\n"
        "- Avoid overfitting to past looks; keep options fresh yet appropriate.\n\n"
        "- The purpose of the outfit history is to show you what outfits we have already tried within the conversation. We want to keep it fresh each time.\n"

        "- THE USERS CONVERSATION DATA IS THE MOST IMPORTANT SOURCE OF DIRECTION FOR THE OUTFIT GENERATION. BE CREATIVE.\n"
        "- THE MOST RECENT CHAT MESSAGE IS THE DIRECTION WE NEED TO FOLLOW AS CLOSELY AS POSSIBLE.\n\n"

        "USER_PROFILE:\n" + j(profile) + "\n"
        "BODY_CONTEXT:\n" + j(ctx.get('body_context')) + "\n"
        "LIFESTYLE_CONTEXT:\n" + j(ctx.get('lifestyle_context')) + "\n"
        "STYLE_CONTEXT:\n" + j(ctx.get('style_context')) + "\n"
        "CONVERSATION_HISTORY:\n" + j(conversation_history) + "\n"
        "OUTFIT_HISTORY:\n" + j(format_outfit_history(outfit_history)) + "\n"
        "Return via the provided function schema ONLY."
    )


def generate_outfit_prompts(
    user_data: Dict[str, Any],
    num_outfits: int,
    num_items: int,
    clothing_items: List[str],
    conversation_history: List[Dict[str, Any]]
) -> Tuple[str, str]:
    user_gender = (user_data or {}).get("gender")
    system_prompt = generate_outfit_system_prompt(num_items, clothing_items, user_gender)
    user_prompt = generate_outfit_user_prompt(user_data, num_outfits, conversation_history)
    return system_prompt, user_prompt
