#!/usr/bin/env python3
"""Export OpenAPI schema to public/openapi.json."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import create_app

OUT = Path(__file__).resolve().parents[1] / "public" / "openapi.json"


def main() -> None:
    schema = create_app().openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
