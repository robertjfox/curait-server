import os
from dotenv import load_dotenv

load_dotenv(override=True)

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def _env_int(name: str, dev_default: int, prod_default: int) -> int:
    return int(os.getenv(name, str(dev_default if IS_DEV else prod_default)))


IS_DEV = _env_bool("IS_DEV")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# CORS Configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")


NUM_OUTFITS_IN_GRID = int(os.getenv("NUM_OUTFITS_IN_GRID", "1"))

# Shopping Configuration
SHOPPING_RESULTS_TO_FETCH = _env_int("SHOPPING_RESULTS_TO_FETCH", 12, 40)
SHOPPING_RESULTS_TO_RANK = _env_int("SHOPPING_RESULTS_TO_RANK", 8, 20)
SHOPPING_RESULTS_TO_RETURN = _env_int("SHOPPING_RESULTS_TO_RETURN", 6, 10)


CLOTHING_ITEMS = [
   "outerwear", "tops", "dresses", "bottoms", "footwear"
]

# Product ranking toggle
PRODUCT_RANKING_ENABLED = _env_bool("PRODUCT_RANKING_ENABLED", True)
PRODUCT_RANKING_GRID_UPLOAD_ENABLED = _env_bool("PRODUCT_RANKING_GRID_UPLOAD_ENABLED", False)

# Search and ranking performance settings
SERPER_MAX_CONCURRENCY = _env_int("SERPER_MAX_CONCURRENCY", 2, 15)
SHOPPING_SEARCH_TIMEOUT = float(os.getenv("SHOPPING_SEARCH_TIMEOUT", "12.0"))
RANKING_BATCH_SIZE = _env_int("RANKING_BATCH_SIZE", 2, 12)
ITEM_PROCESSING_CONCURRENCY = _env_int("ITEM_PROCESSING_CONCURRENCY", 1, 5)
SEARCH_HTTP_MAX_CONNECTIONS = _env_int("SEARCH_HTTP_MAX_CONNECTIONS", 4, 50)
SEARCH_HTTP_MAX_KEEPALIVE_CONNECTIONS = _env_int("SEARCH_HTTP_MAX_KEEPALIVE_CONNECTIONS", 2, 10)
RANKING_IMAGE_DOWNLOAD_CONCURRENCY = _env_int("RANKING_IMAGE_DOWNLOAD_CONCURRENCY", 1, 8)
RANKING_IMAGE_MAX_PRODUCTS = int(os.getenv("RANKING_IMAGE_MAX_PRODUCTS", str(SHOPPING_RESULTS_TO_RANK)))
RANKING_MAX_RETRIES = int(os.getenv("RANKING_MAX_RETRIES", "1"))  # Number of retries for failed ranking operations
RANKING_RETRY_DELAY = float(os.getenv("RANKING_RETRY_DELAY", "1.0"))  # Initial delay between retries in seconds
RANKING_TIMEOUT = int(os.getenv("RANKING_TIMEOUT", "60"))  # Timeout for ranking operations in seconds

# OpenAI client timeout settings (in seconds)
OPENAI_CONNECT_TIMEOUT = float(os.getenv("OPENAI_CONNECT_TIMEOUT", "10.0"))  # Connection timeout
OPENAI_READ_TIMEOUT = float(os.getenv("OPENAI_READ_TIMEOUT", "300.0"))  # Read timeout (5 minutes for streaming)
OPENAI_WRITE_TIMEOUT = float(os.getenv("OPENAI_WRITE_TIMEOUT", "60.0"))  # Write timeout
OPENAI_POOL_TIMEOUT = float(os.getenv("OPENAI_POOL_TIMEOUT", "60.0"))  # Pool timeout

# Blocked sources for search filtering
BLOCKED_SOURCES_RAW = os.getenv("BLOCKED_SOURCES", "ebay,aliexpress,dhgate,wish,temu,alibaba,banggood,gearbest")
BLOCKED_SOURCES = [source.strip().lower() for source in BLOCKED_SOURCES_RAW.split(",") if source.strip()]
