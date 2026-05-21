from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rva_api.api.media.live_video import router as live_video_router
from rva_api.api.v1.live import router as live_router

app = FastAPI(title="Retail Video Analytics API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(live_router, prefix="/api/v1")
app.include_router(live_video_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
