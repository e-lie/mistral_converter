import queue
import threading
from collections.abc import Callable

from mistral_converter.core.book import Book, Step

Key = tuple[str, str, Step]


class JobQueue:
    """One in-memory queue shared by all users; steps run one at a time.

    Queued and running steps both count as running. Failures are remembered until the
    step is started again. Nothing survives a restart.
    """

    def __init__(self):
        self._jobs: queue.Queue[tuple[Key, Callable[[], None]]] = queue.Queue()
        self._running: set[Key] = set()
        self._failed: dict[Key, str] = {}
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    @staticmethod
    def _key(book: Book, step: Step) -> Key:
        return (str(book.folder), book.stem, step)

    def state(self, book: Book, step: Step) -> tuple[str, str | None]:
        """("done" | "running" | "failed" | "todo", error message)."""
        key = self._key(book, step)
        with self._lock:
            if key in self._running:
                return "running", None
            if key in self._failed:
                return "failed", self._failed[key]
        return ("done", None) if book.is_done(step) else ("todo", None)

    def is_busy(self, book: Book) -> bool:
        with self._lock:
            return any(k[:2] == (str(book.folder), book.stem) for k in self._running)

    def submit(self, book: Book, step: Step, work: Callable[[], None]) -> bool:
        """Queue a step; False if it is already queued or running."""
        key = self._key(book, step)
        with self._lock:
            if key in self._running:
                return False
            self._running.add(key)
            self._failed.pop(key, None)
            if self._worker is None:
                self._worker = threading.Thread(target=self._work, daemon=True)
                self._worker.start()
        self._jobs.put((key, work))
        return True

    def _work(self) -> None:
        while True:
            key, work = self._jobs.get()
            try:
                work()
            except Exception as error:
                with self._lock:
                    self._failed[key] = str(error) or type(error).__name__
            finally:
                with self._lock:
                    self._running.discard(key)
