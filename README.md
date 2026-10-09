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
MC_DATA_DIR=data MC_DEV_USER=me MC_RBW_ITEM=mistral uv run uvicorn --factory mistral_converter.web.app:create_app
```

| Variable | Purpose | Default |
| --- | --- | --- |
| `MC_DATA_DIR` | where books are stored, one folder per user | `data` |
| `MC_USER_HEADER` | request header carrying the user name | `Remote-User` |
| `MC_DEV_USER` | user to assume when the header is absent (development) | none |
| `MC_MAX_UPLOAD_MB` | upload size limit | `200` |
| `MC_ROOT_PATH` | URL prefix when served under a path | empty |
| `MC_RBW_ITEM` | [rbw](https://github.com/doy/rbw) item holding the Mistral API key | none |
| `MC_RBW_USER` | entry user, if the item name is ambiguous | none |
| `MC_RBW_RETRY_SECONDS` | delay between key lookups while the vault is locked | `30` |

The API key is read with `rbw get` and kept in memory only. While it is unavailable, OCR and heading fix are refused.

## Tests

```bash
uv run pytest
```
