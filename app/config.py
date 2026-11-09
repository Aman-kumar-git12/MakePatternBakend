import os
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings

INSECURE_JWT_SECRETS = {
    "dsa_tracker_super_secret_jwt_key_2026_change_in_production",
    "supersecretjwtkey",
    "secret",
    "changeme",
    "your_jwt_secret_key_here",
}

DEV_JWT_SECRET = "dev-only-insecure-secret-do-not-use-in-production"


def _detect_environment() -> str:
    # Hosted platforms are always production unless explicitly overridden.
    if os.getenv("ENVIRONMENT"):
        return os.environ["ENVIRONMENT"]
    if os.getenv("RENDER") or os.getenv("VERCEL") or os.getenv("FLY_APP_NAME") or os.getenv("RAILWAY_ENVIRONMENT"):
        return "production"
    return "development"


class Settings(BaseSettings):
    ENVIRONMENT: str = _detect_environment()
    JWT_SECRET: str = DEV_JWT_SECRET
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days, matches the frontend session cookie
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CLIENT_URL: str = "https://make-pattern-dev.vercel.app"
    CORS_ORIGINS: str = ""
    # Regex for preview deployments of *this* project only (not every *.vercel.app site).
    CORS_ORIGIN_REGEX: str = r"^https://make-pattern[a-z0-9\-]*\.vercel\.app$"

    # MongoDB is the single source of truth. No credentials live in code.
    MONGODB_URI: Optional[str] = None
    MONGODB_URL: Optional[str] = None
    MONGODB_DB_NAME: str = "dsa_tracker"

    LEETCODE_GRAPHQL_URL: str = "https://leetcode.com/graphql"

    # Optional Judge0 code execution (C++/Java). Python/JS run in the browser without it.
    # RapidAPI: JUDGE0_URL=https://judge0-ce.p.rapidapi.com, JUDGE0_API_HOST=judge0-ce.p.rapidapi.com
    # Self-hosted: JUDGE0_URL=https://judge0.example.com, JUDGE0_API_KEY sent as X-Auth-Token
    JUDGE0_URL: Optional[str] = None
    JUDGE0_API_KEY: Optional[str] = None
    JUDGE0_API_HOST: Optional[str] = None

    @property
    def judge0_enabled(self) -> bool:
        return bool(self.JUDGE0_URL)

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod", "staging")

    @property
    def mongo_connection_uri(self) -> Optional[str]:
        return self.MONGODB_URI or self.MONGODB_URL

    @model_validator(mode="after")
    def validate_security(self):
        if self.is_production:
            if self.JWT_SECRET in INSECURE_JWT_SECRETS or self.JWT_SECRET == DEV_JWT_SECRET or len(self.JWT_SECRET) < 32:
                raise ValueError(
                    "JWT_SECRET must be set to a strong random value (>= 32 chars) in production. "
                    "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
                )
            if not self.mongo_connection_uri:
                raise ValueError("MONGODB_URI must be set in production.")
        return self


settings = Settings()
