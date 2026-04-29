"""
Simple user selfie handler for Supabase Storage.
"""

import logging
from typing import List
from clients.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

AVATAR_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"]


def get_user_selfie_url(filename: str) -> str:
    supabase = get_supabase_client()
    bucket = "user-selfies"
    
    try:
        public_url = supabase.storage.from_(bucket).get_public_url(filename)
        return public_url
        
    except Exception as e:
        logger.error(f"❌ Failed to get selfie URL for {filename}: {e}")
        raise


def get_user_avatar_url(user_id: str) -> str:
    """Return the legacy/default public avatar URL for a user.

    This does not prove the object exists. Callers that need to load the image
    should try `get_user_avatar_urls`, because avatar generation stores the
    actual extension returned by Gemini.
    """
    supabase = get_supabase_client()
    bucket = "user-avatars"
    
    filename = f"{user_id}.png"
    try:
        public_url = supabase.storage.from_(bucket).get_public_url(filename)
        logger.debug(f"🎭 Retrieved user avatar: {filename}")
        return public_url
    except Exception as e:
        logger.error(f"❌ Failed to get avatar URL for {user_id}: {e}")
        raise


def get_user_avatar_urls(user_id: str) -> List[str]:
    supabase = get_supabase_client()
    bucket = "user-avatars"

    urls: List[str] = []
    for ext in AVATAR_EXTENSIONS:
        filename = f"{user_id}{ext}"
        try:
            urls.append(supabase.storage.from_(bucket).get_public_url(filename))
        except Exception as e:
            logger.debug(f"🎭 Failed to build avatar URL for {filename}: {e}")
    return urls


def list_user_selfies() -> List[str]:
    supabase = get_supabase_client()
    bucket = "user-selfies"
    
    try:
        response = supabase.storage.from_(bucket).list()
        filenames = [item['name'] for item in response if item.get('name')]
        return filenames
        
    except Exception as e:
        logger.error(f"❌ Failed to list selfies: {e}")
        return [] 