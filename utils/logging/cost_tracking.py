import logging, os, re
from typing import Any, Dict, Optional

class CostLogger:
    # ---- Pricing ----
    MODEL_PRICING = {
        "gpt-4o": {"in": 0.0025, "out": 0.0100},
        "gpt-4o-mini": {"in": 0.00015, "out": 0.00060},
        "o4-mini": {"in": 0.00110, "out": 0.00440},
        "gpt-5": {"in": 0.00125, "out": 0.0100},
        "gpt-5-mini": {"in": 0.00025, "out": 0.00200},
        "gpt-5-nano": {"in": 0.00005, "out": 0.00040},
        "gpt-image-1": {"txt_in": 0.00500, "img_in": 0.01000, "img_out": 0.04000},
    }
    SEARCH_PRICING = {"serper": 0.0006, "serpapi": 0.0030}


    def __init__(self) -> None:
        self.log = logging.getLogger(__name__)
        self._enabled: Optional[bool] = None
        self._s: Dict[str, Dict[str, Any]] = {}


    # ---- Internals ----
    def _on(self) -> bool:
        if self._enabled is None:
            self._enabled = os.getenv("ENABLE_COST_LOGGING", "true").lower() in ("1","true","yes","on")
        return self._enabled


    def _norm(self, model: str) -> str:
        m = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model)
        return re.sub(r"-(preview|alpha|beta)(-\d{4}-\d{2}-\d{2})?$", "", m)


    def _ensure(self, sid: str) -> Dict[str, Any]:
        return self._s.setdefault(sid, {
            "outfit_gen": {"cost": 0.0, "calls": 0},
            "search": {"cost": 0.0, "calls": 0},
            "ranking": {"cost": 0.0, "calls": 0},
            "vton": {"cost": 0.0, "calls": 0},
            "total_cost": 0.0,
        })


    def _bump(self, s: Dict[str, Any], key: str, cost: float, calls: int = 1) -> None:
        s[key]["cost"] += float(cost)
        s[key]["calls"] += int(calls)
        s["total_cost"] += float(cost)


    # ---- Public, minimal surface ----
    def track_openai(
        self,
        *,
        thread_id: Optional[str],
        category: str = "outfit_gen",
        model: Optional[str] = None,
        response: Optional[Any] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        vton_quality_default: str = "medium",
    ) -> None:
        """
        One method for ALL OpenAI calls.
        Pass either (model + tokens) OR (response with .model/.usage).
        Handles text models and gpt-image-1 automatically.
        """
        if not (self._on() and thread_id):
            return
        s = self._ensure(thread_id)

        # Prefer response if given
        if response is not None:
            model = getattr(response, "model", model or "gpt-4o")
            usage = getattr(response, "usage", None)
        else:
            usage = None
            model = model or "gpt-4o"

        norm = self._norm(model)

        # Image model path
        if norm == "gpt-image-1":
            try:
                self.log.debug(f"gpt-image-1 detected, usage: {usage}")
                if usage and getattr(usage, "input_tokens_details", None) is not None:
                    txt = getattr(usage.input_tokens_details, "text_tokens", 0) or 0
                    img = getattr(usage.input_tokens_details, "image_tokens", 0) or 0
                    out = getattr(usage, "output_tokens", 0) or 0
                    p = self.MODEL_PRICING["gpt-image-1"]
                    # log image input and output cost here  
                    txt_in_p = (txt/1000.0)*p["txt_in"]
                    img_in_p = (img/1000.0)*p["img_in"]
                    img_out_p = (out/1000.0)*p["img_out"]    

                    cost = txt_in_p + img_in_p + img_out_p
                    # self.log.info(f"💰 VTON cost: {txt_in_p:.4f} txt | {img_in_p:.4f} img | {img_out_p:.4f} out = ${cost:.4f}")
                    
                else:
                    # Fallback estimate by quality
                    from _config.model_config import VIRTUAL_TRY_ON
                    q = (VIRTUAL_TRY_ON.get("quality") or vton_quality_default).lower()
                    cost = {"low":0.015, "medium":0.060, "high":0.250}.get(q, 0.060)
                    self.log.info(f"💰 VTON cost fallback (no usage): quality={q} = ${cost:.4f}")
                self._bump(s, "vton" if category=="outfit_gen" else category, cost, 1)
            except Exception as e:
                self.log.error(f"❌ VTON cost tracking failed: {e}")
                # Still track a minimal cost so we don't lose the call count  
                self._bump(s, "vton" if category=="outfit_gen" else category, 0.01, 1)
            return

        # Text model path
        p = self.MODEL_PRICING.get(norm) or self.MODEL_PRICING["gpt-4o-mini"]
        
        if usage:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost = (max(prompt_tokens,0)/1000.0)*p["in"] + (max(completion_tokens,0)/1000.0)*p["out"]
        self._bump(s, category, cost, 1)


    def track_search(self, *, thread_id: Optional[str], provider: str = "serpapi") -> None:
        if not (self._on() and thread_id):
            return
        s = self._ensure(thread_id)
        self._bump(s, "search", float(self.SEARCH_PRICING.get(provider, self.SEARCH_PRICING["serpapi"])), 1)


    def log_final_summary(self, thread_id: str) -> None:
        if not self._on():
            return
        s = self._s.get(thread_id)
        if not s:
            return
        money = lambda x: f"${x:.4f}"
        lines = [
            f"• Outfit Gen: {money(s['outfit_gen']['cost'])}",
            f"• Shopping Search: {money(s['search']['cost'])} | {s['search']['calls']} calls",
            f"• Product Ranking: {money(s['ranking']['cost'])} | {s['ranking']['calls']} calls",
            f"• VTON: {money(s['vton']['cost'])} | {s['vton']['calls']} calls",
            f"• Total Cost: {money(s['total_cost'])}",
        ]
        logging.getLogger(__name__).info("\n".join(lines))

    def reset_thread(self, thread_id: str) -> None:
        self._s.pop(thread_id, None)

    def get_total_cost_cents(self, thread_id: str) -> Optional[int]:
        """Get total cost for a thread in cents (rounded)"""
        if not self._on():
            return None
        s = self._s.get(thread_id)
        if not s:
            return None
        return round(s["total_cost"] * 100)  # Convert dollars to cents

    def has_thread_data(self, thread_id: str) -> bool:
        """Check if we have cost data for a thread"""
        return thread_id in self._s and self._on()
