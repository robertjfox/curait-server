import _config as config


def generate_prompt_suggestions_schema():
	return {
		"type": "json_schema",
		"json_schema": {
			"name": "prompt_suggestions",
			"strict": True,
			"schema": {
				"type": "object",
				"properties": {
					"prompts": {
						"type": "array",
						"minItems": 4,
						"maxItems": 4,
						"items": {
							"type": "string",
							"description": "Short, one-sentence prompt tailored to the user."
						}
					}
				},
				"required": ["prompts"],
				"additionalProperties": False,
			},
		},
	} 