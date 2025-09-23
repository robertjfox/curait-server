from typing import Optional
from supabase import create_client
import _config

_supabase_client = None


def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        if not _config.SUPABASE_URL or not _config.SUPABASE_KEY:
            raise RuntimeError("Supabase configuration missing: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        _supabase_client = create_client(_config.SUPABASE_URL, _config.SUPABASE_KEY)
        try:
            import logging
            logging.getLogger(__name__).info("[SUPABASE] Client initialized")
        except Exception:
            pass
    return _supabase_client 