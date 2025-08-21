from fastapi import APIRouter, HTTPException

import logging
import time

from models import VirtualTryOnRequest, VirtualTryOnResponse
from services.virtual_tryon_service import VirtualTryOnService
from interfaces.users_interface import UsersInterface
from interfaces.outfits_interface import OutfitsInterface
from interfaces.outfit_items_interface import OutfitItemsInterface
from interfaces.threads_interface import ThreadsInterface

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["virtual-try-on"])

virtual_tryon_service = VirtualTryOnService()
users_interface = UsersInterface()
outfits_interface = OutfitsInterface()
outfit_items_interface = OutfitItemsInterface()
threads_interface = ThreadsInterface()


@router.post("/virtual-try-on", response_model=VirtualTryOnResponse)
async def virtual_try_on(request: VirtualTryOnRequest):
    try:
        # Fetch user data
        user_data = users_interface.get_relevant_context(request.user_id)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Add user_id to user_data for face overlay functionality
        user_data["id"] = request.user_id
        
        # Fetch outfit items to get products
        outfit_items = outfit_items_interface.get_by_outfit(request.outfit_id)
        if not outfit_items:
            raise HTTPException(status_code=404, detail="Outfit not found or has no items")
        
        # Find products from search results in outfit items
        item_products = []
        for i, item in enumerate(outfit_items):
            search_results = item.get("search_results", [])
            
            for j, product in enumerate(search_results):
                if product.get("productId") in request.product_ids:
                    # Try multiple possible image field names
                    image_url = (
                        product.get("imageUrl") or 
                        product.get("thumbnail") or 
                        product.get("image_url") or 
                        product.get("serpapi_thumbnail") or
                        ""
                    )
                    
                    if not image_url:
                        logger.error(f"❌ Product {product.get('title', 'Unknown')} has no image URL")
                        continue
                    
                    item_products.append({
                        "imageUrl": image_url,
                        "title": product.get("title", f"Item {len(item_products) + 1}")
                    })
                else:
                    logger.debug(f"🔍 Product ID {product.get('productId')} not in requested IDs")
        
        if not item_products:
            raise HTTPException(status_code=400, detail="No valid products found for the provided product IDs")
        
        logger.info(f"🎯 Starting VTON with {len(item_products)} products for user {request.user_id}")
        
        result = await virtual_tryon_service.generate_virtual_tryon(
            item_products=item_products,
            gender=user_data.get("gender"),
            user_data=user_data,
            thread_id=request.thread_id,
            user_id=request.user_id,
        )
        
        # Extract image URL from service result
        image_url = result.get("image_url", "")
        
        # Save VTON image URL to outfit record
        if image_url:
            outfits_interface.update_vton_image(request.outfit_id, image_url)
        
        return VirtualTryOnResponse(image_url=image_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in virtual try-on: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Virtual try-on failed: {str(e)}") 