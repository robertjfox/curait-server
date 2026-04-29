# Database migrations

Single-file schema for Curait. Apply `001_schema.sql` once against a fresh
Supabase project (via the SQL Editor) and you're done.

## Schema shape

```
users ─1:N─► threads ─1:N─► outfits ─1:N─► outfit_items
```

- `threads.comments` — JSONB array of `{ message, timestamp }`, one entry per
  user turn. There is no separate `messages` table.
- `outfits` are keyed to `thread_id` (no `message_id`). A thread accumulates
  outfits over time as the user sends more messages.
- `outfit_items.search_results` — JSONB list of ranked product candidates
  returned by the shopping search (Serper / SerpAPI) + vision ranker.

## Storage buckets

`001_schema.sql` inserts the public storage buckets the server writes to:

| Bucket | Written by |
|---|---|
| `virtual-tryon-images` | Gemini VTON output |
| `product-ranking-grids` | Ranking grid composites |
| `vton-image-input-grid` | Thumbnail grids used as VTON input |
| `processed-bg-removal-imgs` | Background-removed assets |
| `user-selfies` | User-uploaded selfies |
| `user-avatars` | Gemini-rendered full-body avatars |
| `outfit-flatlay-images` | Outfit flatlay renderings |

## Applying

1. Open your Supabase project's SQL Editor.
2. Paste and run `001_schema.sql`.
3. Confirm tables, indexes, triggers, and buckets exist.

## Making changes

When the schema evolves, edit `001_schema.sql` in place (this is an MVP
with no production data — there's no migration runner). If you ever need
versioned migrations, drop new numbered files alongside this one and track
their application manually.
