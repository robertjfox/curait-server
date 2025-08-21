from typing import Dict, Any


def generate_conversation_user_intent_schema() -> Dict[str, Any]:
    """JSON schema for conversation decision making.
    
    Returns simple decision about whether to generate outfits or chat.
    Only used at the beginning of threads before outfits exist.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ConversationDecision",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "decision": {
                        "type": "string",
                        "enum": ["GENERATE", "CHAT"],
                        "description": "Whether to generate new outfits or continue chatting"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of why this decision was made"
                    }
                },
                "required": ["decision", "reasoning"],
                "additionalProperties": False
            }
        }
    } 