"""
app/core/config.py — Application settings via pydantic-settings.

All values come from environment variables (or a .env file at dev time).
No secrets are hard-coded here — only defaults that are safe to expose.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # ── Database (PostgreSQL) ─────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://unigraph:changeme_in_prod@postgres:5432/unigraph"
    )

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme_in_prod"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_OR_YOU_WILL_GET_HACKED"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # ── Dev user (Phase 0/1 only — replaced with DB users in Phase 2) ─────────
    dev_user_email: str = "investigator@i4c.gov.in"
    dev_user_password: str = "devpass"
    dev_user_role: str = "investigator"

    # ── VASP API keys ─────────────────────────────────────────────────────────
    # Comma-separated in the env var; parsed into a list here.
    vasp_api_keys: str = "dev_vasp_key_1_CHANGEME"

    @property
    def vasp_api_keys_set(self) -> set:
        """Return the set of valid VASP API keys for O(1) lookup."""
        return {k.strip() for k in self.vasp_api_keys.split(",") if k.strip()}

    # ── Celery ────────────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ── Blockchain explorers (Phase 3) ────────────────────────────────────────
    etherscan_api_key: str = ""
    blockstream_base_url: str = "https://blockstream.info/api"
    trongrid_api_key: str = ""
    tronscan_api_key: str = ""

    # ── Ollama (Phase 6) ──────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"

    def validate_production_safety(self) -> list[str]:
        """Return a list of warnings if prod-unsafe defaults are still present."""
        warnings: list[str] = []
        if self.app_env == "production":
            if self.jwt_secret_key.startswith("CHANGE_ME"):
                warnings.append(
                    "JWT_SECRET_KEY is using the default insecure value — rotate it NOW.",
                )
            if "changeme" in self.database_url.lower():
                warnings.append("DATABASE_URL contains the default 'changeme_in_prod' credential.")
            if "changeme" in self.neo4j_password.lower():
                warnings.append("NEO4J_PASSWORD is still the default insecure value.")
            if self.dev_user_password == "devpass":
                warnings.append(
                    "DEV_USER_PASSWORD is 'devpass' — disable the dev user in production.",
                )
            if "CHANGEME" in self.vasp_api_keys:
                warnings.append("VASP_API_KEYS contains the default placeholder.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — import and call this everywhere instead of Settings()."""
    return Settings()
