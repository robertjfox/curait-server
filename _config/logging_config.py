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
        'utils.image_processing.face_injector': ' 🪞 VTON ',
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
        'utils.logging.cost_tracking': ' 💰 COST ',
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
        
        # Special handling for COST messages - don't show [COST] prefix if message already contains cost info
        if prefix == ' 💰 COST ' and (message.startswith('•') or message.startswith('[COST]')):
            # Remove [COST] from message if present and just show the content
            if message.startswith('[COST]'):
                message = message[6:].strip()
            return f"{color}{message}{reset}"
        
        return f"{color}[{prefix}] {message}{reset}"


def setup_logging(level=logging.INFO):
    """Configure colored logging with newline separation and module prefixes"""
    # Create custom handler with colored formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter('%(message)s\n'))
    
    # Configure basic logging
    logging.basicConfig(
        level=level,
        handlers=[handler]
    )
    
    # Silence noisy third-party loggers by default
    for noisy_logger in ("httpx", "httpcore", "openai", "urllib3", "insightface", "onnxruntime", "opencv", "cv2"):
        nl = logging.getLogger(noisy_logger)
        nl.setLevel(logging.WARNING)
        nl.propagate = False


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
        'COST': logging.getLogger('utils.logging.cost_tracking'),
        'OUTFIT_RESP': logging.getLogger('services.outfit_generation_service'),
        'USERS_ROUTER': logging.getLogger('api.routers.users'),
        'TESTING_ROUTER': logging.getLogger('api.routers.testing'),
        'UNSUB_ROUTER': logging.getLogger('api.routers.unsubscribe'),
    }
    
    for prefix, logger in test_loggers.items():
        logger.info(f"Test message from {prefix} module")
        logger.error(f"Test error from {prefix} module") 