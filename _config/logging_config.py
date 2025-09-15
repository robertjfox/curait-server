import logging
import sys


class ColoredFormatter(logging.Formatter):
    """Colored log formatter for terminal output with module prefixes"""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[37m',       # White
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    # Module to prefix mapping
    MODULE_PREFIXES = {
        # Search related
        'clients.shopping.serper_client': ' 🔍 SEARCH ',
        'clients.shopping.serpapi_client': ' 🔍 SEARCH ',
        'clients.shopping': ' 🔍 SEARCH ',
        'clients.openai_client': ' 🤖 OPENAI ',
        
        # Thread-based chat (replaced old chat service)
        'services.thread_service': ' 🧵 THREADS ',

        
        # Ranking related
        'services.product_ranking_service': ' 📊 RANK ',
        
        # Virtual try-on related
        'services.virtual_tryon_service': ' 🪞 VTON ',
        'api.routers.virtual_tryon': ' 🪞 VTON ',
        
        # API Routers
        'api.routers.users': ' 👤 USERS ',
        'api.routers.threads': ' 🧵 THREADS ',
        'api.routers.outfit_generation': ' ✨ OUTFIT_GEN ',
        'api.routers.product_search': ' 🔍 SEARCH ',
        'api.routers.product_ranking': ' 📊 RANK ',
        'api.routers.testing': ' 🧪 TEST ',
        'api.routers.unsubscribe': ' 🚫 UNSUB ',
        
        # Config related
        '_config.master_config': ' ⚙️ CONFIG ',
        '_config.logging_config': ' ⚙️ CONFIG ',
        '_config.model_config': ' ⚙️ CONFIG ',
        '_config': ' ⚙️ CONFIG ',
        '__main__': ' ⚙️ CONFIG ',  # Main app startup/shutdown logs
        'main': ' ⚙️ CONFIG ',      # Main app startup/shutdown logs
        
        # Utils related
        'utils.image_processing.background_removal': ' 🛠️ UTILS ',
        'utils.image_processing.create_image_grid': ' 🖼️ GRID ',
        'utils.response_handler_utils': ' 🛠️ UTILS ',
        'utils.search_client_utils': ' 🛠️ UTILS ',
        
        # Outfit generation related
        'services.outfit_generation_service': ' ✨ OUTFIT_GEN ',
    }
    
    def _get_prefix(self, module_name):
        """Get the appropriate prefix for a module"""
        # Try exact match first
        if module_name in self.MODULE_PREFIXES:
            return self.MODULE_PREFIXES[module_name]
        
        # Try partial matches (check if any key is a prefix of the module name)
        for key, prefix in self.MODULE_PREFIXES.items():
            if module_name.startswith(key):
                return prefix
        
        # Default prefix for unmatched modules
        return 'APP'
    
    def format(self, record):
        # Get the original formatted message
        message = super().format(record)
        
        # Get module prefix
        prefix = self._get_prefix(record.name)
        
        # Add color based on log level
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Disable special cost handling
        return f"{color}{message}{reset}"


class SubstringFilter(logging.Filter):
    """Filter out records containing any forbidden substrings."""
    def __init__(self, forbidden: list[str]) -> None:
        super().__init__()
        self.forbidden = tuple(forbidden)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return not any(sub in msg for sub in self.forbidden)


def setup_logging(level=logging.INFO):
    """Configure colored logging with newline separation and module prefixes"""
    # Create custom handler with colored formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter('%(message)s\n'))
    # Drop specific noisy lines printed by some SDKs
    handler.addFilter(SubstringFilter([
        "AFC is enabled", 
        "AFC remote call",
        "Agent Function Calling",
    ]))
    
    # Configure basic logging
    logging.basicConfig(
        level=level,
        handlers=[handler]
    )
    
    # Silence noisy third-party loggers by default
    # Note: We silence "openai._base_client" but NOT "clients.openai_client" 
    noisy_loggers = (
        # HTTP clients
        "httpx", "httpcore", "urllib3",
        
        # OpenAI SDK internals
        "openai._base_client", "openai.resources",
        
        # Vision / CV libs
        "insightface", "onnxruntime", "opencv", "cv2",
        
        # Google / Gemini SDK + gRPC
        "google", "google.genai", "google.api_core", "google.cloud", "google.auth", "google.protobuf",
        "grpc", "absl"
    )
    for name in noisy_loggers:
        nl = logging.getLogger(name)
        # Make gRPC extra quiet
        if name == "grpc":
            nl.setLevel(logging.ERROR)
        elif name in ("google.genai",):
            nl.setLevel(logging.ERROR)
        else:
            nl.setLevel(logging.WARNING)
        nl.propagate = False

    # Further reduce absl log verbosity if present
    try:
        import absl.logging as absl_logging  # type: ignore
        absl_logging.set_verbosity(absl_logging.ERROR)
        absl_logging.use_python_logging()
    except Exception:
        pass
    
    # Make sure our openai client logger works
    openai_client_logger = logging.getLogger('clients.openai_client')
    openai_client_logger.setLevel(level)
    openai_client_logger.propagate = True



def test_log_prefixes():
    """Test function to demonstrate different log prefixes"""
    test_loggers = {
        'SEARCH_SERPER': logging.getLogger('clients.shopping.serper_client'),
        'SEARCH_SERPAPI': logging.getLogger('clients.shopping.serpapi_client'),
        'OPENAI_CLIENT': logging.getLogger('clients.openai_client'),
        'THREADS': logging.getLogger('services.thread_service'),
        'RANK': logging.getLogger('services.product_ranking_service'),
        'VTON_SERVICE': logging.getLogger('services.virtual_tryon_service'),
        'CONFIG': logging.getLogger('_config.master_config'),
        'OUTFIT_GEN': logging.getLogger('services.outfit_generation_service'),
        'UTILS_BG': logging.getLogger('utils.image_processing.background_removal'),
        'OUTFIT_RESP': logging.getLogger('services.outfit_generation_service'),
        'USERS_ROUTER': logging.getLogger('api.routers.users'),
        'TESTING_ROUTER': logging.getLogger('api.routers.testing'),
        'UNSUB_ROUTER': logging.getLogger('api.routers.unsubscribe'),
    }
    
    for prefix, logger in test_loggers.items():
        logger.info(f"Test message from {prefix} module")
        logger.error(f"Test error from {prefix} module") 