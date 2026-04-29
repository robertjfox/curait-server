from __future__ import annotations
import os
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from interfaces import db, aexec

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["saved-products"])


class ToggleSavedProductRequest(BaseModel):
	saved: bool
	product: Dict[str, Any]
	outfit_id: Optional[str] = None
	outfit_item_id: Optional[str] = None


@router.post("/{user_id}/saved-products", response_model=dict)
async def toggle_saved_product(user_id: str, request: ToggleSavedProductRequest):
	"""Save or un-save a product snapshot for the user.

	Save = upsert by (user_id, link). Un-save = delete the matching row.
	"""
	link = request.product.get("link")
	if not link:
		raise HTTPException(status_code=400, detail="Product is missing a link")

	try:
		if request.saved:
			row = await aexec(
				db.saved_products.upsert,
				user_id=user_id,
				product=request.product,
				outfit_id=request.outfit_id,
				outfit_item_id=request.outfit_item_id,
				api_provider=os.getenv("SEARCH_PROVIDER", "serper").lower().strip(),
			)
			if not row:
				raise HTTPException(status_code=500, detail="Failed to save product")
			return {"success": True, "saved_product": row}

		await aexec(db.saved_products.delete_by_link, user_id=user_id, link=link)
		return {"success": True}

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Saved product toggle failed for user {user_id[:6]}: {e}")
		raise HTTPException(status_code=500, detail="Saved product toggle failed")


@router.get("/{user_id}/saved-products", response_model=dict)
async def list_saved_products(user_id: str):
	"""Return every product the user has saved, newest first."""
	try:
		products = await aexec(db.saved_products.list_by_user, user_id)
		return {"success": True, "products": products}
	except Exception as e:
		logger.error(f"❌ Listing saved products failed for {user_id[:6]}: {e}")
		raise HTTPException(status_code=500, detail="List saved products failed")
