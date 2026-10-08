"""应用入口。"""

from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.health import router as health_router
from app.api.lyrics import router as lyrics_router
from app.api.music_jobs import router as music_jobs_router
from app.settings import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
install_error_handlers(app)
app.include_router(health_router, prefix="/api")
app.include_router(lyrics_router, prefix="/api")
app.include_router(music_jobs_router, prefix="/api")
