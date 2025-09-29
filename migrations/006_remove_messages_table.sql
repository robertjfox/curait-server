-- Migration 6: Remove messages table and simplify architecture
-- Replaces messages table with comments JSONB field on threads table

-- Add comments column to threads table for user comments
ALTER TABLE threads ADD COLUMN IF NOT EXISTS comments JSONB DEFAULT '[]';

-- Add explore_idea_id to threads table for linking to explore ideas
ALTER TABLE threads ADD COLUMN IF NOT EXISTS explore_idea_id UUID REFERENCES explore_ideas(id);

-- Add is_cached column to outfits table
ALTER TABLE outfits ADD COLUMN IF NOT EXISTS is_cached BOOLEAN DEFAULT FALSE;

-- Remove message_id column from outfits table since we're eliminating messages entirely
ALTER TABLE outfits DROP COLUMN IF EXISTS message_id;

-- Add new indexes
CREATE INDEX IF NOT EXISTS idx_threads_comments ON threads USING GIN (comments);
CREATE INDEX IF NOT EXISTS idx_outfits_is_cached ON outfits(is_cached);

-- Drop old indexes that reference messages
DROP INDEX IF EXISTS idx_messages_thread_id;
DROP INDEX IF EXISTS idx_messages_created_at;

-- Drop the messages table
DROP TABLE IF EXISTS messages CASCADE;

-- Update comments for documentation
COMMENT ON TABLE threads IS 'Conversation threads with embedded comments as JSONB';
COMMENT ON TABLE outfits IS 'AI-generated styling recommendations linked to threads';

COMMENT ON COLUMN threads.comments IS 'JSONB array of user comments with message and timestamp';
COMMENT ON COLUMN outfits.is_cached IS 'Flag indicating if this outfit is cached/processed';
