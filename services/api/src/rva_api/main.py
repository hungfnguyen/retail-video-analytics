from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rva_api.api.v1.live import router as live_router
from rva_api.api.v1.media import router as media_router

app = FastAPI(title="Retail Video Analytics API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(live_router, prefix="/api/v1")
app.include_router(media_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
