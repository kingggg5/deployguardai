from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "DeployGuard AI"
    environment: str = "development"
    database_url: str = "sqlite:///./deployguard.db"
    github_webhook_secret: str = ""
    telemetry_ingest_token: str = ""
    allow_database_reset: bool = False
    auth_provider: Literal["development", "oidc", "disabled"] = "development"
    development_user_email: str = "owner@deployguard.local"
    development_user_name: str = "Local workspace owner"
    access_token_ttl_hours: int = Field(default=12, ge=1, le=168)
    invitation_ttl_hours: int = Field(default=72, ge=1, le=720)
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_client_id: str = ""
    oidc_scope: str = "openid profile email"
    oidc_jwks_url: str = ""
    oidc_algorithms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["RS256"]
    )
    oidc_leeway_seconds: int = Field(default=30, ge=0, le=300)
    frontend_public_url: str = "http://127.0.0.1:4300"
    github_app_id: str = ""
    github_app_slug: str = ""
    github_app_private_key: str = ""
    github_api_url: str = "https://api.github.com"
    github_api_version: str = "2026-03-10"
    github_checks_enabled: bool = False
    github_webhook_max_body_bytes: int = Field(
        default=1_048_576,
        ge=1_024,
        le=10_485_760,
    )
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:4200",
            "http://localhost:4200",
            "http://127.0.0.1:4201",
            "http://localhost:4201",
            "http://127.0.0.1:4300",
            "http://localhost:4300",
        ]
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("oidc_algorithms", mode="before")
    @classmethod
    def parse_oidc_algorithms(cls, value: object) -> object:
        if isinstance(value, str):
            return [
                algorithm.strip()
                for algorithm in value.split(",")
                if algorithm.strip()
            ]
        return value

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> "Settings":
        production = self.environment.strip().lower() == "production"
        if production and self.auth_provider != "oidc":
            raise ValueError(
                "Production requires AUTH_PROVIDER=oidc"
            )
        if (
            production
            and self.telemetry_ingest_token
            and len(self.telemetry_ingest_token) < 32
        ):
            raise ValueError(
                "Production TELEMETRY_INGEST_TOKEN must be at least "
                "32 characters because it is the collector credential root"
            )
        if self.auth_provider == "oidc":
            if not self.oidc_client_id.strip():
                self.oidc_client_id = self.oidc_audience
            missing = [
                name
                for name, value in (
                    ("OIDC_ISSUER", self.oidc_issuer),
                    ("OIDC_AUDIENCE", self.oidc_audience),
                    ("OIDC_JWKS_URL", self.oidc_jwks_url),
                )
                if not value.strip()
            ]
            if missing:
                raise ValueError(
                    "OIDC configuration is incomplete: "
                    + ", ".join(missing)
                )
            if not self.oidc_algorithms:
                raise ValueError("OIDC_ALGORITHMS cannot be empty")
        return self

    def development_auth_available(self) -> bool:
        return (
            self.auth_provider == "development"
            and self.environment.strip().lower() != "production"
        )

    def github_app_available(self) -> bool:
        return all(
            value.strip()
            for value in (
                self.github_app_id,
                self.github_app_slug,
                self.github_app_private_key,
            )
        )

    def email_delivery_mode(self) -> Literal[
        "smtp", "development_outbox", "disabled"
    ]:
        if self.smtp_host.strip() and self.smtp_from_email.strip():
            return "smtp"
        if self.environment.strip().lower() != "production":
            return "development_outbox"
        return "disabled"

@lru_cache
def get_settings() -> Settings:
    return Settings()
