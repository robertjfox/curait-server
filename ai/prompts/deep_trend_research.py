from typing import Tuple


def build_deep_trend_research_input(*, gender: str, date_iso: str) -> str:
    """Return a single input string for the Responses API.

    Combines instructions and minimal context into one string.
    """
    instructions = (
        "You are a fashion macro-trend research analyst. Analyze current, time-aware fashion trends for the given gender and date. "
        "Be precise, recent, and practical. Capture both mainstream and emerging themes that would influence outfit concepts today.\n\n"
        "Provide a comprehensive trend report covering:\n"
        "- Key themes and aesthetics\n"
        "- Must-have items and pieces\n"
        "- Trending colors and palettes\n"
        "- Popular silhouettes and fits\n"
        "- Style notes and insights\n\n"
        "Write in a clear, informative style that could guide outfit generation. "
        "Do NOT include sources, citations, or references in your output."
    )

    user_payload = f"Gender: {gender}, Date: {date_iso}"
    return instructions + "\n\n" + user_payload


