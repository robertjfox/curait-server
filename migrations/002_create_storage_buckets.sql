-- Migration 002: Create Storage Buckets
-- Creates required Supabase storage buckets for AI Stylist

-- Create storage buckets (run in Supabase SQL Editor)
INSERT INTO storage.buckets (id, name, public)
VALUES 
    ('virtual-tryon-images', 'virtual-tryon-images', true),
    ('product-ranking-grids', 'product-ranking-grids', true),
    ('vton-image-input-grid', 'vton-image-input-grid', true),
    ('processed-bg-removal-imgs', 'processed-bg-removal-imgs', true),
    ('user-selfies', 'user-selfies', true),
    ('outfit-flatlay-images', 'outfit-flatlay-images', true)
ON CONFLICT (id) DO NOTHING; 