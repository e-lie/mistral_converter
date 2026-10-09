from pathlib import Path

from mistral_converter.core.book import Book, write_atomic, write_json_atomic
from mistral_converter.core.mistral import MistralApi, MistralClient


def ocr_document(source: Path, api: MistralApi | None = None) -> tuple[Path, Path]:
    """Run Mistral OCR on a PDF and write the response JSON and Markdown next to it."""
    api = api or MistralClient()
    response = api.ocr(source.read_bytes())

    book = Book.of(source)
    write_json_atomic(book.ocr_json, response)
    write_atomic(book.markdown, "\n\n".join(page["markdown"] for page in response["pages"]))
    return book.ocr_json, book.markdown
