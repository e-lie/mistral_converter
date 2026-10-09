import threading

import pytest
from fastapi.testclient import TestClient

from conftest import FakeMistral, upload, wait_for
from mistral_converter.web.app import create_app


class GatedMistral(FakeMistral):
    """OCR blocks until released; records how many calls overlap."""

    def __init__(self):
        self.release = threading.Event()
        self.started = threading.Semaphore(0)
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self._lock = threading.Lock()

    def ocr(self, pdf):
        with self._lock:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.started.release()
        self.release.wait(5)
        with self._lock:
            self.active -= 1
        return super().ocr(pdf)


class FailingMistral(FakeMistral):
    def ocr(self, pdf):
        raise RuntimeError("quota exceeded")


def start(client, stem, folder="books"):
    return client.post("/steps/ocr", data={"folder": folder, "stem": stem})


def test_ocr_lifecycle(client, settings):
    upload(client)
    page = client.get("/", params={"folder": "books"}).text
    assert "Run" in page and "⏳" not in page

    started = start(client, "book")
    assert started.status_code == 200

    page = wait_for(client, "books", lambda p: "✓" in p)
    assert "⏳" not in page and "hx-trigger" not in page
    folder = settings.data_dir / "alice/books"
    assert (folder / "book.ocr.json").exists() and (folder / "book.md").read_text() == "# Title\n\ntext"
    assert "kind=ocr" in page and "kind=md" in page
    assert start(client, "book").status_code == 409


def test_hourglass_and_polling_while_running(settings):
    api = GatedMistral()
    client = TestClient(create_app(settings, api), headers={"Remote-User": "alice"})
    upload(client)
    page = start(client, "book").text
    assert "⏳" in page and 'hx-trigger="every 2s"' in page
    api.started.acquire(timeout=5)
    assert "⏳" in client.get("/books", params={"folder": "books"}).text
    assert client.post("/delete", data={"folder": "books", "stem": "book"}).status_code == 409
    api.release.set()
    wait_for(client, "books", lambda p: "✓" in p)


def test_steps_run_one_at_a_time_across_users(settings):
    api = GatedMistral()
    app = create_app(settings, api)
    alice = TestClient(app, headers={"Remote-User": "alice"})
    bob = TestClient(app, headers={"Remote-User": "bob"})
    upload(alice, name="a.pdf")
    upload(bob, name="b.pdf")
    start(alice, "a")
    start(bob, "b")
    api.started.acquire(timeout=5)
    assert "⏳" in bob.get("/books", params={"folder": "books"}).text
    assert api.calls == 1
    api.release.set()
    wait_for(alice, "books", lambda p: "✓" in p)
    wait_for(bob, "books", lambda p: "✓" in p)
    assert api.calls == 2 and api.max_active == 1


def test_failure_is_shown_and_can_be_retried(settings):
    app = create_app(settings, FailingMistral())
    client = TestClient(app, headers={"Remote-User": "alice"})
    upload(client)
    start(client, "book")
    page = wait_for(client, "books", lambda p: "quota exceeded" in p)
    assert "Retry" in page and "⏳" not in page
    app.state.api = FakeMistral()
    start(client, "book")
    wait_for(client, "books", lambda p: "✓" in p)


def test_other_user_cannot_start_ocr(client, other_client):
    upload(client)
    assert start(other_client, "book").status_code == 404
    assert start(client, "../book").status_code in (400, 404)


def test_restart_clears_running_state(settings):
    api = GatedMistral()
    first = TestClient(create_app(settings, api), headers={"Remote-User": "alice"})
    upload(first)
    start(first, "book")
    api.started.acquire(timeout=5)
    restarted = TestClient(create_app(settings, FakeMistral()), headers={"Remote-User": "alice"})
    page = restarted.get("/books", params={"folder": "books"}).text
    assert "⏳" not in page and "Run" in page
    api.release.set()
