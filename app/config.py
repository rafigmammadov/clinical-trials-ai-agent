"""Environment-backed application configuration; no secrets are logged."""

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from urllib.parse import urlsplit
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
    base_url = os.getenv(
        "CLINICALTRIALS_API_URL", "https://clinicaltrials.gov/api/v2"
    ).rstrip("/")
    try:
        endpoint = urlsplit(base_url)
        valid_endpoint = (
            bool(endpoint.hostname)
            and (endpoint.scheme == "https" or
                 endpoint.scheme == "http" and endpoint.hostname in {"localhost", "127.0.0.1", "::1"})
            and not endpoint.username and not endpoint.password
            and not endpoint.query and not endpoint.fragment
            and not any(char.isspace() for char in base_url)
        )
    except ValueError:
        valid_endpoint = False
    if not valid_endpoint:
        raise ValueError("CLINICALTRIALS_API_URL must be HTTPS (or HTTP loopback for local testing) without credentials or query strings")

    try:
        timeout = float(os.getenv("CLINICALTRIALS_TIMEOUT_SECONDS", "20"))
    except ValueError as exc:
        raise ValueError("CLINICALTRIALS_TIMEOUT_SECONDS must be numeric") from exc
    if not isfinite(timeout) or not 0.1 <= timeout <= 120:
        raise ValueError("CLINICALTRIALS_TIMEOUT_SECONDS must be between 0.1 and 120")

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        planner_mode=mode,
        clinicaltrials_api_url=base_url,
        clinicaltrials_timeout_seconds=timeout,
    )
