import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


def build_prompt_suggestions_messages(user_data: Dict[str, Any], first_messages: List[str], existing_prompts: List[str] = None) -> List[Dict[str, str]]:
	"""Construct system+user messages for prompt suggestions generation."""
	system = (
		"""
		You are an AI stylist prompting assistant. 
Your job is to write short scenario prompts that another AI will later use to build outfits. 
Do NOT mention or name clothing, colors, fabrics, or accessories. 
Only describe the occasion, setting, or activity. 

Make them realistic and not lame hipster shit that nobody does.
These are not just scenarios, they are scenarios that a user would REALISTICALLY ask for from a virtual stylist AI tool.

Each prompt must be:
- One complete sentence
- Max 90 characters
- Clear, specific, and actionable
- Diverse across occasions and styles
- No quotes, emojis, hashtags, numbering, or trailing punctuation
- Appropriate for the current season and location/date provided
- Absolutely NO clothing or style suggestions in the text
- No words like suggest or recommend, because its already implied
- AVOID repeating or being too similar to any existing prompts provided
		"""
	)
	user_blob = json.dumps(user_data or {}, ensure_ascii=False)
	now_utc_iso = datetime.now(timezone.utc).date().isoformat()
	user_location = (user_data or {}).get("location")
	user_content = (
		"CURRENT_DATE_UTC:\n" + now_utc_iso + "\n\n"
		+ ("USER_LOCATION:\n" + str(user_location) + "\n\n" if user_location else "")
		+ "USER_DATA:\n" + user_blob + "\n\n"
		+ "FIRST_USER_MESSAGES_FROM_RECENT_THREADS:\n" + json.dumps(first_messages or [], ensure_ascii=False) + "\n\n"
		+ ("EXISTING_PROMPTS_TO_AVOID_REPEATING:\n" + json.dumps(existing_prompts or [], ensure_ascii=False) + "\n\n" if existing_prompts else "")
	)
	return [
		{"role": "system", "content": system},
		{"role": "user", "content": user_content},
	] 