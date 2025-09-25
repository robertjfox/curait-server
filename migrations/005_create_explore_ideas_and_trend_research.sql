-- Migration 005: Explore Ideas + Trend Research + Outfits linkage

-- Ensure UUID extension exists (safe if already created)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ================================================
-- Table: trend_research
-- Stores daily deep research blobs per gender
-- ================================================
CREATE TABLE IF NOT EXISTS trend_research (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gender TEXT NOT NULL CHECK (gender IN ('male', 'female')),
    research TEXT NOT NULL,
    research_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trend_research_date_gender ON trend_research (research_date DESC, gender);

COMMENT ON TABLE trend_research IS 'Daily LLM deep research for fashion trends by gender';
COMMENT ON COLUMN trend_research.gender IS 'male or female';
COMMENT ON COLUMN trend_research.research IS 'Deep research output (JSON or text)';
COMMENT ON COLUMN trend_research.research_date IS 'Logical date the research applies to';

-- ================================================
-- Table: explore_ideas
-- Pre-generated ideas for the Explore landing page
-- ================================================
CREATE TABLE IF NOT EXISTS explore_ideas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    description TEXT,
    concept_outfits JSONB DEFAULT '{}'::jsonb,
    image_url TEXT,
    gender TEXT NOT NULL CHECK (gender IN ('male', 'female')),
    idea_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
    rank SMALLINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enforce at most 4 per gender/day and stable ordering positions
CREATE UNIQUE INDEX IF NOT EXISTS uq_explore_ideas_date_gender_rank ON explore_ideas (idea_date, gender, rank);
CREATE INDEX IF NOT EXISTS idx_explore_ideas_date_gender ON explore_ideas (idea_date DESC, gender);

COMMENT ON TABLE explore_ideas IS 'Daily curated explore ideas with representative image';
COMMENT ON COLUMN explore_ideas.concept_outfits IS 'Structured JSON for the archetypal outfit concept';
COMMENT ON COLUMN explore_ideas.gender IS 'male or female';
COMMENT ON COLUMN explore_ideas.status IS 'draft|published|archived';

-- Reuse the existing timestamp update trigger function from 001 if present
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc WHERE proname = 'update_updated_at_column'
    ) THEN
        BEGIN
            CREATE TRIGGER update_explore_ideas_updated_at
            BEFORE UPDATE ON explore_ideas
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        EXCEPTION WHEN duplicate_object THEN
            -- Trigger already exists; ignore
            NULL;
        END;
    END IF;
END $$;

-- ================================================
-- Outfits linkage: add optional reference to explore_ideas
-- ================================================
ALTER TABLE outfits
ADD COLUMN IF NOT EXISTS explore_idea_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_outfits_explore_idea_id'
          AND table_name = 'outfits'
    ) THEN
        ALTER TABLE outfits
        ADD CONSTRAINT fk_outfits_explore_idea_id
        FOREIGN KEY (explore_idea_id)
        REFERENCES explore_ideas(id)
        ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_outfits_explore_idea_id ON outfits (explore_idea_id);

COMMENT ON COLUMN outfits.explore_idea_id IS 'Optional link to explore_ideas for pre-generated concepts';

