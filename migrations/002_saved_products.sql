-- Saved products: snapshot of a Serper/SerpApi search result that the
-- user explicitly hearted from the products view. The full Serper/SerpApi
-- payload is preserved in `snapshot` so we can recreate the original
-- product card UI even if pricing/availability changes later. Top-level
-- columns mirror the most queried fields for indexing/filtering.

CREATE TABLE IF NOT EXISTS saved_products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    outfit_id UUID REFERENCES outfits(id) ON DELETE SET NULL,
    outfit_item_id UUID REFERENCES outfit_items(id) ON DELETE SET NULL,

    link TEXT NOT NULL,
    title TEXT,
    price TEXT,
    image_url TEXT,
    source TEXT,
    product_id TEXT,
    rating NUMERIC,
    rating_count INTEGER,

    api_provider TEXT,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (user_id, link)
);

COMMENT ON COLUMN saved_products.snapshot IS 'Full search result payload at save time (Serper/SerpApi shape).';
COMMENT ON COLUMN saved_products.api_provider IS 'Search provider that produced this result (serper|serpapi).';

CREATE INDEX IF NOT EXISTS idx_saved_products_user_id ON saved_products(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_products_outfit_id ON saved_products(outfit_id);
CREATE INDEX IF NOT EXISTS idx_saved_products_outfit_item_id ON saved_products(outfit_item_id);

DROP TRIGGER IF EXISTS update_saved_products_updated_at ON saved_products;
CREATE TRIGGER update_saved_products_updated_at
    BEFORE UPDATE ON saved_products FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE saved_products DISABLE ROW LEVEL SECURITY;
