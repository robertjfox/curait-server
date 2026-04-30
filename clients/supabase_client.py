from typing import Optional
from typing import Any
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


def reset_supabase_client():
    """Drop the cached Supabase client so the next call opens fresh sessions."""
    global _supabase_client
    old_client = _supabase_client
    _supabase_client = None

    if old_client is None:
        return

    candidate_paths: tuple[tuple[str, ...], ...] = (
        ("postgrest", "session"),
        ("postgrest", "_session"),
        ("storage", "_client"),
        ("auth", "_http_client"),
    )
    for path in candidate_paths:
        obj: Any = old_client
        try:
            for attr in path:
                obj = getattr(obj, attr)
        except AttributeError:
            continue
        close = getattr(obj, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass