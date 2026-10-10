# mistral_converter

Convert scanned books and PDFs into clean Markdown and EPUB with the Mistral OCR API.

Three steps, each producing files next to the source PDF:

1. **OCR**: `book.ocr.json` and `book.md`
2. **Heading fix**: `book.fixed.ocr.json`, with the heading hierarchy rebuilt by an LLM
3. **EPUB**: `book.epub`, with chapters, table of contents, images and footnotes

## Install

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # then set MISTRAL_API_KEY
```

## Command line

```bash
uv run --env-file .env mistral-converter ocr book.pdf
uv run --env-file .env mistral-converter fix book.ocr.json
uv run --env-file .env mistral-converter epub book.ocr.json --title "Title" --author "Author"
uv run --env-file .env mistral-converter convert book.pdf
```

`make ocr|fix|epub|convert PDF=book.pdf` does the same.

## Web interface

A small web UI (FastAPI and htmx) lets signed-in users upload PDFs, run the steps separately or all at once, follow their status and download the results.

```bash
uv sync --extra web
MC_DATA_DIR=data MC_DEV_USER=me uv run uvicorn --factory mistral_converter.web.app:create_app
```

| Variable | Purpose | Default |
| --- | --- | --- |
| `MC_DATA_DIR` | where books are stored, one folder per user | `data` |
| `MC_USER_HEADER` | request header carrying the user name | `Remote-User` |
| `MC_DEV_USER` | user to assume when the header is absent (development) | none |
| `MC_MAX_UPLOAD_MB` | upload size limit | `200` |
| `MC_ROOT_PATH` | URL prefix when served under a path | empty |

Each user enters their Mistral API key in the web page; it is stored in `<MC_DATA_DIR>/<user>/.mistral_key` (mode 600). While it is not set, OCR and heading fix are refused.

## YunoHost

The repository root is also a YunoHost package (`manifest.toml`, `scripts/`, `conf/`). Install and upgrade commands are in `doc/ADMIN.md`.

## Tests

```bash
uv run pytest
```
