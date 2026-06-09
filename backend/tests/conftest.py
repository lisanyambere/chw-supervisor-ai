"""Pytest config — make `backend/` importable as `app.*` and load .env."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(REPO_ROOT / ".env", override=False)

# The app warms the activity cache at startup by hitting OpenMRS; tests run the
# lifespan via TestClient, so disable the warm to keep the suite hermetic.
os.environ.setdefault("ACTIVITY_WARM_ON_STARTUP", "0")
