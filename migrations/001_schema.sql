-- Consolidated schema for Curait
--
-- This is the single source of truth for the Postgres (Supabase) schema.
-- Run in the Supabase SQL Editor against a fresh project.
--
-- Hierarchy:
--     users (1) → (N) threads (1) → (N) outfits (1) → (N) outfit_items
--
-- `threads.comments` is a JSONB array of {message, timestamp} objects — the
-- full user-side chat history for a thread. Assistant replies come in the
-- form of generated `outfits` rows keyed to `thread_id`.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_name TEXT,
    last_name TEXT,
    email TEXT UNIQUE,
    dob DATE,
    location TEXT,
    gender TEXT CHECK (gender IN ('male', 'female', 'other')),
    height_cm NUMERIC,
    weight_kg NUMERIC,
    context JSONB DEFAULT '{}'::jsonb,
    prompt_suggestions JSONB,
    prompts_last_updated TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON COLUMN users.context IS 'Long-lived user style profile (body type, preferences, etc.)';
COMMENT ON COLUMN users.prompt_suggestions IS 'JSONB object shaped like {"prompts": [string, ...]}';
COMMENT ON COLUMN users.height_cm IS 'Optional height used by the avatar generator';
COMMENT ON COLUMN users.weight_kg IS 'Optional weight used by the avatar generator';

-- ---------------------------------------------------------------------------
-- threads
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    context JSONB DEFAULT '{}'::jsonb,
    comments JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON COLUMN threads.context IS 'Evolving conversation state (constraints, learned preferences).';
COMMENT ON COLUMN threads.comments IS 'JSONB array of {message, timestamp} entries appended per user turn.';

CREATE INDEX IF NOT EXISTS idx_threads_user_id ON threads(user_id);
CREATE INDEX IF NOT EXISTS idx_threads_updated_at ON threads(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_threads_comments_gin ON threads USING GIN (comments);

-- ---------------------------------------------------------------------------
-- outfits
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outfits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    outfit_order INTEGER DEFAULT 0,
    is_cached BOOLEAN DEFAULT FALSE,
    saved BOOLEAN DEFAULT FALSE,
    feedback TEXT,
    vton_image_url TEXT,
    default_rendering_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON COLUMN outfits.is_cached IS 'Pre-generated outfit held in reserve for the next regeneration.';
COMMENT ON COLUMN outfits.saved IS 'User-saved look shown in the saved looks gallery.';
COMMENT ON COLUMN outfits.vton_image_url IS 'Virtual try-on image rendered onto the user avatar.';
COMMENT ON COLUMN outfits.default_rendering_url IS 'AI-generated flatlay image of the outfit.';

CREATE INDEX IF NOT EXISTS idx_outfits_thread_id ON outfits(thread_id);
CREATE INDEX IF NOT EXISTS idx_outfits_is_cached ON outfits(is_cached);
CREATE INDEX IF NOT EXISTS idx_outfits_saved ON outfits(saved);
CREATE INDEX IF NOT EXISTS idx_outfits_order ON outfits(outfit_order);

-- ---------------------------------------------------------------------------
-- outfit_items
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outfit_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT,
    keywords TEXT,
    item_order INTEGER DEFAULT 0,
    feedback TEXT,
    search_results JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON COLUMN outfit_items.keywords IS 'Space-delimited phrase used to drive shopping search.';
COMMENT ON COLUMN outfit_items.search_results IS 'Ranked list of product candidates from Serper/SerpAPI.';

CREATE INDEX IF NOT EXISTS idx_outfit_items_outfit_id ON outfit_items(outfit_id);
CREATE INDEX IF NOT EXISTS idx_outfit_items_order ON outfit_items(item_order);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_threads_updated_at ON threads;
CREATE TRIGGER update_threads_updated_at
    BEFORE UPDATE ON threads FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_outfits_updated_at ON outfits;
CREATE TRIGGER update_outfits_updated_at
    BEFORE UPDATE ON outfits FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_outfit_items_updated_at ON outfit_items;
CREATE TRIGGER update_outfit_items_updated_at
    BEFORE UPDATE ON outfit_items FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- This is a no-auth MVP: the browser talks to Postgres directly via the anon
-- key for all CRUD (guest user provisioning, thread/outfit reads, realtime
-- subscriptions). We therefore disable RLS on the app tables. When a real
-- auth story is added, flip these back on and write per-table policies keyed
-- off `auth.uid()`.
-- ---------------------------------------------------------------------------
ALTER TABLE users        DISABLE ROW LEVEL SECURITY;
ALTER TABLE threads      DISABLE ROW LEVEL SECURITY;
ALTER TABLE outfits      DISABLE ROW LEVEL SECURITY;
ALTER TABLE outfit_items DISABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- Storage buckets
-- ---------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES
    ('virtual-tryon-images',     'virtual-tryon-images',     true),
    ('product-ranking-grids',    'product-ranking-grids',    true),
    ('vton-image-input-grid',    'vton-image-input-grid',    true),
    ('processed-bg-removal-imgs','processed-bg-removal-imgs',true),
    ('user-selfies',             'user-selfies',             true),
    ('user-avatars',             'user-avatars',             true),
    ('outfit-flatlay-images',    'outfit-flatlay-images',    true)
ON CONFLICT (id) DO NOTHING;
