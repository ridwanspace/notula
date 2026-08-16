"""Runtime configuration from the environment (`.env` supported).

The default provider is "mock": a fresh clone runs the whole pipeline offline
with zero API keys. Live mode validates its credentials at startup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_prefix="NOTULA_", extra="ignore"
    )

    provider: Literal["mock", "live"] = "mock"
    gemini_api_key: str = Field(
        default="", validation_alias=AliasChoices("GEMINI_API_KEY", "NOTULA_GEMINI_API_KEY")
    )
    deepseek_api_key: str = Field(
        default="", validation_alias=AliasChoices("DEEPSEEK_API_KEY", "NOTULA_DEEPSEEK_API_KEY")
    )
    gemini_model: str = "gemini-3.5-flash"
    summarizer_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    data_dir: Path = Path("var")
    max_upload_bytes: int = 200 * 1024 * 1024
    max_chunk_seconds: float = 1200.0
    overlap_seconds: float = 15.0
    max_repair_attempts: int = 2

    @property
    def db_path(self) -> Path:
        return self.data_dir / "notula.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def workdir(self) -> Path:
        return self.data_dir / "work"

    def validate_live(self) -> None:
        """Fail fast at startup when live mode is missing credentials."""
        if self.provider != "live":
            return
        missing = [
            name
            for name, value in (
                ("GEMINI_API_KEY", self.gemini_api_key),
                ("DEEPSEEK_API_KEY", self.deepseek_api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError("provider=live requires API keys; missing: " + ", ".join(missing))
