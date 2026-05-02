import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
load_dotenv(PROJECT_ROOT / ".env")


def get_config_value(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return value if value else default


# Supabase client initialization
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vnrxrwgnxqgaxmnwjxpl.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

