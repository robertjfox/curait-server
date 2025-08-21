from typing import List


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