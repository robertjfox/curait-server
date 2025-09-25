import os
from dotenv import load_dotenv

load_dotenv(override=True)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# CORS Configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")


NUM_OUTFITS_IN_GRID = int(os.getenv("NUM_OUTFITS_IN_GRID", "3"))
QUEUE_MULTIPLIER = int(os.getenv("QUEUE_MULTIPLIER", "2"))

# Shopping Configuration
SHOPPING_MIN_PRICE = int(os.getenv("SHOPPING_MIN_PRICE", "40"))
SHOPPING_MAX_PRICE = int(os.getenv("SHOPPING_MAX_PRICE", "200"))
SHOPPING_RESULTS_TO_FETCH = int(os.getenv("SHOPPING_RESULTS_TO_FETCH", "40"))
SHOPPING_RESULTS_TO_RANK = int(os.getenv("SHOPPING_RESULTS_TO_RANK", "20"))
SHOPPING_RESULTS_TO_RETURN = int(os.getenv("SHOPPING_RESULTS_TO_RETURN", "10"))


CLOTHING_ITEMS = [
   "outerwear",  "tops", "dresses", "bottoms", "footwear", "accessories"
]

# Product ranking toggle
PRODUCT_RANKING_ENABLED = os.getenv("PRODUCT_RANKING_ENABLED", "true").lower() in ("1", "true", "yes", "on")

# Search and ranking performance settings
SERPER_MAX_CONCURRENCY = int(os.getenv("SERPER_MAX_CONCURRENCY", "15"))  # Increased from default 10
RANKING_BATCH_SIZE = int(os.getenv("RANKING_BATCH_SIZE", "12"))  # Process rankings in parallel batches
RANKING_MAX_RETRIES = int(os.getenv("RANKING_MAX_RETRIES", "1"))  # Number of retries for failed ranking operations
RANKING_RETRY_DELAY = float(os.getenv("RANKING_RETRY_DELAY", "1.0"))  # Initial delay between retries in seconds
RANKING_TIMEOUT = int(os.getenv("RANKING_TIMEOUT", "60"))  # Timeout for ranking operations in seconds
VIRTUAL_TRYON_TIMEOUT = int(os.getenv("VIRTUAL_TRYON_TIMEOUT", "120"))  # Timeout for VTO operations

# OpenAI client timeout settings (in seconds)
OPENAI_CONNECT_TIMEOUT = float(os.getenv("OPENAI_CONNECT_TIMEOUT", "10.0"))  # Connection timeout
OPENAI_READ_TIMEOUT = float(os.getenv("OPENAI_READ_TIMEOUT", "300.0"))  # Read timeout (5 minutes for streaming)
OPENAI_WRITE_TIMEOUT = float(os.getenv("OPENAI_WRITE_TIMEOUT", "60.0"))  # Write timeout
OPENAI_POOL_TIMEOUT = float(os.getenv("OPENAI_POOL_TIMEOUT", "60.0"))  # Pool timeout

# Blocked sources for search filtering
BLOCKED_SOURCES_RAW = os.getenv("BLOCKED_SOURCES", "ebay,aliexpress,dhgate,wish,temu,alibaba,banggood,gearbest")
BLOCKED_SOURCES = [source.strip().lower() for source in BLOCKED_SOURCES_RAW.split(",") if source.strip()]
