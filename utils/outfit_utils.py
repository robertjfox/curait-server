from typing import List, Dict, Any


def format_outfit_history(outfit_history: List[Dict[str, Any]]) -> str:
    lines: List[str] = []

    if not outfit_history:
        return ""

    for outfit in outfit_history[-9:]:
        title = str(outfit.get("title", "")).strip()
        description = str(outfit.get("description", "")).strip()
        raw_keywords = outfit.get("keywords", [])

        if isinstance(raw_keywords, str):
            keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        elif isinstance(raw_keywords, (list, tuple, set)):
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        else:
            keywords = []

        if title:
            lines.append(title)
        # if description:
        #     lines.append(f"- {description}")
        for keyword in keywords:
            lines.append(f"- {keyword}")

        if title or description or keywords:
            lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def extract_colors_from_keywords(keywords: str) -> List[str]:
    """Extract color words from keywords."""
    colors = [
        "black", "white", "navy", "cream", "gray", "brown", "red", "blue", 
        "green", "pink", "purple", "yellow", "orange", "beige", "camel", 
        "burgundy", "olive", "sage", "blush"
    ]
    found_colors = []
    keywords_lower = keywords.lower()
    
    for color in colors:
        if color in keywords_lower:
            found_colors.append(color)
    
    return found_colors


def extract_style_from_description(description: str) -> str:
    """Extract style direction from outfit description."""
    style_words = [
        "professional", "casual", "elegant", "modern", "classic", "edgy", 
        "romantic", "bohemian", "minimalist", "sophisticated"
    ]
    description_lower = description.lower()
    
    for style in style_words:
        if style in description_lower:
            return style
    
    return "unspecified" 