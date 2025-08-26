# The JSON schema created here has the following shape:
# {
#   "outfit_1": {
#     "item_1": "string",
#     "item_2": "string",
#     ...
#   },
#   "outfit_2": {
#     "item_1": "string",
#     "item_2": "string",
#     ...
#   },
#   ...
#   "metadata": {
#     "outfit_1": {
#       "name": "string",
#       "description": "string",
#       "item_1": {
#         "type": "string",
#         "keywords": "string"
#       },
#       ...
#     },
#     "outfit_2": {
#       "name": "string",
#       "description": "string",
#       "item_1": {
#         "type": "string",
#         "keywords": "string"
#       },
#       ...
#     },
#     ...
#   }
# }

from typing import List

def generate_outfit_schema(num_outfits: int, num_items: int, clothing_items: List[str]):
    # Keywords section - comes first for immediate search
    keywords_properties = {}
    keywords_required = []
    
    for i in range(1, num_outfits + 1):
        outfit_key = f"outfit_{i}"
        item_keywords = {}
        
        for j in range(1, num_items + 1):
            item_key = f"item_{j}"
            item_keywords[item_key] = {
                "type": "string",
                "description": "Space-separated keywords ONLY. Use spaces between words, NEVER commas, quotes, or special characters. Example: 'mens slim fit navy cotton chinos' NOT 'mens, slim, fit, navy, cotton, chinos'"
            }
        
        keywords_properties[outfit_key] = {
            "type": "object", 
            "properties": item_keywords,
            "required": [f"item_{j}" for j in range(1, num_items + 1)],
            "additionalProperties": False
        }
        keywords_required.append(outfit_key)
    
    # Metadata section - comes after keywords
    metadata_properties = {}
    metadata_required = []

    for i in range(1, num_outfits + 1):
        outfit_key = f"outfit_{i}"
        
        item_properties = {
            "name": {"type": "string"},
            "description": {"type": "string"},
        }
        item_required = ["name", "description"]

        for j in range(1, num_items + 1):
            item_key = f"item_{j}"
            item_properties[item_key] = {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": clothing_items},
                    "keywords": {
                        "type": "string",
                        "description": "Space-separated keywords ONLY. Use spaces between words, NEVER commas, quotes, or special characters. Example: 'mens slim fit navy cotton chinos' NOT 'mens, slim, fit, navy, cotton, chinos'"
                    },
                },
                "required": ["type", "keywords"],
                "additionalProperties": False,
            }
            item_required.append(item_key)

        metadata_properties[outfit_key] = {
            "type": "object",
            "properties": item_properties,
            "required": item_required,
            "additionalProperties": False,
        }
        metadata_required.append(outfit_key)

    # Combined schema with keywords first, then metadata
    all_properties = {}
    all_properties.update(keywords_properties)
    all_properties["metadata"] = {
        "type": "object",
        "properties": metadata_properties,
        "required": metadata_required,
        "additionalProperties": False
    }
    
    all_required = keywords_required + ["metadata"]

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "outfit_suggestions",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": all_properties,
                "required": all_required,
                "additionalProperties": False,
            },
        },
    } 