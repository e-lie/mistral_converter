from fastapi.testclient import TestClient

from conftest import FakeMistral, upload, wait_for
from mistral_converter.web.app import create_app
from mistral_converter.web.settings import Settings


def make(tmp_path, user="alice"):
    keys = []

    def factory(key):
        keys.append(key)
        return FakeMistral()

    app = create_app(Settings(data_dir=tmp_path / "data"), api_factory=factory)
    return TestClient(app, headers={"Remote-User": user}), keys


def post(client, step):
    return client.post(f"/steps/{step}", data={"folder": "books", "stem": "book"})


def test_steps_refused_until_key_is_set(tmp_path):
    client, keys = make(tmp_path)
    upload(client)
    assert "API key is not set" in client.get("/", params={"folder": "books"}).text
    assert post(client, "ocr").status_code == 503
    assert post(client, "all").status_code == 503

    saved = client.post("/key", data={"key": " secret-key ", "folder": "books"}, follow_redirects=False)
    assert saved.status_code == 303
    page = client.get("/", params={"folder": "books"}).text
    assert "API key is not set" not in page and "secret-key" not in page

    assert post(client, "ocr").status_code == 200
    wait_for(client, "books", lambda p: "✓" in p)
    assert keys == ["secret-key"]


def test_key_is_per_user_and_removable(tmp_path):
    client, _ = make(tmp_path)
    client.post("/key", data={"key": "k"})
    other = TestClient(client.app, headers={"Remote-User": "bob"})
    assert "API key is not set" in other.get("/").text
    assert "API key is not set" not in client.get("/").text

    client.post("/key/delete")
    assert "API key is not set" in client.get("/").text


def test_empty_key_is_refused(tmp_path):
    client, _ = make(tmp_path)
    assert client.post("/key", data={"key": "  "}).status_code == 400
