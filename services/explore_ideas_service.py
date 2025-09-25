import logging
from typing import Dict, Any, Literal
from datetime import date
import time
import asyncio

from clients.openai_client import get_openai_client
from clients.supabase_client import get_supabase_client
from clients.gemini_client import get_gemini_client
from ai.prompts.explore_cover import build_cover_prompt


logger = logging.getLogger(__name__)


class ExploreIdeasService:
    def __init__(self) -> None:
        self.openai_client = get_openai_client()
        self._supabase = get_supabase_client()
        try:
            self._gemini = get_gemini_client()
        except Exception:
            self._gemini = None

    async def generate_and_save_trend_research(self, *, gender: Literal["male", "female"]) -> Dict[str, Any]:
        """Generate deep research for the given gender and save a row in trend_research.

        Returns a dict with the inserted row and metadata.
        """

        # Build minimal user_data-like context for research prompt with actual date
        today = date.today().isoformat()

        logger.info(f"[EXPLORE] generating deep trend research gender={gender} date={today}")

        # 1) Create a processing row first
        draft_payload = {
            "gender": gender,
            "research": "",
            "research_date": today,
            "status": "processing",
        }
        logger.info("[EXPLORE] inserting trend_research row (processing)")
        draft_res = self._supabase.table("trend_research").insert(draft_payload).execute()
        draft_row = draft_res.data[0] if draft_res and draft_res.data else None
        research_id = draft_row.get("id") if draft_row else None
        logger.info(f"[EXPLORE] inserted trend_research id={research_id}")

        # Measure end-to-end generation time
        started_at = time.perf_counter()
        try:
            # 2) Generate research
            research_obj = await self.openai_client.generate_deep_trend_research(
                gender=gender,
                date_iso=today,
            )

            # Persist as text; store JSON string if dict
            if isinstance(research_obj, dict):
                import json
                research_text = json.dumps(research_obj, separators=(",", ":"))
            else:
                research_text = str(research_obj)

            # 3) Update row to completed
            elapsed_s = int(round(time.perf_counter() - started_at))
            logger.info(f"[EXPLORE] updating trend_research id={research_id} to completed (in {elapsed_s}s)")
            upd_res = self._supabase.table("trend_research").update({
                "research": research_text,
                "status": "completed",
                "generation_time_seconds": elapsed_s,
            }).eq("id", research_id).execute()
            final_row = upd_res.data[0] if upd_res and upd_res.data else draft_row
            return {"row": final_row, "gender": gender, "date": today}

        except Exception as e:
            logger.warning(f"[EXPLORE] research generation failed: {e}")
            # 4) Update row to failed
            try:
                elapsed_s = int(round(time.perf_counter() - started_at))
                logger.info(f"[EXPLORE] updating trend_research id={research_id} to failed (after {elapsed_s}s)")
                upd_res = self._supabase.table("trend_research").update({
                    "status": "failed",
                    "generation_time_seconds": elapsed_s,
                }).eq("id", research_id).execute()
                failed_row = upd_res.data[0] if upd_res and upd_res.data else draft_row
            except Exception:
                failed_row = draft_row
            return {"row": failed_row, "gender": gender, "date": today}

    async def generate_explore_ideas(self, *, gender: Literal["male", "female"]) -> Dict[str, Any]:
        """Generate 4 new explore ideas (title + description) for the given gender.

        Uses trend outfits data for inspiration and considers previous ideas
        to encourage novelty.
        """
        logger.info(f"[EXPLORE] generating explore ideas gender={gender}")

        # 1) Fetch recent trend outfits with their items for inspiration
        trend_inspiration = ""

        try:
            logger.info(f"[EXPLORE] fetching trend outfits with items for inspiration")
            
            # First, get trend outfits with their basic info
            trend_outfits_res = (
                self._supabase.table("trend_outfits")
                .select("id, name")
                .order("created_at", desc=True)
                .eq("gender", gender)
                .limit(30)  # Get recent trend outfits for variety
                .execute()
            )
            
            if trend_outfits_res.data:
                outfit_ids = [outfit["id"] for outfit in trend_outfits_res.data]
                
                # Now fetch the trend outfit items for these outfits
                items_res = (
                    self._supabase.table("trend_outfit_items")
                    .select("outfit_id, type, keywords")
                    .in_("outfit_id", outfit_ids)
                    .execute()
                )
                
                # Group items by outfit_id
                outfit_items_map = {}
                for item in items_res.data or []:
                    outfit_id = item["outfit_id"]
                    if outfit_id not in outfit_items_map:
                        outfit_items_map[outfit_id] = []
                    outfit_items_map[outfit_id].append({
                        "type": item["type"],
                        "keywords": item["keywords"]
                    })
                
                # Build trend inspiration from outfits and their items
                trend_data = []
                for outfit in trend_outfits_res.data:
                    outfit_id = outfit["id"]
                    outfit_name = outfit["name"]
                    items = outfit_items_map.get(outfit_id, [])
                    
                    if items:
                        items_desc = []
                        for item in items:
                            item_type = item["type"]
                            keywords = item["keywords"]
                            items_desc.append(f"{item_type}: {keywords}")
                        
                        trend_data.append(f"Outfit: {outfit_name}\nItems: {'; '.join(items_desc)}\n\n")
                
                trend_inspiration = "\n".join(trend_data)
                logger.info(f"[EXPLORE] found {len(trend_outfits_res.data)} trend outfits with items for inspiration ({len(trend_inspiration)} chars)")
            else:
                logger.info(f"[EXPLORE] no trend outfits found for inspiration")
        except Exception as e:
            logger.warning(f"[EXPLORE] failed to fetch trend outfits: {e}")
            pass

        # 2) Fetch previous explore ideas for this gender (recent 30)
        prev_titles: list[str] = []

        try:
            logger.info(f"[EXPLORE] fetching previous ideas for {gender}")
            res_prev = (
                self._supabase.table("explore_ideas")
                # title and description
                .select("title,description")
                .eq("gender", gender)
                .order("created_at", desc=True)
                .limit(30)
                .execute()
            )
            prev_titles = [
                r.get("title", "") + ": " + r.get("description", "") 
                for r in (res_prev.data or []) 
                if r and r.get("title")
            ]
            logger.info(f"[EXPLORE] found {len(prev_titles)} previous titles")
        except Exception as e:
            logger.warning(f"[EXPLORE] failed to fetch previous titles: {e}")
            prev_titles = []

        # 3) Ask OpenAI to propose 4 new ideas
        logger.info(f"[EXPLORE] calling OpenAI to generate ideas")
        ideas = await self.openai_client.generate_explore_ideas(
            gender=gender,
            trend_inspiration=trend_inspiration,
            previous_titles=prev_titles,
        )

        if not ideas:
            logger.info("[EXPLORE] no ideas generated; returning empty result")
            return {"created": 0, "rows": []}
        
        logger.info(f"[EXPLORE] OpenAI returned {len(ideas)} ideas")

        # 4) Insert into explore_ideas with concept_outfits
        payloads = [
            {
                "title": i.get("title", ""),
                "description": i.get("description", ""),
                "gender": gender,
                "concept_outfits": i.get("concept_outfits", {}),
            }
            for i in ideas
        ]
        logger.info(f"[EXPLORE] inserting {len(payloads)} ideas into database")
        try:
            ins = self._supabase.table("explore_ideas").insert(payloads).execute()
            rows = ins.data or []
            logger.info(f"[EXPLORE] successfully inserted {len(rows)} explore ideas")

            # 5) Generate cover images (best‑effort); update image_url when available
            if self._gemini and rows:
                for row in rows:
                    try:
                        title = row.get("title") or ""
                        description = row.get("description") or ""
                        concept_outfits = row.get("concept_outfits") or {}
                        # Extract only the first outfit for cover image generation
                        first_outfit = {}
                        outfits = concept_outfits.get("outfits") if isinstance(concept_outfits, dict) else None
                        if outfits:
                            first_outfit = {"outfits": [outfits[0]]}
                        # Include outfit concept so the image reflects the styling
                        prompt = build_cover_prompt(title=title, description=description, gender=gender, concept_outfit=first_outfit)
                        
                        # Use the same pattern as flatlay generation
                        def _generate():
                            return self._gemini._generate_image([prompt])
                        
                        img_bytes = await asyncio.to_thread(_generate)
                        if not img_bytes:
                            logger.warning(f"[EXPLORE] no image bytes returned for {row['id']}")
                            continue

                        # Upload to bucket (following flatlay pattern)
                        import uuid
                        from utils.image_processing.image_gen import detect_image_mime_and_ext
                        
                        mime_type, ext = detect_image_mime_and_ext(img_bytes)
                        filename = f"explore_cover_{uuid.uuid4().hex}{ext}"
                        bucket = "explore-ideas-covers"
                        
                        # Retry logic like flatlay upload
                        max_retries = 3
                        url = None
                        for attempt in range(max_retries):
                            try:
                                self._supabase.storage.from_(bucket).upload(filename, img_bytes, {"content-type": mime_type})
                                url = self._supabase.storage.from_(bucket).get_public_url(filename)
                                break
                            except Exception as e:
                                if "Bucket not found" in str(e) and attempt == 0:
                                    # Try to create bucket once
                                    try:
                                        self._supabase.storage.create_bucket(bucket, public=True)
                                        logger.info(f"[EXPLORE] created bucket {bucket}")
                                    except Exception:
                                        pass
                                if attempt == max_retries - 1:
                                    logger.error(f"[EXPLORE] upload failed after {max_retries} attempts: {e}")
                                    break
                                else:
                                    logger.warning(f"[EXPLORE] upload attempt {attempt + 1} failed, retrying: {e}")
                                    await asyncio.sleep(1)
                        
                        if url:
                            # Update row with image_url
                            self._supabase.table("explore_ideas").update({"image_url": url}).eq("id", row["id"]).execute()
                            row["image_url"] = url
                            logger.info(f"[EXPLORE] cover image set for {row['id']}: {url}")
                        
                    except Exception as e:
                        logger.warning(f"[EXPLORE] cover generation failed for {row.get('id')}: {e}")

            return {"created": len(rows), "rows": rows}
        except Exception as e:
            logger.error(f"[EXPLORE] failed to insert explore ideas: {e}")
            return {"created": 0, "rows": []}


