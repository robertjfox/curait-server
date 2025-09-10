-- Migration 004: Create thread_costs table and cost tracking functions
-- Adds cost tracking functionality for AI operations per thread

-- Create thread_costs table
CREATE TABLE thread_costs (
    id SERIAL PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    outfit_gen_calls NUMERIC DEFAULT 0,
    outfit_gen_cost_cents NUMERIC DEFAULT 0,
    search_calls NUMERIC DEFAULT 0,
    search_cost_cents NUMERIC DEFAULT 0,
    ranking_calls NUMERIC DEFAULT 0,
    ranking_cost_cents NUMERIC DEFAULT 0,
    flatlay_gen_calls NUMERIC DEFAULT 0,
    flatlay_gen_cost_cents NUMERIC DEFAULT 0,
    vton_gen_calls NUMERIC DEFAULT 0,
    vton_gen_cost_cents NUMERIC DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create unique index on thread_id
CREATE UNIQUE INDEX idx_thread_costs_thread_id ON thread_costs(thread_id);

-- Create function to increment thread costs atomically
CREATE OR REPLACE FUNCTION increment_thread_cost(
    p_thread_id UUID,
    p_calls_field TEXT,
    p_cost_field TEXT,
    p_cost_increment NUMERIC
) RETURNS VOID AS $$
BEGIN
    -- Use dynamic SQL to update the specified fields
    EXECUTE format(
        'UPDATE thread_costs SET %I = %I + 1, %I = %I + $1, updated_at = NOW() WHERE thread_id = $2',
        p_calls_field, p_calls_field, p_cost_field, p_cost_field
    ) USING p_cost_increment, p_thread_id;
    
    -- If no rows were updated, the record doesn't exist, so create it
    IF NOT FOUND THEN
        -- Insert new record with the incremented values
        EXECUTE format(
            'INSERT INTO thread_costs (thread_id, %I, %I) VALUES ($2, 1, $1)',
            p_calls_field, p_cost_field
        ) USING p_cost_increment, p_thread_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Add trigger to automatically update updated_at
CREATE TRIGGER update_thread_costs_updated_at 
    BEFORE UPDATE ON thread_costs 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Add comment for documentation
COMMENT ON TABLE thread_costs IS 'Cost tracking for AI operations per conversation thread';
COMMENT ON FUNCTION increment_thread_cost IS 'Atomically increment call count and cost for a specific operation type'; 