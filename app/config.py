"""Environment-backed application configuration; no secrets are logged."""

from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    openai_api_key: str
    openai_model: str
    planner_mode: str
    clinicaltrials_api_url: str
    clinicaltrials_timeout_seconds: float


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    mode = os.getenv("PLANNER_MODE", "openai").strip().lower()
    if mode not in {"openai", "rules"}:
        raise ValueError("PLANNER_MODE must be 'openai' or 'rules'")
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        planner_mode=mode,
        clinicaltrials_api_url=os.getenv(
            "CLINICALTRIALS_API_URL", "https://clinicaltrials.gov/api/v2"
        ).rstrip("/"),
        clinicaltrials_timeout_seconds=float(
            os.getenv("CLINICALTRIALS_TIMEOUT_SECONDS", "20")
        ),
    )
