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
    user: str = Field(default="postgres")
    password: str = Field(default="")
    db: str = Field(default="postgres")

    # Role-specific login users (created by postgres/init-roles.sh)
    dba_password: str = Field(default="", description="Password for dba_user (POSTGRES_DBA_PASSWORD)")
    app_password: str = Field(default="", description="Password for app_user (POSTGRES_APP_PASSWORD)")
    login_password: str = Field(default="", description="Password for login_user (POSTGRES_LOGIN_PASSWORD)")

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
            name for name, val in [
                ("POSTGRES_DBA_PASSWORD", self.dba_password),
                ("POSTGRES_APP_PASSWORD", self.app_password),
                ("POSTGRES_LOGIN_PASSWORD", self.login_password),
            ]
            if not val
        ]
        if missing:
            raise ValueError(
                f"❌ Missing required DB role passwords: {', '.join(missing)}. "
                "Run: docker compose up -d --force-recreate backend"
            )
        return self

    @property
    def dba_async_url(self) -> str:
        """Build async SQLAlchemy URL for dba_user (migrations, full access)"""
        host, port = self.url.split(":")
        return f"postgresql+asyncpg://dba_user:{self.dba_password}@{host}:{port}/{self.db}"

    @property
    def app_async_url(self) -> str:
        """Build async SQLAlchemy URL for app_user (general API, CRUD on public, SELECT on auth)"""
        host, port = self.url.split(":")
        return f"postgresql+asyncpg://app_user:{self.app_password}@{host}:{port}/{self.db}"

    @property
    def login_async_url(self) -> str:
        """Build async SQLAlchemy URL for login_user (auth endpoints, CRUD on auth schema)"""
        host, port = self.url.split(":")
        return f"postgresql+asyncpg://login_user:{self.login_password}@{host}:{port}/{self.db}"


class RedisSettings(BaseSettings):
    """Valkey cache configuration (redis-py compatible)"""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = Field(default="redis://localhost:6379/0")
    socket_timeout: int = Field(default=5)
    socket_connect_timeout: int = Field(default=5)


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
    auth_required: bool = Field(default=True, alias="AUTH_REQUIRED")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")

    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    google: GoogleOAuthSettings = Field(default_factory=GoogleOAuthSettings)
    authentik: AuthentikSettings = Field(default_factory=AuthentikSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)

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
