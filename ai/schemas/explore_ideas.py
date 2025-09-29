from typing import Dict, Any
import _config as config

# shape of the below schema is
# {
#   "ideas": [
#     {
#       "title": "string",
#       "description": "string",
#       "outfits": [
#         {
#           "name": "string",
#           "items": [
#             {
#               "type": "string",
#               "keywords": "string"
#             }
#           ]
#         }
#       ]
#     }
#   ]
# }

def generate_explore_ideas_schema() -> Dict[str, Any]:
    """Return response_format wrapper for OpenAI chat.completions structured output.

    Produces a single idea with title and description only.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "explore_idea",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short catchy title for the explore idea (max 6 words)"
                    },
                    "description": {
                        "type": "string", 
                        "description": "Brief description of the styling concept (1-2 sentences)"
                    }
                },
                "required": ["title", "description"],
                "additionalProperties": False,
            },
        },
    }


