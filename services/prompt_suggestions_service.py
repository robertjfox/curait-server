from __future__ import annotations
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timezone

from interfaces.users_interface import UsersInterface
from interfaces.threads_interface import ThreadsInterface
from interfaces.messages_interface import MessagesInterface
from clients.openai_client import get_openai_client

logger = logging.getLogger(__name__)

class PromptSuggestionsService:
    """Service to generate and persist short prompt suggestions for a user."""

    def __init__(self) -> None:
        self.users = UsersInterface()
        self.threads = ThreadsInterface()
        self.messages = MessagesInterface()
        self.openai = get_openai_client()

    async def generate_and_save(self, user_id: str, *, max_threads: int = 10, ignore_throttle: bool = False) -> List[str]:
        """Compute prompt suggestions from user context + first messages of recent threads."""
        try:
            user_row = self.users.get(user_id)

            # Only accept JSONB object {"prompts": [...]}
            existing_prompts_raw = (user_row or {}).get("prompt_suggestions") if user_row else None
            existing_prompts: List[str] = []
            if isinstance(existing_prompts_raw, dict) and isinstance(existing_prompts_raw.get("prompts"), list):
                existing_prompts = [str(p).strip() for p in existing_prompts_raw.get("prompts") if str(p).strip()]

            # Throttle check
            last_updated_raw = (user_row or {}).get("prompts_last_updated") if user_row else None
            now_utc = datetime.now(timezone.utc)
            if (not ignore_throttle) and isinstance(last_updated_raw, str) and last_updated_raw:
                ts_str = last_updated_raw.replace("Z", "+00:00")
                try:
                    last_dt = datetime.fromisoformat(ts_str)
                except Exception:
                    last_dt = None
                if last_dt is not None and last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if last_dt is not None:
                    delta_sec = (now_utc - last_dt).total_seconds()
                    if delta_sec >= 0 and delta_sec < 90 and len(existing_prompts) >= 1:
                        return existing_prompts[:4]

            user_data = self.users.get_relevant_context(user_id) or {}

            recent_threads = self.threads.list_recent_by_user(user_id, limit=max_threads)
            first_messages: List[str] = []
            for t in recent_threads:
                msg = self.messages.get_first_user_message(t["id"]) if t and t.get("id") else None
                if msg:
                    first_messages.append(msg)

            prompts = await self.openai.generate_prompt_suggestions(
                user_data=user_data,
                first_messages=first_messages[:max_threads],
                existing_prompts=existing_prompts[:4] if existing_prompts else None,
            )

            # Persist to user table as JSONB: {"prompts": [...]}
            try:
                payload = {
                    "prompt_suggestions": {"prompts": prompts},
                    "prompts_last_updated": now_utc.isoformat(),
                }
                self.users.update(user_id, payload)
            except Exception as e:
                logger.warning(f"[Prompts] user={user_id[:6]} failed to persist prompts: {e}")

            return prompts
        except Exception as e:
            logger.error(f"PromptSuggestionsService failed for user {user_id[:6]}: {e}")
            raise 