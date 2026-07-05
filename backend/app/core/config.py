from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    gemini_api_key: str
    # --- Modal LLM inference endpoint (custom HTTP endpoint from modal_app.py) ---
    modal_url: str = ""
    modal_api_key: str = ""  # Bearer token for the custom Modal LLM HTTP endpoint
    # --- Modal SDK auth (for Sandbox creation) ---
    # These are also read automatically as MODAL_TOKEN_ID / MODAL_TOKEN_SECRET env vars
    modal_token_id: str = ""
    modal_token_secret: str = ""
    google_application_credentials: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
