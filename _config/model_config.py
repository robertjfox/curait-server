# Centralized OpenAI model configuration (no env vars)

# MODELS ====================================================

GPT_4O = "gpt-4o-2024-08-06"
GPT_4O_MINI = "gpt-4o-mini-2024-07-18"

GPT_4O_SEARCH = 'gpt-4o-search-preview-2025-03-11'

GPT_O4_MINI = 'o4-mini-2025-04-16'

GPT_4_1 = 'gpt-4.1-2025-04-14'

GPT_5 = 'gpt-5-2025-08-07'
GPT_5_MINI = "gpt-5-mini-2025-08-07"
GPT_5_NANO = "gpt-5-nano-2025-08-07"
GPT_5_CHAT = 'gpt-5-chat-latest'

GPT_IMAGE_1 = "gpt-image-1"


# CORE FUNCTIONALITY CONFIGS ===============================

# For generating outfit recommendations with structured JSON output
# Category: "outfit_generation"
OUTFIT_GENERATION = {
    "model": GPT_4O_MINI,
    # "model": GPT_4_1,
    # "model": GPT_4O_SEARCH,
    # "model": GPT_O4_MINI,
    # "model": GPT_5,
    # "model": GPT_5_MINI,
    # "model": GPT_5_NANO,
    # "model": GPT_5_CHAT,
}

# For ranking and scoring product search results with visual analysis
# Category: "product_ranking"
PRODUCT_RANKING = {
    # "model": GPT_4O_MINI,
"model": GPT_O4_MINI,
    # "model": GPT_4O,
    # "model": GPT_4_1,
    # "model": GPT_5_MINI,
    # "model": GPT_5_NANO,
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
       "model": GPT_4_1,
}

# For generating short prompt suggestions for the user
# Category: "prompt_suggestions"
PROMPT_SUGGESTIONS = {
       "model": GPT_4_1,
}

