from __future__ import annotations
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timezone

from interfaces import db, aexec
from clients.openai_client import get_openai_client

logger = logging.getLogger(__name__)


class PromptSuggestionsService:
	"""Generate and persist short prompt suggestions for a user."""

	def __init__(self) -> None:
		self.openai = get_openai_client()

	async def generate_and_save(
		self,
		user_id: str,
		*,
		max_threads: int = 10,
		ignore_throttle: bool = False,
	) -> List[str]:
		"""Compute prompt suggestions from user context + first messages of recent threads."""
		try:
			user_row = await aexec(db.users.get, user_id)

			existing_prompts_raw = (user_row or {}).get("prompt_suggestions") if user_row else None
			existing_prompts: List[str] = []
			if isinstance(existing_prompts_raw, dict) and isinstance(existing_prompts_raw.get("prompts"), list):
				existing_prompts = [str(p).strip() for p in existing_prompts_raw.get("prompts") if str(p).strip()]

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

			user_data = await aexec(db.users.get_relevant_context, user_id) or {}

			recent_threads = await aexec(db.threads.list_recent_by_user, user_id, max_threads)
			first_messages: List[str] = []
			for t in recent_threads:
				thread_id = t.get("id") if t else None
				if not thread_id:
					continue
				comments = await aexec(db.threads.get_comments, thread_id)
				if comments:
					first_messages.append(comments[0].get("message", ""))

			prompts = await self.openai.generate_prompt_suggestions(
				user_data=user_data,
				first_messages=first_messages[:max_threads],
				existing_prompts=existing_prompts[:4] if existing_prompts else None,
			)

			try:
				payload = {
					"prompt_suggestions": {"prompts": prompts},
					"prompts_last_updated": now_utc.isoformat(),
				}
				await aexec(db.users.update, user_id, payload)
			except Exception as e:
				logger.warning(f"[Prompts] user={user_id[:6]} failed to persist prompts: {e}")

			return prompts
		except Exception as e:
			logger.error(f"PromptSuggestionsService failed for user {user_id[:6]}: {e}")
			raise


_service: Optional[PromptSuggestionsService] = None


def get_prompt_suggestions_service() -> PromptSuggestionsService:
	global _service
	if _service is None:
		_service = PromptSuggestionsService()
	return _service
