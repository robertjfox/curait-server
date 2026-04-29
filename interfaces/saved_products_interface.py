from __future__ import annotations
from typing import Any, Dict, List, Optional
import logging

from clients.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SavedProductsInterface:
	"""CRUD operations for the saved_products table."""

	def __init__(self) -> None:
		self._supabase = get_supabase_client()
		self._table = "saved_products"

	def _flatten(self, product: Dict[str, Any]) -> Dict[str, Any]:
		"""Pluck the queryable columns out of a Serper/SerpApi product payload."""
		return {
			"link": product.get("link"),
			"title": product.get("title"),
			"price": product.get("price"),
			"image_url": product.get("imageUrl") or product.get("image_url"),
			"source": product.get("source"),
			"product_id": product.get("productId") or product.get("product_id"),
			"rating": product.get("rating"),
			"rating_count": product.get("ratingCount") or product.get("rating_count"),
		}

	def upsert(
		self,
		*,
		user_id: str,
		product: Dict[str, Any],
		outfit_id: Optional[str] = None,
		outfit_item_id: Optional[str] = None,
		api_provider: Optional[str] = None,
	) -> Optional[Dict[str, Any]]:
		"""Create or update a saved product keyed on (user_id, link)."""
		flat = self._flatten(product)
		link = flat.get("link")
		if not link:
			logger.warning("Cannot save product without a link")
			return None

		payload: Dict[str, Any] = {
			"user_id": user_id,
			"outfit_id": outfit_id,
			"outfit_item_id": outfit_item_id,
			**flat,
			"api_provider": api_provider,
			"snapshot": product,
		}

		try:
			res = (
				self._supabase
				.table(self._table)
				.upsert(payload, on_conflict="user_id,link")
				.execute()
			)
			return res.data[0] if res.data else None
		except Exception as e:
			logger.error(f"Failed to upsert saved product for user {user_id[:6]}: {e}")
			return None

	def delete_by_link(self, *, user_id: str, link: str) -> bool:
		try:
			self._supabase.table(self._table).delete().eq("user_id", user_id).eq("link", link).execute()
			return True
		except Exception as e:
			logger.error(f"Failed to delete saved product: {e}")
			return False

	def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
		try:
			res = (
				self._supabase
				.table(self._table)
				.select("*")
				.eq("user_id", user_id)
				.order("created_at", desc=True)
				.execute()
			)
			return res.data or []
		except Exception as e:
			logger.error(f"Failed to list saved products for user {user_id[:6]}: {e}")
			return []
