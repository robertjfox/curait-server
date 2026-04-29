import _config as config


def generate_remix_outfit_schema():
    clothing_items = config.CLOTHING_ITEMS

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "remix_outfit",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "items": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["keep", "change"],
                                },
                                "source_item_id": {
                                    "type": "string",
                                    "description": "Existing outfit item id to reuse, or empty string for a new/replaced item.",
                                },
                                "type": {"type": "string", "enum": clothing_items},
                                "keywords": {
                                    "type": "string",
                                    "minLength": 30,
                                    "maxLength": 60,
                                    "description": "Single space-delimited shopping query phrase.",
                                    "pattern": r"^\S+(?: \S+){0,9}$",
                                },
                            },
                            "required": [
                                "action",
                                "source_item_id",
                                "type",
                                "keywords",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name", "items"],
                "additionalProperties": False,
            },
        },
    }
