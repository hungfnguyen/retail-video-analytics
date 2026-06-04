from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rva_api.api.media.live_video import router as live_video_router
from rva_api.api.media.live_webrtc import (
    close_peer_connections,
    router as live_webrtc_router,
)
from rva_api.api.v1.analytics import router as analytics_router
from rva_api.api.v1.live import router as live_router
from rva_api.api.v1.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_peer_connections()


app = FastAPI(
    title="Retail Video Analytics API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(live_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(live_video_router)
app.include_router(live_webrtc_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
