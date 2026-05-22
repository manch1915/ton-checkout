from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import ContainerDep
from app.api.routes import auth, dashboard, merchant_api, pay
from app.container import Container, build_container
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.demo_shop import routes as shop


class Health(BaseModel):
    status: str
    network: str
    provider: str


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.env)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or build_container(settings)
        try:
            yield
        finally:
            await app.state.container.close()

    app = FastAPI(
        title="TON Checkout",
        version="0.1.0",
        summary="Non-custodial checkout for Gram, USDT on TON and Telegram Stars",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (pay, merchant_api, auth, dashboard, shop):
        app.include_router(module.router)

    @app.get("/api/health", tags=["service"])
    async def health(container: ContainerDep) -> Health:
        async with container.sessions() as session:
            await session.execute(text("select 1"))
        return Health(status="ok", network=settings.ton_network, provider=container.provider.name)

    return app


app = create_app()
