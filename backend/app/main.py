"""应用入口：当前仅提供基础健康检查。"""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.settings import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(health_router, prefix="/api")
