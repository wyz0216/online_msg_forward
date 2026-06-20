from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_path: Path
    upload_dir: Path
    max_upload_mb: int
    cleanup_token: str
    host: str
    port: int

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        secret_key=os.getenv("SECRET_KEY", "dev-secret-change-me"),
        database_path=Path(os.getenv("DATABASE_PATH", "data/app.db")),
        upload_dir=Path(os.getenv("UPLOAD_DIR", "uploads")),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "20")),
        cleanup_token=os.getenv("CLEANUP_TOKEN", "dev-cleanup-token"),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )
