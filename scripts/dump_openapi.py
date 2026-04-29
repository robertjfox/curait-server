"""Dump the FastAPI OpenAPI schema to `openapi.json` in the repo root.

The sibling `curait-web-app` repo consumes this file via `openapi-typescript`
to generate strongly-typed HTTP request/response bindings (no manual drift).

Run from the `curait-server` directory:

    python -m scripts.dump_openapi

No live API keys are required — any missing env vars are stubbed with
placeholders so the app module imports cleanly for schema extraction.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


_PLACEHOLDER_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "SERPER_API_KEY",
    "SERPAPI_API_KEY",
)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    os.chdir(repo_root)

    for name in _PLACEHOLDER_ENV_VARS:
        os.environ.setdefault(name, "__placeholder_for_openapi_dump__")
    if not os.environ.get("SUPABASE_URL", "").startswith("http"):
        os.environ["SUPABASE_URL"] = "http://localhost:54321"

    from main import app  # noqa: E402  (path injected above)

    schema = app.openapi()
    output_path = repo_root / "openapi.json"
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(schema, fp, indent=2, sort_keys=True)
        fp.write("\n")

    print(f"Wrote OpenAPI schema → {output_path}")


if __name__ == "__main__":
    main()
