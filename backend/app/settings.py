"""统一读取项目根目录的环境变量文件。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "AI 写词与作曲"
    runtime_dir: Path = Path("runtime")
    model_api_url: str = ""
    model_api_key: str = ""
    model_name: str = ""
    fluidsynth_path: str = ""
    ffmpeg_path: str = ""
    soundfont_path: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
