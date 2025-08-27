-- Migration 003: Add default rendering URL field to outfits table
-- Adds support for storing flatlay image URLs for outfit visualization

-- Add default_rendering_url column to outfits table
ALTER TABLE outfits ADD COLUMN default_rendering_url TEXT;

-- Add comment for documentation
COMMENT ON COLUMN outfits.default_rendering_url IS 'URL for the AI-generated flatlay image of this outfit'; 