from __future__ import annotations
from typing import Any, Dict, Optional
from clients.supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)

class ThreadCostsInterface:
    """CRUD operations for the thread_costs table."""

    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "thread_costs"

    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get cost data for a thread."""
        try:
            res = self._supabase.table(self._table).select("*").eq("thread_id", thread_id).single().execute()
            return res.data
        except Exception:
            return None

    def get_total_cost_cents(self, thread_id: str) -> Optional[int]:
        """Get total cost for a thread in cents."""
        try:
            data = self.get(thread_id)
            if not data:
                return None
                
            total = (
                (data.get("outfit_gen_cost_cents") or 0) +
                (data.get("search_cost_cents") or 0) +
                (data.get("ranking_cost_cents") or 0) +
                (data.get("flatlay_gen_cost_cents") or 0) +
                (data.get("vton_gen_cost_cents") or 0)
            )
            return int(total)
        except Exception:
            return None

    def delete(self, thread_id: str) -> bool:
        """Delete cost data for a thread."""
        try:
            self._supabase.table(self._table).delete().eq("thread_id", thread_id).execute()
            return True
        except Exception:
            return False 