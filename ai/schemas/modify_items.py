from typing import Dict, Any


def get_outfit_modification_schema() -> Dict[str, Any]:
    """Schema for outfit modification response."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "OutfitModification",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "modifications": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "description": "The type of item to modify (e.g., 'outerwear', 'tops', 'dresses', 'bottoms', 'footwear',)"
                                },
                                "new_keywords": {
                                    "type": "string",
                                    "description": "Space-separated keywords ONLY. Use spaces between words, NEVER commas, quotes, or special characters. Example: 'mens slim fit navy cotton chinos' NOT 'mens, slim, fit, navy, cotton, chinos'"
                                },
                                "reasoning": {
                                    "type": "string",
                                    "description": "Why this item needs to be modified"
                                }
                            },
                            "required": ["type", "new_keywords", "reasoning"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["modifications"],
                "additionalProperties": False
            }
        }
    } 