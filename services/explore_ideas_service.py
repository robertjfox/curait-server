import logging
from typing import Dict, Any, List

from clients.openai_client import get_openai_client
from clients.supabase_client import get_supabase_client
from clients.gemini_client import get_gemini_client
from ai.prompts.trend_outfit_rendering import build_trend_outfit_rendering_prompt

logger = logging.getLogger(__name__)

class ExploreIdeasService:
    def __init__(self) -> None:
        self.openai_client = get_openai_client()
        self._supabase = get_supabase_client()
        try:
            self._gemini = get_gemini_client()
        except Exception:
            self._gemini = None

    async def generate_explore_ideas(self, *, trend_outfit_id: str) -> Dict[str, Any]:
        # fetch the trend outfit by ID
        outfit = self._fetch_trend_outfit_by_id(trend_outfit_id)
        if not outfit:
            logger.warning(f"[EXPLORE] trend outfit {trend_outfit_id} not found")
            return {"created": 0, "rows": []}

        # extract the items from the trend outfit
        base_items = self._extract_outfit_items(outfit)
        if not base_items:
            logger.warning(f"[EXPLORE] no items found for trend outfit {trend_outfit_id}")
            return {"created": 0, "rows": []}

        gender = outfit.get("gender", "female")

        # generate the explore idea (title + description)
        idea = await self.openai_client.generate_explore_ideas(
            gender=gender,
            outfit_items=base_items,
            source_img_url=outfit.get("source_img_url")
        )

        if not idea:
            logger.warning(f"[EXPLORE] failed to generate idea for trend outfit {trend_outfit_id}")
            return {"created": 0, "rows": []}

        # create the payload for the explore idea
        payload = {
            "title": idea.get("title") or "New Explore Idea",
            "description": idea.get("description") or "A fresh take on current trends",
            "gender": gender,
        }

        # insert the explore idea
        insert_res = self._supabase.table("explore_ideas").insert(payload).execute()
        rows = insert_res.data or []

        if not rows:
            logger.warning("[EXPLORE] failed to insert explore idea")
            return {"created": 0, "rows": []}

        idea_row = rows[0]

        # update the source trend outfit with the explore idea ID
        try:
            self._supabase.table("trend_outfits").update({"explore_idea_id": idea_row["id"]}).eq("id", trend_outfit_id).execute()
            logger.info(f"[EXPLORE] linked trend outfit {trend_outfit_id} to explore idea {idea_row['id']}")
        except Exception as e:
            logger.warning(f"[EXPLORE] failed to update trend outfit {trend_outfit_id} with explore idea ID: {e}")


        return {"created": 1, "rows": [idea_row]}

    async def generate_trend_outfit_variations(self, *, trend_outfit_id: str, num_to_generate: int = 1) -> Dict[str, Any]:
        """Create additional trend outfit variations linked to an explore idea."""
        logger.info(f"[EXPLORE] Starting variation generation for trend outfit {trend_outfit_id} with {num_to_generate} variations")

        outfit = self._fetch_trend_outfit_by_id(trend_outfit_id, include_explore=True)
        if not outfit:
            logger.warning(f"[EXPLORE] trend outfit {trend_outfit_id} not found for variations")
            return {"created": 0, "rows": []}

        explore_idea_id = outfit.get("explore_idea_id")
        if not explore_idea_id:
            logger.warning(f"[EXPLORE] trend outfit {trend_outfit_id} missing explore idea link")
            return {"created": 0, "rows": []}

        explore = self._fetch_explore_idea_by_id(explore_idea_id)
        if not explore:
            logger.warning(f"[EXPLORE] explore idea {explore_idea_id} not found for trend variations")
            return {"created": 0, "rows": []}

        base_items = self._extract_outfit_items(outfit)
        if not base_items:
            logger.warning(f"[EXPLORE] no items found on trend outfit {trend_outfit_id} for variations")
            return {"created": 0, "rows": []}

        logger.info(f"[EXPLORE] generating {num_to_generate} variations for trend outfit {trend_outfit_id}")

        # Fetch the original outfit (with source_id) and previous variations
        original_outfit = self._fetch_original_outfit_for_explore_idea(explore_idea_id)
        previous_variations = self._fetch_previous_variations_for_explore_idea(explore_idea_id, exclude_outfit_id=trend_outfit_id)

        outfits_payload = await self.openai_client.generate_trend_outfit_variations(
            gender=outfit.get("gender", "female"),
            explore_title=explore.get("title") or "Untitled Explore Idea",
            explore_description=explore.get("description") or "",
            base_outfit_items=base_items,
            desired_count=num_to_generate,
            previous_outfit_variations=previous_variations,
        )

        if not outfits_payload:
            logger.warning(f"[EXPLORE] variation response empty for trend outfit {trend_outfit_id}")
            return {"created": 0, "rows": []}

        created_rows: List[Dict[str, Any]] = []
        for outfit_obj in outfits_payload:
            try:
                new_outfit = (
                    self._supabase
                    .table("trend_outfits")
                    .insert({
                        "gender": outfit.get("gender"),
                        "explore_idea_id": explore_idea_id,
                    })
                    .execute()
                )
                new_outfit_row = (new_outfit.data or [None])[0]
                if not new_outfit_row:
                    continue

                trend_outfit_id_new = new_outfit_row["id"]
                created_rows.append(new_outfit_row)

                rendering_url: str | None = None
                if self._gemini:
                    try:
                        rendering_url = await self._generate_trend_outfit_rendering(
                            title=explore.get("title", ""),
                            description=explore.get("description", ""),
                            gender=outfit.get("gender", "female"),
                            trend_outfit_items=outfit_obj.get("items", []),
                        )
                    except Exception as render_err:
                        logger.warning(f"[EXPLORE] failed to create rendering for variation {trend_outfit_id_new}: {render_err}")

                for item in outfit_obj.get("items", []):
                    try:
                        self._supabase.table("trend_outfit_items").insert({
                            "outfit_id": trend_outfit_id_new,
                            "type": item.get("type"),
                            "keywords": item.get("keywords"),
                            "search_results": [],
                        }).execute()
                    except Exception as item_err:
                        logger.warning(f"[EXPLORE] failed to insert variation item: {item_err}")

                if rendering_url:
                    try:
                        self._supabase.table("trend_outfits").update({"rendering_url": rendering_url}).eq("id", trend_outfit_id_new).execute()
                        new_outfit_row["rendering_url"] = rendering_url
                        logger.info(f"[EXPLORE] saved rendering for variation {trend_outfit_id_new}")
                    except Exception as update_err:
                        logger.warning(f"[EXPLORE] failed to save rendering URL for {trend_outfit_id_new}: {update_err}")

            except Exception as insert_err:
                logger.error(f"[EXPLORE] failed to insert trend outfit variation: {insert_err}")

        logger.info(f"[EXPLORE] variation generation complete: {len(created_rows)} new outfits created")
        return {"created": len(created_rows), "rows": created_rows}

    def _fetch_trend_outfit_by_id(self, trend_outfit_id: str, include_explore: bool = False) -> Dict[str, Any] | None:
        try:
            res = (
                self._supabase.table("trend_outfits")
                .select(
                    "id,gender,source_img_url,explore_idea_id,"
                    "trend_outfit_items(type,keywords)"
                )
                .eq("id", trend_outfit_id)
                .execute()
            )
            row = (res.data or [None])[0]
            if row and not include_explore:
                row.pop("explore_idea_id", None)
            return row
        except Exception as e:
            logger.warning(f"[EXPLORE] failed to fetch trend outfit {trend_outfit_id}: {e}")
            return None

    def _fetch_explore_idea_by_id(self, explore_idea_id: str) -> Dict[str, Any] | None:
        try:
            res = (
                self._supabase
                .table("explore_ideas")
                .select("id,title,description,gender")
                .eq("id", explore_idea_id)
                .execute()
            )
            return (res.data or [None])[0]
        except Exception as e:
            logger.warning(f"[EXPLORE] failed to fetch explore idea {explore_idea_id}: {e}")
            return None

    def _extract_outfit_items(self, outfit: Dict[str, Any]) -> List[Dict[str, str]]:
        items_raw = outfit.get("trend_outfit_items") or outfit.get("items") or []
        cleaned: List[Dict[str, str]] = []
        for item in items_raw:
            item_type = (item or {}).get("type")
            keywords = (item or {}).get("keywords")
            if not item_type or not keywords:
                continue
            cleaned.append({"type": str(item_type), "keywords": str(keywords)})

        # log the actual item content
        items_str = "; ".join([f"{item['type']}: {item['keywords']}" for item in cleaned])
        logger.info(f"[EXPLORE] extracted {len(cleaned)} outfit items: {items_str}")

        return cleaned

    def _fetch_original_outfit_for_explore_idea(self, explore_idea_id: str) -> Dict[str, Any] | None:
        """Fetch the original outfit (with source_id) for the given explore idea."""
        try:
            res = (
                self._supabase
                .table("trend_outfits")
                .select("id,gender,source_id,trend_outfit_items(type,keywords)")
                .eq("explore_idea_id", explore_idea_id)
                .not_.is_("source_id", None)
                .limit(1)
                .execute()
            )
            return (res.data or [None])[0]
        except Exception as e:
            logger.warning(f"[EXPLORE] failed to fetch original outfit for explore idea {explore_idea_id}: {e}")
            return None

    def _fetch_previous_variations_for_explore_idea(self, explore_idea_id: str, exclude_outfit_id: str) -> List[Dict[str, Any]]:
        """Fetch previous outfit variations (without source_id) for the given explore idea, excluding the specified outfit."""
        try:
            res = (
                self._supabase
                .table("trend_outfits")
                .select("id,gender,trend_outfit_items(type,keywords)")
                .eq("explore_idea_id", explore_idea_id)
                .is_("source_id", None)
                .neq("id", exclude_outfit_id)
                .limit(10)  # Limit to avoid overly long prompts
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.warning(f"[EXPLORE] failed to fetch previous variations for explore idea {explore_idea_id}: {e}")
            return []

    def _insert_trend_outfit(
        self,
        *,
        source_img_url: str,
        gender: str,
        explore_idea_id: str | None,
        source_id: str | None,
        rendering_url: str | None,
    ) -> Dict[str, Any] | None:
        payload: Dict[str, Any] = {
            "source_img_url": source_img_url,
            "gender": gender,
            "not_valid_outfit": False,  # Default to False, will be updated after analysis
        }
        if explore_idea_id:
            payload["explore_idea_id"] = explore_idea_id
        if source_id:
            payload["source_id"] = source_id
        if rendering_url:
            payload["rendering_url"] = rendering_url

        res = self._supabase.table("trend_outfits").insert(payload).execute()
        rows = res.data or []
        return rows[0] if rows else None

    def _insert_trend_outfit_items(self, *, outfit_id: str, items: List[Dict[str, str]]) -> None:
        for item in items:
            try:
                self._supabase.table("trend_outfit_items").insert({
                    "outfit_id": outfit_id,
                    "type": item.get("type"),
                    "keywords": item.get("keywords"),
                    "search_results": [],
                }).execute()
            except Exception as e:
                logger.warning(f"[EXPLORE] failed to insert trend outfit item: {e}")

    async def _generate_trend_outfit_rendering(self, *, title: str, description: str, gender: str, trend_outfit_items: List[Dict[str, str]]) -> str | None:
        """Generate a rendering image using Gemini based on the trend outfit items."""
        try:
            import asyncio
            import uuid
            from utils.image_processing.image_gen import detect_image_mime_and_ext
            
            # Build the rendering prompt using trend outfit items
            prompt = build_trend_outfit_rendering_prompt(
                title=title,
                description=description,
                gender=gender,
                outfit_items=trend_outfit_items
            )
            
            # Generate image with Gemini
            def _generate():
                return self._gemini._generate_image([prompt])
            
            img_bytes = await asyncio.to_thread(_generate)
            if not img_bytes:
                logger.warning("[EXPLORE] no image bytes returned from Gemini")
                return None

            # Upload to bucket
            mime_type, ext = detect_image_mime_and_ext(img_bytes)
            filename = f"trend_outfit_rendering_{uuid.uuid4().hex}{ext}"
            bucket = "trend-outfit-renderings"
            
            # Retry logic for upload
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self._supabase.storage.from_(bucket).upload(filename, img_bytes, {"content-type": mime_type})
                    url = self._supabase.storage.from_(bucket).get_public_url(filename)
                    logger.info(f"[EXPLORE] trend outfit rendering uploaded: {url}")
                    return url
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
                        return None
                    else:
                        logger.warning(f"[EXPLORE] upload attempt {attempt + 1} failed, retrying: {e}")
                        await asyncio.sleep(1)
            
            return None
        except Exception as e:
            logger.warning(f"[EXPLORE] trend outfit rendering generation failed: {e}")
            return None

    async def analyze_trend_outfit(self, *, image_url: str, source_id: str) -> Dict[str, Any]:
        logger.info("[EXPLORE] analyzing trend outfit image")

        if not image_url:
            raise ValueError("image_url is required")

        # Create the record immediately with source_id and source_img_url to prevent duplication
        outfit_row = self._insert_trend_outfit(
            source_img_url=image_url,
            gender="female",  # Default, will be updated after analysis
            explore_idea_id=None,
            source_id=source_id,
            rendering_url=None,
        )

        if not outfit_row:
            raise RuntimeError("Failed to create trend outfit record")

        try:
            outfit_payload = await self.openai_client.analyze_trend_outfit_image(
                image_url=image_url,
            )

            # Check if the analysis indicates this is not a valid outfit
            if outfit_payload and outfit_payload.get("not_valid_outfit"):
                logger.info("[EXPLORE] Image analysis determined this is not a valid outfit")
                self._supabase.table("trend_outfits").update({
                    "not_valid_outfit": True
                }).eq("id", outfit_row["id"]).execute()

                outfit_row["not_valid_outfit"] = True
                outfit_row["items"] = []
                return outfit_row

            if not outfit_payload:
                raise RuntimeError("Failed to analyze trend outfit image")

            items = outfit_payload.get("items") or []
            cleaned_items = []
            for item in items:
                item_type = (item or {}).get("type")
                keywords = (item or {}).get("keywords")
                if item_type and keywords:
                    cleaned_items.append({
                        "type": str(item_type),
                        "keywords": str(keywords),
                    })

            if not cleaned_items:
                raise RuntimeError("Trend outfit analysis returned no items")

            # Extract gender from the first item's keywords
            gender_to_store = "female"  # default
            if cleaned_items:
                first_keywords = cleaned_items[0].get("keywords", "").lower()
                if first_keywords.startswith(("mens", "men's")):
                    gender_to_store = "male"
                elif first_keywords.startswith(("womens", "women's")):
                    gender_to_store = "female"

            outfit_name = outfit_payload.get("name") or "Trend Outfit"

            rendering_url: str | None = None
            if self._gemini:
                try:
                    rendering_url = await self._generate_trend_outfit_rendering(
                        title=outfit_name,
                        description="",
                        gender=gender_to_store,
                        trend_outfit_items=cleaned_items,
                    )
                except Exception as render_err:
                    logger.warning(f"[EXPLORE] rendering generation failed: {render_err}")

            # Update the record with analysis results
            update_payload = {
                "gender": gender_to_store,
                "not_valid_outfit": False,
            }
            if rendering_url:
                update_payload["rendering_url"] = rendering_url

            self._supabase.table("trend_outfits").update(update_payload).eq("id", outfit_row["id"]).execute()

            self._insert_trend_outfit_items(outfit_id=outfit_row["id"], items=cleaned_items)

            outfit_row.update(update_payload)
            outfit_row["items"] = cleaned_items

        except Exception as e:
            logger.warning(f"[EXPLORE] Analysis failed, marking as invalid outfit: {e}")
            # Mark as invalid outfit if analysis fails
            self._supabase.table("trend_outfits").update({
                "not_valid_outfit": True
            }).eq("id", outfit_row["id"]).execute()

            outfit_row["not_valid_outfit"] = True
            outfit_row["items"] = []

        return outfit_row


