from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_dotenv() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("XIAOBA_AUTODEV_APP_NAME", "XiaoBa-AutoDev")
    host: str = os.getenv("XIAOBA_AUTODEV_HOST", "0.0.0.0")
    port: int = int(os.getenv("XIAOBA_AUTODEV_PORT", "8090"))
    page_size: int = int(os.getenv("XIAOBA_AUTODEV_PAGE_SIZE", "50"))

    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "xiaoba_autodev")

    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "xiaoba-autodev")
    minio_region: str = os.getenv("MINIO_REGION", "ap-guangzhou")
    minio_secure: bool = env_bool("MINIO_SECURE", False)
    artifact_prefix: str = os.getenv("XIAOBA_AUTODEV_ARTIFACT_PREFIX", "cases")
    log_prefix: str = os.getenv("XIAOBA_AUTODEV_LOG_PREFIX", "session-logs")

    @property
    def workdir_root(self) -> Path:
        return ROOT_DIR / "data" / "cases"


settings = Settings()
settings.workdir_root.mkdir(parents=True, exist_ok=True)
