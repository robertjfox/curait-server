from typing import List, Dict, Any


def format_outfit_history(outfit_history: List[Dict[str, Any]]) -> str:
    lines: List[str] = []

    if not outfit_history:
        return ""

    for outfit in outfit_history[-4:]:
        title = str(outfit.get("title", "")).strip()
        description = str(outfit.get("description", "")).strip()
        raw_keywords = outfit.get("keywords", [])

        if isinstance(raw_keywords, str):
            keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        elif isinstance(raw_keywords, (list, tuple, set)):
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        else:
            keywords = []

        if title:
            lines.append(title)
        # if description:
        #     lines.append(f"- {description}")
        for keyword in keywords:
            lines.append(f"- {keyword}")

        if title or description or keywords:
            lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)

