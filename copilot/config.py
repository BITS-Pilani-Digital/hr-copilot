"""Central configuration. Everything is overridable with environment variables (or a .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
POLICY_DIR = Path(os.getenv("POLICY_DIR", DATA_DIR / "policies"))
INDEX_DIR = Path(os.getenv("INDEX_DIR", DATA_DIR / "index"))
HR_RECORDS_PATH = Path(os.getenv("HR_RECORDS_PATH", DATA_DIR / "hr_records.json"))
REQUESTS_PATH = Path(os.getenv("REQUESTS_PATH", DATA_DIR / "requests.json"))

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "900"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
TOP_K = int(os.getenv("TOP_K", "4"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.25"))

COMPANY_NAME = os.getenv("COMPANY_NAME", "Nimbus Labs")
