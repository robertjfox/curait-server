from fastapi import APIRouter, HTTPException
import logging

from models import VirtualTryOnRequest, VirtualTryOnResponse
from services.virtual_tryon_service import get_virtual_tryon_service
from interfaces import db, aexec

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["virtual-try-on"])


@router.post("/virtual-try-on", response_model=VirtualTryOnResponse)
async def virtual_try_on(request: VirtualTryOnRequest):
	try:
		if not request.thumbnails:
			raise HTTPException(status_code=400, detail="No thumbnails provided for virtual try-on")

		item_products = []

		# If we have outfit_id, lookup item types from outfit items.
		if request.outfit_id:
			outfit_items = await aexec(db.outfit_items.get_by_outfit, request.outfit_id)
			url_to_type = {}

			for item in outfit_items:
				item_type = item.get("type", "Item")
				search_results = item.get("search_results", [])
				for product in search_results:
					image_url = (
						product.get("imageUrl")
						or product.get("thumbnail")
						or product.get("image_url")
						or product.get("serpapi_thumbnail")
						or ""
					)
					if image_url:
						url_to_type[image_url] = item_type

			for i, image_url in enumerate(request.thumbnails):
				if not image_url:
					continue
				item_type = url_to_type.get(image_url, f"Item {i + 1}")
				item_products.append({"imageUrl": image_url, "title": item_type})
		else:
			for i, image_url in enumerate(request.thumbnails):
				if not image_url:
					continue
				item_products.append({"imageUrl": image_url, "title": f"Item {i + 1}"})

		if not item_products:
			raise HTTPException(status_code=400, detail="No valid thumbnails provided")

		logger.info(f"🎯 Starting VTON with {len(item_products)} products")

		result = await get_virtual_tryon_service().generate_virtual_tryon(
			item_products=item_products,
			user_id=request.user_id,
		)

		image_url = result.get("image_url", "")

		if image_url and request.outfit_id:
			try:
				await aexec(db.outfits.update_vton_image, request.outfit_id, image_url)
			except Exception as e:
				logger.warning(f"⚠️ Failed to persist VTON URL to outfit {request.outfit_id}: {e}")

		return VirtualTryOnResponse(image_url=image_url)

	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"❌ Error in virtual try-on: {str(e)}")
		raise HTTPException(status_code=500, detail=f"Virtual try-on failed: {str(e)}")
