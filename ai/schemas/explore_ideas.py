from typing import Dict, Any
import _config as config


def generate_explore_ideas_schema() -> Dict[str, Any]:
    """Return response_format wrapper for OpenAI chat.completions structured output.

    Produces exactly 4 ideas, each with title, description, and concept_outfits
    aligned to our outfit item conventions.
    """
    clothing_items = list(getattr(config, "CLOTHING_ITEMS", []))

    item_object_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": clothing_items or None},
            "keywords": {
                "type": "string",
                "description": "Single space-delimited keyword phrase (no commas)",
                "minLength": 10,
                "maxLength": 120,
            },
        },
        "required": ["type", "keywords"],
        "additionalProperties": False,
    }

    outfit_object_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "items": {"type": "array", "minItems": 3, "maxItems": 6, "items": item_object_schema},
        },
        "required": ["name", "items"],
        "additionalProperties": False,
    }

    concept_outfits_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "outfits": {"type": "array", "minItems": 3, "maxItems": 3, "items": outfit_object_schema},
        },
        "required": ["outfits"],
        "additionalProperties": False,
    }

    idea_object_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "concept_outfits": concept_outfits_schema,
        },
        "required": ["title", "description", "concept_outfits"],
        "additionalProperties": False,
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "explore_ideas",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "ideas": {
                        "type": "array",
                        "minItems": 4,
                        "maxItems": 4,
                        "items": idea_object_schema,
                    }
                },
                "required": ["ideas"],
                "additionalProperties": False,
            },
        },
    }


