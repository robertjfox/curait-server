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

OUTFIT_GENERATION = {
    "model": GPT_4_1,
    # "model": GPT_O4_MINI,

}

PRODUCT_RANKING = {
#     "model": GPT_O4_MINI,
    "model": GPT_4_1,

}

TITLE_GENERATION = {
       "model": GPT_4_1,
}

PROMPT_SUGGESTIONS = {
       "model": GPT_5_MINI,
}

THREAD_RESEARCH = {
       "model": GPT_5_MINI,
}
