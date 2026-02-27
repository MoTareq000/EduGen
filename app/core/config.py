import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def get_config_value(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return value if value else default

