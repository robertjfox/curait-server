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
                                    "description": "The type of item to modify (e.g., 'tops', 'bottoms', 'footwear', 'accessories')"
                                },
                                "new_keywords": {
                                    "type": "string",
                                    "description": "The new search keywords for this item"
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