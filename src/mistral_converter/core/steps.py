import json
from pathlib import Path

from mistral_converter.core.book import Book, write_json_atomic
from mistral_converter.core.epub import build_epub
from mistral_converter.core.headings import fix_headings
from mistral_converter.core.metadata import Metadata, resolve_metadata
from mistral_converter.core.mistral import MistralApi


def fix_book(book: Book, api: MistralApi | None = None, source: Path | None = None) -> Path:
    """Write the fixed OCR response of a book, from its OCR response or the given source."""
    response = json.loads((source or book.ocr_json).read_text(encoding="utf-8"))
    response["pages"] = fix_headings(response["pages"], api)
    return write_json_atomic(book.fixed_json, response)


def epub_book(
    book: Book,
    overrides: Metadata | None = None,
    api: MistralApi | None = None,
    source: Path | None = None,
) -> Path:
    """Build the EPUB of a book, from the fixed OCR response when present unless a source is given."""
    pages = json.loads((source or book.best_ocr_json).read_text(encoding="utf-8"))["pages"]
    metadata = resolve_metadata(pages, book.meta_json, overrides or Metadata(), book.stem, api)
    return build_epub(pages, metadata, book.epub)
