import subprocess
import threading
import time
from collections.abc import Callable

RbwRun = Callable[[list[str]], str]


def run_rbw(args: list[str]) -> str:
    return subprocess.run(["rbw", *args], capture_output=True, text=True, check=True, timeout=30).stdout


class KeyStore:
    """Mistral API key read with `rbw get`, kept in memory only.

    Resolution is retried in the background while the vault is locked or rbw is missing.
    """

    def __init__(self, item: str | None, user: str | None = None, run: RbwRun = run_rbw, retry_seconds: float = 30):
        self._item = item
        self._user = user
        self._run = run
        self._retry = retry_seconds
        self._key: str | None = None

    @property
    def key(self) -> str | None:
        return self._key

    def resolve(self) -> bool:
        if not self._item:
            return False
        try:
            key = self._run(["get", self._item, *([self._user] if self._user else [])]).strip()
        except Exception:
            return False
        self._key = key or None
        return self._key is not None

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self.resolve():
            time.sleep(self._retry)
