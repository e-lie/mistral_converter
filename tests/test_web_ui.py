from conftest import upload


import dataclasses


def test_index_loads_stylesheets_with_root_path(settings):
    from fastapi.testclient import TestClient

    from mistral_converter.web.app import create_app

    settings = dataclasses.replace(settings, root_path="/conv")
    page = TestClient(create_app(settings, None), headers={"Remote-User": "alice"}).get("/").text
    assert 'href="/conv/static/pico.classless.min.css"' in page
    assert 'href="/conv/static/app.css"' in page
    assert "<style" not in page


def test_static_stylesheets_served(client):
    assert client.get("/static/pico.classless.min.css").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_books_fragment_components(client):
    upload(client)
    page = client.get("/books", params={"folder": "books"}).text
    assert 'name="folder" value="books"' in page
    assert 'name="stem" value="book"' in page
    assert 'class="danger"' in page


def test_error_rendered_as_alert(client):
    page = client.post("/upload", data={"folder": "books"}).text
    assert 'class="alert"' in page


def test_missing_key_alert_and_disabled_buttons(settings):
    from fastapi.testclient import TestClient

    from mistral_converter.web.app import create_app

    c = TestClient(create_app(settings), headers={"Remote-User": "alice"})
    upload(c)
    page = c.get("/", params={"folder": "books"}).text
    assert 'class="alert"' in page
    assert "disabled" in page


def test_styleguide_lists_components(client):
    page = client.get("/styleguide").text
    for part in ("badge running", "badge done", "badge failed", 'class="alert"', "secondary", "danger", "disabled", "hx-post"):
        assert part in page
