from fastapi import APIRouter, HTTPException

import logging
import time

from models import VirtualTryOnRequest, VirtualTryOnResponse
from services.virtual_tryon_service import VirtualTryOnService
from interfaces.outfits_interface import OutfitsInterface
from interfaces.outfit_items_interface import OutfitItemsInterface

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["virtual-try-on"])

virtual_tryon_service = VirtualTryOnService()
outfits_interface = OutfitsInterface()
outfit_items_interface = OutfitItemsInterface()


@router.post("/virtual-try-on", response_model=VirtualTryOnResponse)
async def virtual_try_on(request: VirtualTryOnRequest):
    try:
        # Prepare products from thumbnail URLs
        if not request.thumbnails:
            raise HTTPException(status_code=400, detail="No thumbnails provided for virtual try-on")
        
        item_products = []
        
        # If we have outfit_id, lookup item types from outfit items
        if request.outfit_id:
            outfit_items = outfit_items_interface.get_by_outfit(request.outfit_id)
            url_to_type = {}
            
            # Build mapping of image URLs to item types
            for item in outfit_items:
                item_type = item.get("type", "Item")
                search_results = item.get("search_results", [])
                for product in search_results:
                    image_url = (
                        product.get("imageUrl") or 
                        product.get("thumbnail") or 
                        product.get("image_url") or 
                        product.get("serpapi_thumbnail") or
                        ""
                    )
                    if image_url:
                        url_to_type[image_url] = item_type
            
            # Match thumbnails to types
            for i, image_url in enumerate(request.thumbnails):
                if not image_url:
                    continue
                item_type = url_to_type.get(image_url, f"Item {i + 1}")
                item_products.append({
                    "imageUrl": image_url,
                    "title": item_type
                })
        else:
            # No outfit_id, use generic labels
            for i, image_url in enumerate(request.thumbnails):
                if not image_url:
                    continue
                item_products.append({
                    "imageUrl": image_url,
                    "title": f"Item {i + 1}"
                })
        
        if not item_products:
            raise HTTPException(status_code=400, detail="No valid thumbnails provided")
        
        logger.info(f"🎯 Starting VTON with {len(item_products)} products")
        
        result = await virtual_tryon_service.generate_virtual_tryon(item_products=item_products)
        
        # Extract image URL from service result
        image_url = result.get("image_url", "")
        
        # Save VTON image URL to outfit record if provided
        if image_url and request.outfit_id:
            try:
                outfits_interface.update_vton_image(request.outfit_id, image_url)
            except Exception as e:
                logger.warning(f"⚠️ Failed to persist VTON URL to outfit {request.outfit_id}: {e}")
        
        return VirtualTryOnResponse(image_url=image_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in virtual try-on: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Virtual try-on failed: {str(e)}") 