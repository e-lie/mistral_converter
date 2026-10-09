import json
import zipfile

from fastapi.testclient import TestClient

from conftest import FakeMistral, upload, wait_for
from mistral_converter.web.app import create_app

PAGES = [
    {
        "index": 0,
        "markdown": "## Title\n\ntext",
        "images": [],
        "blocks": [
            {"type": "title", "content": "## Title"},
            {"type": "text", "content": "text"},
        ],
    }
]


class BookMistral(FakeMistral):
    def __init__(self):
        self.chat_calls = []

    def ocr(self, pdf):
        return {"pages": PAGES}

    def chat_json(self, model, prompt):
        self.chat_calls.append(model)
        if "headings" in prompt:
            return json.dumps({"edits": [{"page": 0, "block": 0, "action": "set_level", "level": 1}]})
        return json.dumps({"title": "Inferred", "author": "Someone"})


def post(client, step, **fields):
    return client.post(f"/steps/{step}", data={"folder": "books", "stem": "book", **fields})


def folder_of(settings):
    return settings.data_dir / "alice/books"


def opf(path):
    with zipfile.ZipFile(path) as z:
        return next(z.read(n).decode() for n in z.namelist() if n.endswith(".opf"))


def done_count(page):
    return page.count("✓")


def test_fix_and_epub_need_ocr(client):
    upload(client)
    assert post(client, "fix").status_code == 409
    assert post(client, "epub").status_code == 409
    page = client.get("/books", params={"folder": "books"}).text
    assert page.count("disabled") == 2


def test_epub_uses_fixed_response_when_present(settings):
    client = TestClient(create_app(settings, BookMistral()), headers={"Remote-User": "alice"})
    upload(client)
    post(client, "ocr")
    wait_for(client, "books", lambda p: done_count(p) == 1)
    post(client, "epub")
    wait_for(client, "books", lambda p: done_count(p) == 2)
    raw_epub = (folder_of(settings) / "book.epub").read_bytes()
    with zipfile.ZipFile(folder_of(settings) / "book.epub") as z:
        raw_text = "".join(z.read(n).decode() for n in z.namelist() if n.endswith(".xhtml"))
    assert "<h2" in raw_text and "<h1" not in raw_text

    post(client, "fix")
    wait_for(client, "books", lambda p: done_count(p) == 3)
    assert (folder_of(settings) / "book.fixed.ocr.json").exists()
    assert post(client, "epub").status_code == 409
    post(client, "epub", overwrite="true")
    wait_for(client, "books", lambda p: "⏳" not in p)
    with zipfile.ZipFile(folder_of(settings) / "book.epub") as z:
        fixed_text = "".join(z.read(n).decode() for n in z.namelist() if n.endswith(".xhtml"))
    assert "<h1" in fixed_text
    assert (folder_of(settings) / "book.epub").read_bytes() != raw_epub


def test_metadata_form_overrides_inferred(settings):
    client = TestClient(create_app(settings, BookMistral()), headers={"Remote-User": "alice"})
    upload(client)
    post(client, "ocr")
    wait_for(client, "books", lambda p: done_count(p) == 1)
    post(client, "epub", title="Mine", language="en")
    wait_for(client, "books", lambda p: done_count(p) == 2)
    package = opf(folder_of(settings) / "book.epub")
    assert "Mine" in package and "Inferred" not in package and "Someone" in package


def test_rerun_requires_overwrite_and_replaces(settings):
    api = BookMistral()
    client = TestClient(create_app(settings, api), headers={"Remote-User": "alice"})
    upload(client)
    post(client, "ocr")
    wait_for(client, "books", lambda p: done_count(p) == 1)
    assert post(client, "ocr").status_code == 409
    page = client.get("/books", params={"folder": "books"}).text
    assert "hx-confirm" in page
    (folder_of(settings) / "book.ocr.json").write_text("{}")
    assert post(client, "ocr", overwrite="true").status_code == 200
    wait_for(client, "books", lambda p: "⏳" not in p)
    assert json.loads((folder_of(settings) / "book.ocr.json").read_text())["pages"]


def test_run_all_chains_the_three_steps(settings):
    client = TestClient(create_app(settings, BookMistral()), headers={"Remote-User": "alice"})
    upload(client)
    assert post(client, "all").status_code == 200
    wait_for(client, "books", lambda p: done_count(p) == 3)
    folder = folder_of(settings)
    assert all((folder / name).exists() for name in ("book.ocr.json", "book.fixed.ocr.json", "book.epub"))
    assert post(client, "all").status_code == 409


def test_run_all_failure_of_ocr_marks_later_steps_failed(settings):
    class Failing(BookMistral):
        def ocr(self, pdf):
            raise RuntimeError("quota exceeded")

    client = TestClient(create_app(settings, Failing()), headers={"Remote-User": "alice"})
    upload(client)
    post(client, "all")
    page = wait_for(client, "books", lambda p: "⏳" not in p)
    assert "quota exceeded" in page and "OCR is not done" in page
    assert not (folder_of(settings) / "book.epub").exists()


def test_unknown_step_and_other_user(client, other_client):
    upload(client)
    assert post(client, "bogus").status_code == 404
    assert post(other_client, "all").status_code == 404
