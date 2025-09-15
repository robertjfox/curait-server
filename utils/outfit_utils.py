from typing import List, Dict, Any


def format_outfit_history(outfit_history: List[Dict[str, Any]]) -> str:
    lines: List[str] = []

    if not outfit_history:
        return ""

    for outfit in outfit_history[-5:]:
        title = str(outfit.get("title", "")).strip()
        description = str(outfit.get("description", "")).strip()
        items = outfit.get("items") or []
        overall_feedback = str(outfit.get("feedback", "")).strip()

        title_suffix = f" ({overall_feedback.upper()})" if overall_feedback else ""
        if title:
            lines.append(f"{title}{title_suffix}")
        # if description:
        #     lines.append(f"- {description}")

        for item in items:
            raw_keywords = item.get("keywords", [])
            if isinstance(raw_keywords, str):
                keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
            elif isinstance(raw_keywords, (list, tuple, set)):
                keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
            else:
                keywords = []

            item_feedback = item.get("feedback")
            if isinstance(item_feedback, str):
                item_feedback = item_feedback.strip()
            else:
                item_feedback = ""
            item_suffix = f" ({item_feedback.upper()})" if item_feedback else ""

            for keyword in keywords:
                lines.append(f"- {keyword}{item_suffix}")

        if title or description or items or overall_feedback:
            lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)

