import argparse
import json
import sys
from pathlib import Path

from mistral_converter.core.book import Book, write_json_atomic
from mistral_converter.core.epub import build_epub
from mistral_converter.core.headings import HeadingFixError, fix_headings
from mistral_converter.core.metadata import Metadata, resolve_metadata
from mistral_converter.core.ocr import ocr_document


def fix_command(args) -> list[Path]:
    book = Book.of(args.ocr_json)
    if book.fixed_json.exists() and not args.force:
        return [book.fixed_json]
    response = json.loads(args.ocr_json.read_text(encoding="utf-8"))
    response["pages"] = fix_headings(response["pages"])
    return [write_json_atomic(book.fixed_json, response)]


def epub_command(args) -> list[Path]:
    book = Book.of(args.ocr_json)
    source = book.ocr_json if args.no_fix else book.best_ocr_json
    pages = json.loads(source.read_text(encoding="utf-8"))["pages"]
    overrides = Metadata(
        title=args.title,
        author=args.author,
        date=args.date,
        publisher=args.publisher,
        language=args.language,
    )
    metadata = resolve_metadata(pages, book.meta_json, overrides, book.stem)
    return [build_epub(pages, metadata, book.epub)]


def convert_command(args) -> list[Path]:
    json_path, md_path = ocr_document(args.source)
    args.ocr_json = json_path
    args.force = False
    produced = [json_path, md_path]
    if not args.no_fix:
        try:
            produced += fix_command(args)
        except Exception as error:
            print(f"warning: heading fix failed, using the original OCR response ({error})", file=sys.stderr)
            args.no_fix = True
    return [*produced, *epub_command(args)]


def _add_epub_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title")
    parser.add_argument("--author")
    parser.add_argument("--language")
    parser.add_argument("--publisher")
    parser.add_argument("--date")
    parser.add_argument("--no-fix", action="store_true", help="ignore the fixed OCR response")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mistral-converter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ocr = subparsers.add_parser("ocr", help="OCR a source document")
    ocr.add_argument("source", type=Path)
    ocr.set_defaults(handler=lambda args: ocr_document(args.source))

    fix = subparsers.add_parser("fix", help="Fix the headings of an OCR response")
    fix.add_argument("ocr_json", type=Path)
    fix.add_argument("--force", action="store_true", help="regenerate an existing fixed response")
    fix.set_defaults(handler=fix_command)

    epub = subparsers.add_parser("epub", help="Build an EPUB from an OCR response")
    epub.add_argument("ocr_json", type=Path)
    _add_epub_options(epub)
    epub.set_defaults(handler=epub_command)

    convert = subparsers.add_parser("convert", help="OCR a source document, then build its EPUB")
    convert.add_argument("source", type=Path)
    _add_epub_options(convert)
    convert.set_defaults(handler=convert_command)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        paths = args.handler(args)
    except HeadingFixError as error:
        sys.exit(f"error: {error}")
    for path in paths:
        print(path)
