import _config as config

# Schema shape:
# {
#   "outfits": [
#     {
#       "name": "outfit name",
    #   "description": "outfit description", 
#       "items": [
#         {"type": "shirt", "keywords": "red leather jacket"},
#         {"type": "pants", "keywords": "blue suede shoes"},
#         ...
#       ]
#     },
#     ...
#   ]
# }


def generate_outfit_schema(queue_multiplier: int):
    num_outfits = config.NUM_OUTFITS_IN_GRID * queue_multiplier
    clothing_items = config.CLOTHING_ITEMS

    # Build outfits array with name/description and items array
    item_object_schema = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": clothing_items},
            "keywords": {
                "type": "string",
                "description": "Single space-delimited keyword string for this clothing item. Must be ONE complete keyword phrase with spaces between words (never commas). Example: 'mens slim fit navy cotton chinos' as ONE string, NOT comma-separated values.",
                "minLength": 30,
                "maxLength": 60,
                "pattern": r"^\S+(?: \S+){0,9}$"
            },
        },
        "required": ["type", "keywords"],
        "additionalProperties": False,
    }

    outfit_object_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "items": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": item_object_schema
            }
        },
        "required": ["name", "description", "items"],
        "additionalProperties": False,
    }

    outfits_array_schema = {
        "type": "array",
        "minItems": num_outfits,
        "maxItems": num_outfits,
        "items": outfit_object_schema
    }

    # Combined schema with ONLY outfits (no top-level keywords array)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "outfit_suggestions",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "outfits": outfits_array_schema,
                },
                "required": ["outfits"],
                "additionalProperties": False,
            },
        },
    } 