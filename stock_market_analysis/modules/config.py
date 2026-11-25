"""Configuration: reads settings from environment variables, a .env file or Streamlit secrets.

API keys are NEVER written in the source code. Copy .env.example to .env and fill it in,
or create .streamlit/secrets.toml (see README).
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _setting(name, default=None):
    """Look in environment variables first, then Streamlit secrets."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:  # no secrets file, or Streamlit not running (e.g. in a notebook)
        return default


@dataclass(frozen=True)
class Settings:
    provider: str
    alpha_vantage_key: str | None
    refresh_seconds: int
    quote_ttl: int
    history_ttl: int
    db_path: str


def _int(value, default, minimum):
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def get_settings() -> Settings:
    return Settings(
        provider=str(_setting("DATA_PROVIDER", "yahoo")).strip().lower(),
        alpha_vantage_key=_setting("ALPHA_VANTAGE_API_KEY"),
        refresh_seconds=_int(_setting("REFRESH_SECONDS", 60), 60, 15),
        quote_ttl=_int(_setting("QUOTE_CACHE_SECONDS", 60), 60, 5),
        history_ttl=_int(_setting("HISTORY_CACHE_SECONDS", 900), 900, 60),
        db_path=str(_setting("DATABASE_PATH", BASE_DIR / "data" / "portfolio.db")),
    )
