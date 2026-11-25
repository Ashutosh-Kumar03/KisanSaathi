"""Configuration.

Every setting has a default that works for a local demo, so a missing .env
degrades the app instead of breaking it. Nothing here is required to start.
"""

import os


class Settings:
    """Environment-backed settings.

    Deliberately a plain class rather than a settings library: the whole
    surface is five variables, and a dependency we do not need is a wheel we
    cannot install.
    """

    # Supabase. When either is missing the app falls back to the in-memory
    # store, so the demo never depends on the database being configured.
    supabase_url: str | None = os.getenv("SUPABASE_URL") or None
    supabase_key: str | None = os.getenv("SUPABASE_KEY") or None

    # Optional narration polish. Absent is the normal, supported case.
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Where the Vite dev server runs. Comma-separated list for extras.
    cors_origins: list[str] = (
        os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        .split(",")
    )

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
