#!/usr/bin/env python3
"""
Storage Bucket Creation Script
Creates all required Supabase storage buckets for the AI Stylist system.
Run this after setting up your Supabase environment variables.
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

def create_storage_buckets():
    """Create all required storage buckets."""
    
    # Check environment variables
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables")
        print("   Please set these in your .env file")
        return False
    
    try:
        # Initialize Supabase client
        supabase = create_client(supabase_url, supabase_key)
        
        # Define buckets to create
        buckets = [
            {"id": "virtual-tryon-images", "name": "virtual-tryon-images", "public": True},
            {"id": "product-ranking-grids", "name": "product-ranking-grids", "public": True},
            {"id": "vton-image-input-grid", "name": "vton-image-input-grid", "public": True},
            {"id": "processed-bg-removal-imgs", "name": "processed-bg-removal-imgs", "public": True},
            {"id": "user-selfies", "name": "user-selfies", "public": True},
            {"id": "user-avatars", "name": "user-avatars", "public": True},
        ]
        
        print("🗄️ Creating Supabase Storage Buckets")
        print("=" * 40)
        
        created = 0
        skipped = 0
        
        for bucket in buckets:
            try:
                # Try to create the bucket (Supabase Python client syntax)
                result = supabase.storage.create_bucket(bucket["id"])
                print(f"✅ Created bucket: {bucket['id']}")
                created += 1
                
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"⚠️ Bucket already exists: {bucket['id']}")
                    skipped += 1
                else:
                    print(f"❌ Failed to create bucket {bucket['id']}: {e}")
                    return False
        
        print(f"\n📊 Results: {created} created, {skipped} already existed")
        print("🎉 All storage buckets ready!")
        
        # List all buckets to verify
        try:
            all_buckets = supabase.storage.list_buckets()
            ai_stylist_buckets = [b for b in all_buckets if b.name in [bucket["id"] for bucket in buckets]]
            print(f"\n✅ Verified {len(ai_stylist_buckets)} AI Stylist buckets exist:")
            for bucket in ai_stylist_buckets:
                print(f"   • {bucket.name} (public: {bucket.public})")
        except Exception as e:
            print(f"⚠️ Could not verify buckets: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Storage bucket creation failed: {e}")
        return False


if __name__ == "__main__":
    print("🪣 AI Stylist Storage Bucket Setup")
    print("Creating all required Supabase storage buckets...")
    print()
    
    success = create_storage_buckets()
    
    if success:
        print("\n🚀 Storage setup complete!")
        print("You can now run the user journey test with full image processing.")
    else:
        print("\n🚨 Storage setup failed!")
        print("Please check your Supabase configuration and try again.")
    
    sys.exit(0 if success else 1) 