from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import logging

from clients.openai_client import get_openai_client
from interfaces import db, aexec
from services.prompt_suggestions_service import get_prompt_suggestions_service

logger = logging.getLogger(__name__)


class StyleContextService:
	"""Builds a slow, high-effort styling synthesis from onboarding context."""

	def __init__(self) -> None:
		self.openai = get_openai_client()

	async def synthesize_and_save(self, user_id: str) -> Dict[str, Any] | None:
		try:
			user = await aexec(db.users.get, user_id)
			if not user:
				logger.warning("[StyleContext] user=%s not found", user_id[:6])
				return None

			raw_context = user.get("onboarding_raw_context") or {}
			if not isinstance(raw_context, dict):
				raw_context = {}

			now = datetime.now(timezone.utc).isoformat()
			await aexec(
				db.users.update,
				user_id,
				{
					"context": {
						"style_context_synthesis_status": "pending",
						"style_context_synthesis_started_at": now,
					}
				},
			)

			user_data = {
				"gender": user.get("gender"),
				"location": user.get("location"),
				"onboarding_raw_context": raw_context,
			}
			synthesis = await self.openai.synthesize_style_context(user_data=user_data)

			completed_at = datetime.now(timezone.utc).isoformat()
			await aexec(
				db.users.update,
				user_id,
				{
					"context": {
						**synthesis,
						"style_context_synthesis_status": "complete",
						"style_context_synthesis_completed_at": completed_at,
					}
				},
			)
			logger.info("[StyleContext] user=%s synthesis complete", user_id[:6])
			try:
				await get_prompt_suggestions_service().generate_and_save(
					user_id,
					ignore_throttle=True,
				)
			except Exception as prompt_exc:
				logger.warning(
					"[StyleContext] user=%s prompt suggestion refresh failed: %s",
					user_id[:6],
					prompt_exc,
				)
			return synthesis
		except Exception as exc:
			logger.error("[StyleContext] user=%s synthesis failed: %s", user_id[:6], exc)
			try:
				user = await aexec(db.users.get, user_id)
				context = (user or {}).get("context") or {}
				if not isinstance(context, dict):
					context = {}
				await aexec(
					db.users.update,
					user_id,
					{
						"context": {
							**context,
							"style_context_synthesis_status": "failed",
							"style_context_synthesis_error": str(exc),
						}
					},
				)
			except Exception:
				pass
			return None


_service: Optional[StyleContextService] = None


def get_style_context_service() -> StyleContextService:
	global _service
	if _service is None:
		_service = StyleContextService()
	return _service
