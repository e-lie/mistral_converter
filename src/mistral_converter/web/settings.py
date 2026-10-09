import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    user_header: str = "Remote-User"
    dev_user: str | None = None
    max_upload_mb: int = 200
    root_path: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.environ.get("MC_DATA_DIR", "data")),
            user_header=os.environ.get("MC_USER_HEADER", "Remote-User"),
            dev_user=os.environ.get("MC_DEV_USER") or None,
            max_upload_mb=int(os.environ.get("MC_MAX_UPLOAD_MB", "200")),
            root_path=os.environ.get("MC_ROOT_PATH", ""),
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024
