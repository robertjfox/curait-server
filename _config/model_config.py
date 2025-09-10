# Centralized OpenAI model configuration (no env vars)

# MODELS ====================================================

GPT_4O = "gpt-4o-2024-08-06"
GPT_4O_MINI = "gpt-4o-mini-2024-07-18"
GPT_4O_SEARCH = 'gpt-4o-search-preview-2025-03-11'

GPT_O4_MINI = 'o4-mini-2025-04-16'

GPT_5 = 'gpt-5-2025-08-07'
GPT_5_MINI = "gpt-5-mini-2025-08-07"
GPT_5_NANO = "gpt-5-nano-2025-08-07"

GPT_IMAGE_1 = "gpt-image-1"


# CORE FUNCTIONALITY CONFIGS ===============================

# For generating outfit recommendations with structured JSON output
# Category: "outfit_generation"
OUTFIT_GENERATION = {
    # "model": GPT_4O_MINI,
    "model": GPT_4O,
    # "model": GPT_O4_MINI,
    # "model": GPT_5,
    # "model": GPT_5_MINI,
    # "model": GPT_5_NANO,
}

# For ranking and scoring product search results with visual analysis
# Category: "product_ranking"
PRODUCT_RANKING = {
    # "model": GPT_4O_MINI,
    "model": GPT_O4_MINI,
    # "model": GPT_4O,
    # "model": GPT_5_MINI,
    # "model": GPT_5_NANO,
}

# For generating virtual try-on images
VIRTUAL_TRY_ON = {
    "model": GPT_IMAGE_1,
    "size": "1024x1536",
    "input_fidelity": "low",
    # "input_fidelity": "high",
    "quality": "low",
    # "quality": "medium",
    "n": 1,
}

# For generating outfit flatlay default rendering images
FLATLAY_RENDERING = {
    "model": GPT_IMAGE_1,
    "size": "1024x1024",
    "bucket": "outfit-flatlay-images",
    "quality": "low",
}


# For conversational responses and context gathering
# Category: "thread_chat"
CHAT_MODEL = {
    "model": GPT_4O_MINI
    # "model": GPT_5_MINI
}

# For decision making (outfit generation vs chat)
# Category: "decision_making"
CONVERSATION_DECISION = {
    "model": GPT_4O_MINI,
}

# For modifying individual items based on user feedback
# Category: "item_modification"
ITEM_MODIFICATION = {
    "model": GPT_4O_MINI,
}

TITLE_GENERATION = {
    "model": GPT_4O,
}

