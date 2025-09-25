from typing import Optional, Dict, Any
import json


def build_cover_prompt(*, title: str, description: str, gender: str, concept_outfit: Optional[Dict[str, Any]] = None) -> str:
    """Prompt for generating a 3:4 cover image that visually conveys the idea.

    The prompt biases toward clean, high‑impact editorial design suitable for a fashion app landing tile.
    """
    return (
        "Create a polished, brand‑neutral fashion cover image for an app's Explore tile. "
        "The image should be in a [3:4] format. (Portrait)"
        "The produced image should be FULL BLEED, dont leave any leftover white space."
        "The image must include a person cropped from the mid-face down (showing from nose/mouth area to full body). "
        "Focus on fashion styling and body language that conveys the concept. "
        "Use a subtle and relevant background setting that matches the theme and concept described. "
        "The background should enhance the narrative without being distracting - think editorial fashion photography with contextual environments."
        "No watermarks, no logos, no text elements, no captions or decorative overlays. "
        "Use studio‑grade lighting and color grading suitable for premium fashion."

        + "\n\nTITLE: " + title.strip()
        + "\nDESCRIPTION: " + description.strip()
        + "\nGENDER CONTEXT: " + gender.strip()
        + ("\nCONCEPT_OUTFIT: " + json.dumps(concept_outfit, separators=(",", ":")) if concept_outfit else "")
    )
