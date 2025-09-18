from typing import Dict, Any


def generate_product_ratings_schema(num_results: int) -> Dict[str, Any]:
    """JSON schema for product ranking output used as OpenAI response_format.

    Enforces: { "ratings": [int 0..2] } with exactly num_results items.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ProductRatings",
            "schema": {
                "type": "object",
                "properties": {
                    "ratings": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0, "maximum": 2},
                        # "items": {"type": "number", "minimum": 1, "maximum": 10},
                        "minItems": num_results,
                        "maxItems": num_results,
                    }
                },
                "required": ["ratings"],
                "additionalProperties": False,
            },
        },
    } 