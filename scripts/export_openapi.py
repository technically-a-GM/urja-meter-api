"""Regenerate openapi.json from the FastAPI routes."""

import json
from pathlib import Path

from app.main import app

Path("openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print("Exported openapi.json")
