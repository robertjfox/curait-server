"""
Simple user selfie handler for Supabase Storage.
"""

import logging
from typing import List
from clients.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def get_user_selfie_url(filename: str) -> str:
    """
    Get public URL for a user's selfie.
    
    Args:
        filename: Filename in the bucket (e.g. "user_face_victoria_banks.png")
        
    Returns:
        Public URL of the selfie
    """
    supabase = get_supabase_client()
    bucket = "user-selfies"
    
    try:
        public_url = supabase.storage.from_(bucket).get_public_url(filename)
        return public_url
        
    except Exception as e:
        logger.error(f"❌ Failed to get selfie URL for {filename}: {e}")
        raise


def list_user_selfies() -> List[str]:
    """
    List all selfie filenames in the bucket.
    
    Returns:
        List of all filenames in the bucket
    """
    supabase = get_supabase_client()
    bucket = "user-selfies"
    
    try:
        response = supabase.storage.from_(bucket).list()
        filenames = [item['name'] for item in response if item.get('name')]
        logger.info(f"✅ Found {len(filenames)} selfies in bucket")
        return filenames
        
    except Exception as e:
        logger.error(f"❌ Failed to list selfies: {e}")
        return [] 