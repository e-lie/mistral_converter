import subprocess

from fastapi.testclient import TestClient

from conftest import FakeMistral, upload, wait_for
from mistral_converter.web.app import create_app
from mistral_converter.web.settings import Settings


class Rbw:
    """Fake rbw: locked until `unlock` is called."""

    def __init__(self):
        self.locked = True
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if self.locked:
            raise subprocess.CalledProcessError(1, ["rbw", *args])
        return "secret-key\n"


def make(tmp_path, rbw, user=None):
    keys = []
    settings = Settings(
        data_dir=tmp_path / "data", rbw_item="mistral", rbw_user=user, rbw_retry_seconds=0.02
    )

    def factory(key):
        keys.append(key)
        return FakeMistral()

    app = create_app(settings, rbw=rbw, api_factory=factory)
    return TestClient(app, headers={"Remote-User": "alice"}), keys


def post(client, step):
    return client.post(f"/steps/{step}", data={"folder": "books", "stem": "book"})


def test_locked_vault_refuses_steps_then_recovers(tmp_path):
    rbw = Rbw()
    client, keys = make(tmp_path, rbw, user="me")
    upload(client)

    page = client.get("/", params={"folder": "books"})
    assert page.status_code == 200 and "API key is unavailable" in page.text
    assert post(client, "ocr").status_code == 503
    assert post(client, "all").status_code == 503

    rbw.locked = False
    import time

    deadline = time.time() + 5
    while "API key is unavailable" in client.get("/", params={"folder": "books"}).text:
        assert time.time() < deadline
        time.sleep(0.02)
    assert rbw.calls[-1] == ["get", "mistral", "me"]

    assert post(client, "ocr").status_code == 200
    wait_for(client, "books", lambda p: "✓" in p)
    assert keys == ["secret-key"]


def test_item_not_configured_means_unavailable(tmp_path):
    client = TestClient(
        create_app(Settings(data_dir=tmp_path / "data")), headers={"Remote-User": "alice"}
    )
    upload(client)
    assert "API key is unavailable" in client.get("/").text
    assert post(client, "ocr").status_code == 503


def test_missing_rbw_binary_keeps_service_running(tmp_path):
    def missing(args):
        raise FileNotFoundError("rbw")

    client, _ = make(tmp_path, missing)
    assert client.get("/").status_code == 200
    assert "API key is unavailable" in client.get("/").text
