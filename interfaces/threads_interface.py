from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from clients.supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)

class ThreadsInterface:
    """CRUD operations for the threads table."""

    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "threads"

    def create(
        self,
        user_id: str,
        explore_idea_id: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new thread and return its ID."""
        payload: Dict[str, Any] = {
            "user_id": user_id,
        }

        if explore_idea_id:
            payload["explore_idea_id"] = explore_idea_id
            # If we have an explore_idea_id, fetch the title from the explore idea
            explore_idea = self._get_explore_idea_by_id(explore_idea_id)
            if explore_idea:
                payload["title"] = explore_idea.get("title", "Explore Idea Thread")
        try:
            res = self._supabase.table(self._table).insert(payload).execute()
            return res.data[0]["id"] if res and res.data else None
        except Exception:
            return None

    def _get_explore_idea_by_id(self, explore_idea_id: str) -> Optional[Dict[str, Any]]:
        """Get an explore idea by ID."""
        try:
            res = self._supabase.table("explore_ideas").select("*").eq("id", explore_idea_id).single().execute()
            return res.data
        except Exception:
            return None

    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get a single thread by ID."""
        try:
            res = self._supabase.table(self._table).select("*").eq("id", thread_id).single().execute()
            return res.data
        except Exception:
            return None

    def update_title(self, thread_id: str, title: str) -> bool:
        """Update the title for a thread."""
        try:
            self._supabase.table(self._table).update({
                "title": title,
            }).eq("id", thread_id).execute()
            return True
        except Exception:
            return False

    def update_research(self, thread_id: str, research: Dict[str, Any]) -> bool:
        """Set thread.research TEXT to provided string (JSON string if dict)."""
        try:
            research_text = ""
            if isinstance(research, str):
                research_text = research
            else:
                try:
                    import json as _json
                    research_text = _json.dumps(research)
                except Exception:
                    research_text = str(research)

            self._supabase.table(self._table).update({
                "research": research_text,
            }).eq("id", thread_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to update thread research: {e}")
            return False

    def list_recent_by_user(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent threads for a user, newest first."""
        try:
            res = (
                self._supabase
                    .table(self._table)
                    .select("*")
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
            )
            return res.data or []
        except Exception:
            return []

    def add_comment(self, thread_id: str, message: str) -> bool:
        """Add a user comment to the thread's comments JSONB field."""
        try:
            # Get current comments
            thread = self.get(thread_id)
            if not thread:
                return False

            current_comments = thread.get("comments") or []

            # Add new comment with timestamp
            new_comment = {
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            current_comments.append(new_comment)

            # Update the thread
            self._supabase.table(self._table).update({
                "comments": current_comments
            }).eq("id", thread_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to add comment to thread {thread_id}: {e}")
            return False

    def get_comments(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all comments for a thread."""
        try:
            thread = self.get(thread_id)
            comments = thread.get("comments") if thread else None
            return comments if comments is not None else []
        except Exception:
            return []

    def get_conversation_history(self, thread_id: str) -> List[Dict[str, str]]:
        """Get conversation history from comments in OpenAI chat format."""
        try:
            comments = self.get_comments(thread_id)
            history = []

            for comment in comments:
                history.append({
                    "role": "user",
                    "content": comment.get("message", "")
                })

            return history
        except Exception:
            return []

