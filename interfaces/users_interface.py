from typing import Any, Dict, Optional
from clients.supabase_client import get_supabase_client


class UsersInterface:
    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "users"

    def upsert(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "id" not in payload or not payload["id"]:
            raise ValueError("User 'id' is required to upsert")
        response = self._supabase.table(self._table).upsert(payload, on_conflict="id").execute()
        data = response.data
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        response = self._supabase.table(self._table).select("*").eq("id", user_id).single().execute()
        return response.data

    def update(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not updates:
            return self.get(user_id)
        response = self._supabase.table(self._table).update(updates).eq("id", user_id).execute()
        data = response.data
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return None

    def get_relevant_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        user = self.get(user_id)

        if not user:
            return None
        
        exclude_fields = {
            'id', 'email', 'created_at', 'updated_at'
        }

        result: Dict[str, Any] = {k: v for k, v in user.items() if k not in exclude_fields and v is not None}

        return result

    def find_by_name(self, first_name: str, last_name: str | None = None) -> Optional[Dict[str, Any]]:
        query = self._supabase.table(self._table).select("*")
        query = query.ilike("first_name", f"%{first_name}%")
        if last_name:
            query = query.ilike("last_name", f"%{last_name}%")
        query = query.order("created_at")
        response = query.execute()
        if response.data:
            user = response.data[0]
            if len(response.data) > 1:
                print(f"Multiple users found, taking first: {user.get('first_name', '')} {user.get('last_name', '')} ({user['id']})")
            return user
        return None 