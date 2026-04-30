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
GPT_O4_MINI_DEEP_RESEARCH = "o4-mini-deep-research-2025-06-26"
GPT_IMAGE_1 = "gpt-image-1"
GPT_5_4 = 'gpt-5.4'
GPT_5_4_MINI = "gpt-5.4-mini"
GPT_5_5 = 'gpt-5.5'

# CORE FUNCTIONALITY CONFIGS ===============================

OUTFIT_GENERATION = {
    "model": GPT_5_5,
    "reasoning_effort": 'medium',
}


PRODUCT_RANKING = {
    "model": GPT_5_4,
    "reasoning_effort": 'low',
}

TITLE_GENERATION = {
       "model": GPT_5_4,
       "reasoning_effort": 'low',
}

PROMPT_SUGGESTIONS = {
       "model": GPT_5_4,
       "reasoning_effort": 'medium',
}

STYLE_BRAND_CHIPS = {
       "model": GPT_5_5,
       "reasoning_effort": 'high',
}

STYLE_CONTEXT_SYNTHESIS = {
       "model": GPT_5_5,
       "reasoning_effort": 'xhigh',
}


# GEMINI IMAGE CONFIGS ======================================

GEMINI_FLOW_IMAGE_GENERATION = {
       "model": "gemini-2.5-flash-image",
       "temperature": 0.4,
       "top_p": 0.8,
       "top_k": 32,
       "candidate_count": 1,
       "response_modalities": ["IMAGE"],
       "image_size": "1K",
}

GEMINI_AVATAR_GENERATION = {
       # Highest-quality image editing model in the Gemini API docs.
       # This is intentionally separate from the faster outfit image flow.
       "model": "gemini-3-pro-image-preview",
       "temperature": 0.15,
       "top_p": 0.8,
       "top_k": 32,
       "candidate_count": 1,
       "response_modalities": ["TEXT", "IMAGE"],
       "aspect_ratio": "3:4",
       "image_size": "4K",
}

