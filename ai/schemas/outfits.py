import _config as config


def build_outfit_json_schema(
    *,
    schema_name: str,
    outfit_count_min: int,
    outfit_count_max: int,
    item_count_min: int,
    item_count_max: int,
    keyword_min_length: int,
    keyword_max_length: int,
    keyword_description: str,
    keyword_pattern: str | None = None,
):
    clothing_items = config.CLOTHING_ITEMS

    item_object_schema = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": clothing_items},
            "keywords": {
                "type": "string",
                "description": keyword_description,
                "minLength": keyword_min_length,
                "maxLength": keyword_max_length,
            },
        },
        "required": ["type", "keywords"],
        "additionalProperties": False,
    }

    if keyword_pattern:
        item_object_schema["properties"]["keywords"]["pattern"] = keyword_pattern

    outfit_object_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "items": {
                "type": "array",
                "minItems": item_count_min,
                "maxItems": item_count_max,
                "items": item_object_schema
            }
        },
        "required": ["name", "items"],
        "additionalProperties": False,
    }

    outfits_array_schema = {
        "type": "array",
        "minItems": outfit_count_min,
        "maxItems": outfit_count_max,
        "items": outfit_object_schema
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
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


def generate_outfit_schema(double_batch: bool, num_outfits_override: int = None):
    if double_batch:
        num_outfits = config.NUM_OUTFITS_IN_GRID * 2
    else:
        num_outfits = config.NUM_OUTFITS_IN_GRID

    if num_outfits_override:
        num_outfits = num_outfits_override

    return build_outfit_json_schema(
        schema_name="outfit_suggestions",
        outfit_count_min=num_outfits,
        outfit_count_max=num_outfits,
        item_count_min=3,
        item_count_max=5,
        keyword_min_length=30,
        keyword_max_length=60,
        keyword_description=(
            "Single space-delimited keyword string for this clothing item. "
            "Must be ONE complete keyword phrase with spaces between words (never commas). "
            "Example: 'mens slim fit navy cotton chinos' as ONE string, NOT comma-separated values."
        ),
        keyword_pattern=r"^\S+(?: \S+){0,9}$",
    )

