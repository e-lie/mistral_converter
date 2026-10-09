import pytest
from fastapi.testclient import TestClient

from conftest import PDF, upload
from mistral_converter.web.app import create_app


def test_upload_list_download_delete(client, settings):
    assert upload(client).status_code == 303
    assert (settings.data_dir / "alice/books/book.pdf").read_bytes() == PDF

    page = client.get("/", params={"folder": "books"})
    assert page.status_code == 200
    assert "book" in page.text and "kind=pdf" in page.text

    download = client.get("/download", params={"folder": "books", "stem": "book", "kind": "pdf"})
    assert download.status_code == 200 and download.content == PDF

    deleted = client.post("/delete", data={"folder": "books", "stem": "book"}, follow_redirects=False)
    assert deleted.status_code == 303
    assert not (settings.data_dir / "alice/books/book.pdf").exists()
    assert "No books yet" in client.get("/", params={"folder": "books"}).text


@pytest.mark.parametrize("folder", ["..", "../bob", "/etc", "a/../..", ".hidden", "a//b", "."])
def test_escaping_folder_is_refused(client, settings, folder):
    assert upload(client, folder=folder).status_code == 400
    assert client.get("/", params={"folder": folder}).status_code == 400
    assert not (settings.data_dir / "bob").exists()


def test_users_are_isolated(client, other_client):
    upload(client, name="secret.pdf")
    assert "secret" not in other_client.get("/", params={"folder": "books"}).text
    response = other_client.get("/download", params={"folder": "books", "stem": "secret", "kind": "pdf"})
    assert response.status_code == 404
    other_client.post("/delete", data={"folder": "books", "stem": "secret"})
    assert client.get("/download", params={"folder": "books", "stem": "secret", "kind": "pdf"}).status_code == 200


def test_user_name_cannot_escape(client):
    bad = TestClient(client.app, headers={"Remote-User": ".."})
    assert bad.get("/").status_code == 400


def test_missing_identity_is_refused(client):
    assert TestClient(client.app).get("/").status_code == 401


def test_non_pdf_upload_is_refused(client):
    by_name = upload(client, name="notes.txt", content=PDF)
    assert by_name.status_code == 400 and "PDF" in by_name.text
    by_content = upload(client, content=b"not a pdf at all")
    assert by_content.status_code == 400 and "not a valid PDF" in by_content.text


def test_oversized_upload_is_refused(client, settings):
    response = upload(client, content=PDF + b"0" * (2 * 1024 * 1024))
    assert response.status_code == 413 and "too large" in response.text
    assert not list((settings.data_dir / "alice/books").glob("*"))


def test_duplicate_upload_is_refused(client):
    upload(client)
    assert upload(client).status_code == 409


def test_download_cannot_traverse(client):
    upload(client)
    for stem in ("../book", "..", "a/b"):
        response = client.get("/download", params={"folder": "books", "stem": stem, "kind": "pdf"})
        assert response.status_code in (400, 404)


def test_links_honour_root_path(settings):
    client = TestClient(create_app(settings), root_path="/converter", headers={"Remote-User": "alice"})
    upload(client)
    page = client.get("/", params={"folder": "books"}).text
    assert 'action="/converter/upload"' in page
    assert 'href="/converter/download?' in page
    assert upload(client, name="two.pdf").headers["location"].startswith("/converter/")
