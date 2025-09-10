import logging
from typing import Optional, Any

# Simple pricing in dollars per 1K tokens  
MODEL_PRICING = {
    "gpt-4o": {"in": 0.005, "out": 0.015},
    "gpt-4o-mini": {"in": 0.00015, "out": 0.00060},
    "o4-mini": {"in": 0.00110, "out": 0.00440},
    "gpt-5": {"in": 0.00125, "out": 0.0100},
    "gpt-5-mini": {"in": 0.00025, "out": 0.00200},
    "gpt-5-nano": {"in": 0.00005, "out": 0.00040},
}

def calculate_openai_cost_cents(response: Any, model: Optional[str] = None) -> int:
    """Calculate cost in cents from OpenAI response object using actual usage data"""
    if not response:
        return 0
        
    # Get model and usage from response
    model = getattr(response, "model", model or "gpt-4o-mini")
    usage = getattr(response, "usage", None)
    
    if not usage:
        return 0
    
    # Normalize model name (remove date suffixes and version indicators)
    import re
    norm_model = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model)
    norm_model = re.sub(r"-(preview|alpha|beta)(-\d{4}-\d{2}-\d{2})?$", "", norm_model)
    norm_model = re.sub(r"-\d{4}$", "", norm_model)  # Remove year suffixes like -0613
    
    # Get pricing (default to gpt-4o-mini if not found)
    pricing = MODEL_PRICING.get(norm_model, MODEL_PRICING["gpt-4o-mini"])
    
    # Get actual token counts from usage object
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    
    # Calculate cost in dollars
    cost_dollars = (prompt_tokens / 1000.0) * pricing["in"] + (completion_tokens / 1000.0) * pricing["out"]
    return int(cost_dollars * 100)  # Convert to cents

class CostLogger:
    """Simple cost tracking that writes directly to thread_costs table"""
    
    def __init__(self):
        self.log = logging.getLogger(__name__)
        self._supabase = None  # Lazy init to avoid circular import with _config
    
    def _get_supabase(self):
        if self._supabase is None:
            # Lazy import to avoid _config import during module import time
            from clients.supabase_client import get_supabase_client
            self._supabase = get_supabase_client()
        return self._supabase
    
    def _increment_cost(self, thread_id: str, calls_field: str, cost_field: str, cost_cents: int) -> None:
        """Increment costs using plain Supabase table operations (no RPC)."""
        try:
            sb = self._get_supabase()
            # Fetch existing row (if any)
            try:
                res = sb.table("thread_costs").select("*").eq("thread_id", thread_id).single().execute()
                row = res.data if res and getattr(res, 'data', None) else None
            except Exception:
                row = None
            
            if not row:
                # Insert a new row initialized to zeros, then set the first increments
                payload = {
                    "thread_id": thread_id,
                    "outfit_gen_calls": 0,
                    "outfit_gen_cost_cents": 0,
                    "search_calls": 0,
                    "search_cost_cents": 0,
                    "ranking_calls": 0,
                    "ranking_cost_cents": 0,
                    "flatlay_gen_calls": 0,
                    "flatlay_gen_cost_cents": 0,
                    # optional vton columns if present in schema
                    "vton_gen_calls": 0,
                    "vton_gen_cost_cents": 0,
                }
                payload[calls_field] = 1
                payload[cost_field] = int(cost_cents)
                sb.table("thread_costs").insert(payload).execute()
            else:
                # Update existing row by incrementing values
                new_calls = int((row.get(calls_field) or 0)) + 1
                new_cost = int((row.get(cost_field) or 0)) + int(cost_cents)
                sb.table("thread_costs").update({
                    calls_field: new_calls,
                    cost_field: new_cost,
                }).eq("thread_id", thread_id).execute()
        except Exception as e:
            self.log.error(f"Cost update failed for {calls_field}: {e}")
    
    def track_outfit_gen(self, thread_id: str, response: Any = None, cost_cents: Optional[int] = None) -> None:
        """Track outfit generation OpenAI call cost using actual response usage data"""
        if not thread_id:
            return
        
        if cost_cents is None and response:
            cost_cents = calculate_openai_cost_cents(response)
        
        if cost_cents:
            self._increment_cost(thread_id, "outfit_gen_calls", "outfit_gen_cost_cents", cost_cents)
    
    def track_search(self, thread_id: str, provider: str = "serpapi") -> None:
        """Track search client cost (serper=0.06 cents, serpapi=0.30 cents)"""
        if not thread_id:
            return
            
        cost_cents = 6 if provider == "serper" else 30  # 0.0006 = 0.06 cents, 0.003 = 0.30 cents
        self._increment_cost(thread_id, "search_calls", "search_cost_cents", cost_cents)
    
    def track_ranking(self, thread_id: str, response: Any = None, cost_cents: Optional[int] = None) -> None:
        """Track ranking OpenAI call cost using actual response usage data"""
        if not thread_id:
            return
        
        if cost_cents is None and response:
            cost_cents = calculate_openai_cost_cents(response)
            
        if cost_cents:
            self._increment_cost(thread_id, "ranking_calls", "ranking_cost_cents", cost_cents)
    
    def track_flatlay_gen(self, thread_id: str) -> None:
        """Track flatlay image generation (hardcoded to 1 cent)"""
        if not thread_id:
            return
            
        self._increment_cost(thread_id, "flatlay_gen_calls", "flatlay_gen_cost_cents", 1)

# Global instance
cost_logger = CostLogger()
