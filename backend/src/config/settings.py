# src/config/settings.py
"""
Centralized settings using pydantic-settings.
All environment variables are validated and typed.
"""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration"""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    url: str = Field(default="localhost:5432", description="host:port format")
    db: str = Field(default="postgres")

    # Role-specific login users (created by migrate container)
    app_password: str = Field(default="", description="Password for app_user (POSTGRES_APP_PASSWORD)")
    mgr_password: str = Field(default="", description="Password for mgr_user (POSTGRES_MGR_PASSWORD)")

    @field_validator("url")
    @classmethod
    def validate_url_format(cls, v: str) -> str:
        try:
            host, port = v.split(":")
            int(port)
        except ValueError:
            raise ValueError(f"Invalid format: {v}. Expected 'host:port'") from None
        return v

    @model_validator(mode="after")
    def validate_role_passwords(self) -> "DatabaseSettings":
        missing = [
            name
            for name, val in [
                ("POSTGRES_APP_PASSWORD", self.app_password),
                ("POSTGRES_MGR_PASSWORD", self.mgr_password),
            ]
            if not val
        ]
        if missing:
            raise ValueError(f"❌ Missing required DB passwords: {', '.join(missing)}. Check .env file.")
        return self

    @property
    def app_async_url(self) -> str:
        """Build async SQLAlchemy URL for app_user (general API, CRUD on public, SELECT on auth)"""
        host, port = self.url.split(":")
        return f"postgresql+asyncpg://app_user:{self.app_password}@{host}:{port}/{self.db}"

    @property
    def login_async_url(self) -> str:
        """Build async SQLAlchemy URL for mgr_user (auth lookups + admin paths, BYPASSRLS)."""
        host, port = self.url.split(":")
        return f"postgresql+asyncpg://mgr_user:{self.mgr_password}@{host}:{port}/{self.db}"


class GoogleOAuthSettings(BaseSettings):
    """Google OAuth configuration"""

    model_config = SettingsConfigDict(env_prefix="GOOGLE_")

    client_id: str = Field(default="")
    client_secret: str = Field(default="")
    token_url: str = Field(default="https://oauth2.googleapis.com/token")
    userinfo_url: str = Field(default="https://www.googleapis.com/oauth2/v3/userinfo")
    jwks_url: str = Field(default="https://www.googleapis.com/oauth2/v3/certs")
    issuer: str = Field(default="https://accounts.google.com")


class AuthentikSettings(BaseSettings):
    """Authentik OAuth configuration"""

    model_config = SettingsConfigDict(env_prefix="AUTHENTIK_")

    url: str = Field(default="https://authentik.posetmage.com")
    client_id: str = Field(default="")
    application_slug: str = Field(default="lattice-cast")

    @property
    def token_url(self) -> str:
        return f"{self.url}/application/o/token/"

    @property
    def userinfo_url(self) -> str:
        return f"{self.url}/application/o/userinfo/"

    @property
    def jwks_url(self) -> str:
        return f"{self.url}/application/o/{self.application_slug}/jwks/"

    @property
    def issuer(self) -> str:
        return f"{self.url}/application/o/{self.application_slug}/"


class MinioSettings(BaseSettings):
    """MinIO S3-compatible storage configuration"""

    model_config = SettingsConfigDict(env_prefix="MINIO_")

    endpoint: str = Field(..., description="MinIO endpoint (host:port)")
    access_key: str = Field(..., description="Access key")
    secret_key: str = Field(..., description="Secret key")
    bucket: str = Field(..., description="Default bucket name")
    secure: bool = Field(default=False, description="Use HTTPS")


class AppSettings(BaseSettings):
    """Application-wide settings"""

    model_config = SettingsConfigDict(env_prefix="")

    debug_mode: bool = Field(default=False, alias="DEBUG_MODE")
    NGX_PORT: int = Field(default=8000, alias="NGX_PORT")

    # Self-issued JWT (password-login flow — see middleware/token.py)
    jwt_secret_key: str = Field(default="", alias="JWT_SECRET_KEY", description="Signs self-issued JWTs")
    jwt_expire_minutes: int = Field(default=1440, alias="JWT_EXPIRE_MINUTES")

    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    google: GoogleOAuthSettings = Field(default_factory=GoogleOAuthSettings)
    authentik: AuthentikSettings = Field(default_factory=AuthentikSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)

    @model_validator(mode="after")
    def validate_jwt_secret(self) -> "AppSettings":
        if not self.jwt_secret_key:
            raise ValueError("❌ Missing required JWT_SECRET_KEY. Check .env file.")
        if len(self.jwt_secret_key) <= 10:
            raise ValueError("❌ JWT_SECRET_KEY too short (must be > 10 chars). Check .env file.")
        return self

    # CORS origins
    @property
    def cors_origins(self) -> list[str]:
        if self.debug_mode:
            return ["*"]
        return [
            "https://lattice-cast.posetmage.com",
        ]


@lru_cache
def get_settings() -> AppSettings:
    """Cached settings singleton"""
    return AppSettings()


# Convenience alias
settings = get_settings()
