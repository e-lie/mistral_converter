import json

import pytest
from fastapi.testclient import TestClient

from mistral_converter.web.app import create_app
from mistral_converter.web.settings import Settings


class FakeMistral:
    def ocr(self, pdf: bytes) -> dict:
        return {"pages": [{"index": 0, "markdown": "# Title\n\ntext", "images": [], "blocks": []}]}

    def chat_json(self, model: str, prompt: str) -> str:
        return json.dumps({"edits": []})


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", max_upload_mb=1)


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings, FakeMistral()), headers={"Remote-User": "alice"})


@pytest.fixture
def other_client(settings, client):
    return TestClient(client.app, headers={"Remote-User": "bob"})


PDF = b"%PDF-1.4\n%fake\n"


def upload(client, folder="books", name="book.pdf", content=PDF):
    return client.post(
        "/upload",
        data={"folder": folder},
        files={"file": (name, content, "application/pdf")},
        follow_redirects=False,
    )


def wait_for(client, folder, predicate, timeout=5):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        page = client.get("/books", params={"folder": folder}).text
        if predicate(page):
            return page
        time.sleep(0.02)
    raise AssertionError(f"condition not met, last page:\n{page}")
