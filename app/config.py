import os
from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"  # "development", "staging", "production"
    DATABASE_URL: str = "sqlite:///./dsa_tracker.db"
    SQLITE_FALLBACK: bool = False
    JWT_SECRET: str = "dsa_tracker_super_secret_jwt_key_2026_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CLIENT_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000"
    ALLOW_DEV_FALLBACK_AUTH: bool = False
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "dsa_tracker"

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

    @model_validator(mode="after")
    def validate_security_and_environment(self):
        insecure_keys = {
            "dsa_tracker_super_secret_jwt_key_2026_change_in_production",
            "supersecretjwtkey",
            "secret",
            "changeme",
            "your_jwt_secret_key_here",
        }
        # Outside development, strictly mandate strong non-default secret
        if self.ENVIRONMENT.lower() in ("production", "prod", "staging"):
            if not self.JWT_SECRET or self.JWT_SECRET in insecure_keys or len(self.JWT_SECRET) < 32:
                raise ValueError(
                    "FATAL SECURITY CONFIGURATION: Outside development, JWT_SECRET must be set to a strong, unpredictable secret (min 32 chars). "
                    "Startup aborted to prevent token forgery."
                )
        return self

settings = Settings()
