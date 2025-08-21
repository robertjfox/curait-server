# Database Migrations

This directory contains SQL migration files for the AI Stylist database schema.

## Schema Overview

The database uses a **thread-based conversational architecture** similar to ChatGPT:

```
Users (1) ──→ (N) Threads (1) ──→ (N) Messages (1) ──→ (N) Outfits (1) ──→ (N) Outfit_Items
```

## Tables

### **users**

- User profiles and long-lived style preferences
- Stores personal info and persistent style context

### **threads**

- Conversation threads for ChatGPT-style interactions
- Each thread maintains evolving conversation state

### **messages**

- Individual conversation turns (user/assistant/system)
- Links to generated outfits when assistant provides styling

### **outfits**

- AI-generated styling recommendations
- Linked to the assistant message that created them

### **outfit_items**

- Individual clothing items within outfits
- Contains search results and product links

## Running Migrations

### Supabase (Recommended)

1. Run `001_initial_schema.sql` in Supabase SQL Editor
2. Run `002_create_storage_buckets.sql` in Supabase SQL Editor
3. Verify tables and storage buckets are created correctly
4. Ensure Storage is enabled in your Supabase project settings

### Local PostgreSQL

```bash
# Run migrations in order
psql -d your_database -f migrations/001_initial_schema.sql
```

### Environment Setup

Make sure your `.env` file has the correct database connection:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

## Migration Files

- `001_initial_schema.sql` - Core thread-based schema for ChatGPT-style UX
- `002_create_storage_buckets.sql` - Storage buckets for images and assets
- Future migrations will be numbered sequentially

## Schema Benefits

✅ **ChatGPT-like UX** - Persistent conversation threads  
✅ **Clean relationships** - Clear data hierarchy  
✅ **Performance optimized** - Proper indexes  
✅ **Audit trail** - All conversations and styling saved  
✅ **Scalable** - Easy to add features without breaking changes
