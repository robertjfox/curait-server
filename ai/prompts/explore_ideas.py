import json
from typing import List


def build_explore_ideas_input(*, gender: str, date_iso: str, trend_inspiration: str, previous_titles: List[str]) -> str:
    instructions = (
        "You are an editorial ideation assistant for a fashion app's Explore page. "
        "Generate 4 concise, compelling concepts for tiles users see on first open. "
        "Each concept must be a REALISTIC styling theme that could dictate actual outfit generation in an AI stylist app. "
        "Focus on practical, wearable concepts like occasions, moods, color palettes, silhouettes, or styling approaches. "
        "Avoid fantasy concepts, fictional characters, or overly abstract ideas that wouldn't translate to real clothing recommendations. "
        "Each concept must include: a short title (max 6 words), a 1-2 sentence description, and a concept_outfits JSON with exactly 3 distinct outfits that follows this schema strictly. "
        "Avoid exact duplicates of prior titles and lean on provided trend outfits data when useful."
        "Dont just resuse outfits from the trend outfits, try to create your own based on the trends you are seeing in the trend outfits."
    )

    return (
        instructions
        + "\n\nGENDER:\n"
        + gender
        + "\n\nDATE:\n"
        + date_iso
        + "\n\nTREND_OUTFITS:\n"
        + (trend_inspiration or "")
        + "\n\nPREVIOUS_TITLES:\n"
        + "\n".join(previous_titles or [])
        + "\n\nOUTPUT: Return a JSON object with key 'ideas' containing exactly 4 items."
    )


