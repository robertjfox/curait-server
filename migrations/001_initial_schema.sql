-- Migration 001: Initial schema for ChatGPT-style AI Stylist
-- Creates the core thread-based conversation and styling schema

-- Enable UUID extension for primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table: Core user profiles and preferences
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_name TEXT,
    last_name TEXT,
    email TEXT UNIQUE,
    dob DATE,
    location TEXT,
    gender TEXT CHECK (gender IN ('male', 'female', 'other')),
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Threads table: Conversation threads (ChatGPT-style)
CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages table: Individual conversation turns
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Outfits table: Generated styling recommendations
CREATE TABLE outfits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    outfit_order INTEGER DEFAULT 0,
    is_cached BOOLEAN DEFAULT FALSE,
    vton_image_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Outfit_Items table: Individual clothing items within outfits
CREATE TABLE outfit_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    keywords TEXT,
    item_order INTEGER DEFAULT 0,
    search_results JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_threads_user_id ON threads(user_id);
CREATE INDEX idx_threads_updated_at ON threads(updated_at DESC);
CREATE INDEX idx_threads_comments ON threads USING GIN (comments);
CREATE INDEX idx_outfits_thread_id ON outfits(thread_id);
CREATE INDEX idx_outfits_is_cached ON outfits(is_cached);
CREATE INDEX idx_outfits_order ON outfits(outfit_order);
CREATE INDEX idx_outfit_items_outfit_id ON outfit_items(outfit_id);
CREATE INDEX idx_outfit_items_order ON outfit_items(item_order);

-- Function to automatically update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to automatically update updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_threads_updated_at BEFORE UPDATE ON threads FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_outfits_updated_at BEFORE UPDATE ON outfits FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_outfit_items_updated_at BEFORE UPDATE ON outfit_items FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE users IS 'User profiles and long-lived style preferences';
COMMENT ON TABLE threads IS 'Conversation threads with embedded comments as JSONB';
COMMENT ON TABLE outfits IS 'AI-generated styling recommendations linked to threads';
COMMENT ON TABLE outfit_items IS 'Individual clothing items within styled outfits';

COMMENT ON COLUMN users.context IS 'Long-lived user preferences and style profile (body type, style preferences, etc.)';
COMMENT ON COLUMN threads.context IS 'Evolving conversation state (constraints, filters, learned preferences for this thread)';
COMMENT ON COLUMN threads.comments IS 'JSONB array of user comments with message and timestamp';
COMMENT ON COLUMN outfits.is_cached IS 'Flag indicating if this outfit is cached/processed';
COMMENT ON COLUMN outfit_items.search_results IS 'Product search results with URLs, prices, and thumbnails'; 