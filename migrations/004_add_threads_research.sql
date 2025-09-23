-- Migration 004: Add research column (TEXT) to threads

ALTER TABLE threads
ADD COLUMN IF NOT EXISTS research TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN threads.research IS 'LLM-generated research for the thread (stored as text, may be JSON string)';


