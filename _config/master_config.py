import os
from dotenv import load_dotenv
from utils.logging.cost_tracking import CostLogger

load_dotenv(override=True)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# CORS Configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Outfit Generation
SHOPPING_RESULTS_TO_RETURN = int(os.getenv("SHOPPING_RESULTS_TO_RETURN", "10"))
NUM_OUTFITS_TO_GENERATE = int(os.getenv("NUM_OUTFITS_TO_GENERATE", "1"))
NUM_ITEMS_PER_OUTFIT = int(os.getenv("NUM_ITEMS_PER_OUTFIT", "1"))

# Shopping Configuration
SHOPPING_MIN_PRICE = int(os.getenv("SHOPPING_MIN_PRICE", "40"))
SHOPPING_MAX_PRICE = int(os.getenv("SHOPPING_MAX_PRICE", "200"))
SHOPPING_RESULTS_TO_FETCH = int(os.getenv("SHOPPING_RESULTS_TO_FETCH", "40"))
SHOPPING_RESULTS_TO_RANK = int(os.getenv("SHOPPING_RESULTS_TO_RANK", "20"))

CLOTHING_ITEMS = [
   "outerwear",  "tops", "dresses", "bottoms", "footwear",
]

# Product ranking toggle
PRODUCT_RANKING_ENABLED = os.getenv("PRODUCT_RANKING_ENABLED", "true").lower() in ("1", "true", "yes", "on")

# Background removal toggle (now only applies to top ranked product)
BACKGROUND_REMOVAL_ENABLED = os.getenv("BACKGROUND_REMOVAL_ENABLED", "true").lower() in ("1", "true", "yes", "on")
BACKGROUND_REMOVAL_MAX_CONCURRENCY = int(os.getenv("BACKGROUND_REMOVAL_MAX_CONCURRENCY", str((os.cpu_count() or 4) * 2)))  # 2x CPU cores
BACKGROUND_REMOVAL_PROCESS_WORKERS = int(os.getenv("BACKGROUND_REMOVAL_PROCESS_WORKERS", str(min(4, os.cpu_count() or 2))))  # Up to 4 workers
BACKGROUND_REMOVAL_MAX_DIM = int(os.getenv("BACKGROUND_REMOVAL_MAX_DIM", "1024"))  # max width/height before removal

# Search and ranking performance settings
SERPER_MAX_CONCURRENCY = int(os.getenv("SERPER_MAX_CONCURRENCY", "15"))  # Increased from default 10
RANKING_BATCH_SIZE = int(os.getenv("RANKING_BATCH_SIZE", "6"))  # Process rankings in parallel batches
RANKING_MAX_RETRIES = int(os.getenv("RANKING_MAX_RETRIES", "1"))  # Number of retries for failed ranking operations
RANKING_RETRY_DELAY = float(os.getenv("RANKING_RETRY_DELAY", "1.0"))  # Initial delay between retries in seconds
RANKING_TIMEOUT = int(os.getenv("RANKING_TIMEOUT", "60"))  # Timeout for ranking operations in seconds
VIRTUAL_TRYON_TIMEOUT = int(os.getenv("VIRTUAL_TRYON_TIMEOUT", "120"))  # Timeout for VTO operations

# OpenAI client timeout settings (in seconds)
OPENAI_CONNECT_TIMEOUT = float(os.getenv("OPENAI_CONNECT_TIMEOUT", "10.0"))  # Connection timeout
OPENAI_READ_TIMEOUT = float(os.getenv("OPENAI_READ_TIMEOUT", "300.0"))  # Read timeout (5 minutes for streaming)
OPENAI_WRITE_TIMEOUT = float(os.getenv("OPENAI_WRITE_TIMEOUT", "60.0"))  # Write timeout
OPENAI_POOL_TIMEOUT = float(os.getenv("OPENAI_POOL_TIMEOUT", "60.0"))  # Pool timeout

VTON_ENABLED = os.getenv("VTON_ENABLED", "true").lower() in ("1", "true", "yes", "on")
FACE_SWAP_ENABLED = os.getenv("FACE_SWAP_ENABLED", "true").lower() in ("1", "true", "yes", "on")
ENABLE_COST_LOGGING = os.getenv("ENABLE_COST_LOGGING", "true").lower() in ("1", "true", "yes", "on")
ENABLE_PROMPT_LOGGING = os.getenv("ENABLE_PROMPT_LOGGING", "false").lower() in ("1", "true", "yes", "on")

# Blocked sources for search filtering
BLOCKED_SOURCES_RAW = os.getenv("BLOCKED_SOURCES", "ebay,aliexpress,dhgate,wish,temu,alibaba,banggood,gearbest")
BLOCKED_SOURCES = [source.strip().lower() for source in BLOCKED_SOURCES_RAW.split(",") if source.strip()]

# Face Swap Quality Configuration
FACE_DETECTION_SIZE = int(os.getenv("FACE_DETECTION_SIZE", "320"))  # Higher = better detection but slower
FACE_DETECTION_THRESHOLD = float(os.getenv("FACE_DETECTION_THRESHOLD", "0.1"))  # Lower = more sensitive
FACE_MIN_SIZE = int(os.getenv("FACE_MIN_SIZE", "1024"))  # Minimum face area for quality filtering
FACE_MIN_CONFIDENCE = float(os.getenv("FACE_MIN_CONFIDENCE", "0.5"))  # Minimum detection confidence

# InsightFace Model Storage
# Set to persistent volume path on Railway: /data/insight_cache
INSIGHTFACE_HOME = os.getenv("INSIGHTFACE_HOME", os.path.expanduser("~/.insightface"))

# Global cost logger instance
cost_logger = CostLogger()