import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"


def resolve_data_path(base_dir: Path | None = None) -> Path:
    base_dir = Path(base_dir) if base_dir is not None else BASE_DIR
    project_root = base_dir if base_dir.name == "Incident-2" or (base_dir / ".git").exists() or (base_dir / "app").exists() else base_dir.parent

    env_path = os.getenv("INCIDENT_DATA_PATH")
    candidates = []

    if env_path:
        env_candidate = Path(env_path).expanduser()
        if not env_candidate.is_absolute():
            env_candidate = (project_root / env_candidate).resolve()
        candidates.append(env_candidate)

    processed_dir = base_dir / "processed" if (base_dir / "processed").exists() or base_dir.name == "data" else project_root / "data" / "processed"
    raw_dir = base_dir / "raw" if (base_dir / "raw").exists() or base_dir.name == "data" else project_root / "data" / "raw"

    processed_candidate = processed_dir / "cleaned_incidents.csv"
    raw_candidate = raw_dir / "incidents_raw.csv"
    legacy_candidate = project_root / "data" / "incidents.csv"

    candidates.extend([processed_candidate, raw_candidate, legacy_candidate])

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return processed_candidate.resolve()


# Dataset paths
DATA_PATH = resolve_data_path()

# Database
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "incidentiq.db")).resolve()

# LLM Providers and Keys
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", os.getenv("OPENROUTE_API_KEY", ""))
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash:free")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

# JWT & Security
JWT_SECRET = os.getenv("JWT_SECRET", "incidentiq-super-secret-key-2026-secure-token")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# Search & Retrieval
TOP_K_DEFAULT = int(os.getenv("TOP_K_DEFAULT", "5"))
ENABLE_GUARDRAILS = os.getenv("ENABLE_GUARDRAILS", "true").lower() in ("true", "1", "yes")
