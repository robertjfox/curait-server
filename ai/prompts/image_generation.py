import json
from typing import List, Dict, Any, Optional


# Toggle for background rendering in flatlay images
USE_CONTEXTUAL_BACKGROUNDS = False


def create_flatlay_prompt(outfits: List[Dict[str, Any]]) -> str:
    """Create a prompt for flatlay image generation with multiple outfits."""
    
    
    # Background-specific instructions
    if USE_CONTEXTUAL_BACKGROUNDS:
        background_instruction = """
        And provide individual background that fits the vibe of each outfit and is not distracting.
        The background should a scene that the user fits into naturally, not something that is contrived or abstract.
        Do not make the background or the lighting of the image too dark or too light.
        """
    else:
        background_instruction = "Use a clean, all white background for each outfit."
    
    # Combine all outfits into a single prompt
    combined_prompt = f"""
    Dress the avatars in the following outfits from left to right.
    {background_instruction}
    Keep each avatars body proportions EXACTLY as they are now, do not increase the height.
    You may slightly change the body positioning to give a bit of movement, like in a model photoshoot.
    The user should be looking directly at the camera. KEEP A HIGH FIDELITY OF THE USER'S FACE.
    Keep a bold red line between each cell.
    NEVER include any text in the image.
    """
    
    # Add outfit details
    for i, outfit in enumerate(outfits):
        combined_prompt += f"Outfit {i+1}:\n{json.dumps(outfit, ensure_ascii=False)}\n\n"
    
    return combined_prompt


def create_virtual_tryon_prompt() -> str:
    """Create a prompt for virtual try-on generation."""
    return "Use the first image (user model) as base. Use the second image (clothing grid) to dress them. Same size, no text." 


def create_fullbody_avatar_prompt(
    *,
    height_cm: Optional[float] = None,
    weight_kg: Optional[float] = None,
    gender: Optional[str] = None,
) -> str:
    """Prompt for generating a studio full-body avatar from a selfie.

    The first image input is the user's selfie. Output should be a full-body,
    front-facing studio shot on a clean white background in the exact pose
    described, preserving the user's facial identity.
    """
    metrics = []
    if height_cm is not None:
        metrics.append(f"height ≈ {int(round(height_cm))} cm")
    if weight_kg is not None:
        metrics.append(f"weight ≈ {int(round(weight_kg))} kg")
    metrics_text = (" (" + ", ".join(metrics) + ")") if metrics else ""
    gender_text = f" Present as a {gender.lower()} model silhouette." if gender else ""

    return (
        "Use the first image as the person's face/identity reference. "
        "Generate a FULL-BODY studio photo of the same person standing, front-facing, neutral stance, "
        "feet hip‑width apart, arms relaxed at sides, slight friendly smile. "
        "Plain seamless white background, even soft lighting, natural skin tones, no shadows cut off, no text. "
        "Camera: full-length portrait, subject centered, include head to shoes with small margin. "
        "Image ratio approximately 3:4 (portrait orientation, slightly taller than wide). "
        "Wardrobe: plain white crew‑neck t‑shirt, khaki chino shorts to mid‑thigh, clean white low‑top sneakers, no logos. "
        "Preserve the person's face and hair from the selfie. "
        f"Match body proportions to typical {metrics_text} as guidance if provided." 
        f"{gender_text} "
        "Output a single image only."
    )