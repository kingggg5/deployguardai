from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .auth.oidc import OIDCVerifier
from .config import Settings, get_settings
from .database import Database
from .errors import DomainError, domain_error_handler
from .operations_api import router as operations_router
from .provider_api import router as provider_router
from .seed import seed_database
from .workspace_api import router as workspace_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configured_settings = settings or get_settings()
    database = Database(configured_settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        database.migrate(
            allow_legacy_bootstrap=configured_settings.environment.lower()
            in {"development", "test", "container"}
        )
        session = database.session_factory()
        try:
            if configured_settings.seed_synthetic_data:
                seed_database(session)
        finally:
            session.close()
        yield
        database.dispose()

    application = FastAPI(
        title=configured_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = configured_settings
    application.state.database = database
    application.state.oidc_verifier = (
        OIDCVerifier(configured_settings)
        if configured_settings.auth_provider == "oidc"
        else None
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(DomainError, domain_error_handler)
    application.include_router(router)
    application.include_router(workspace_router)
    application.include_router(provider_router)
    application.include_router(operations_router)
    return application


app = create_app()
