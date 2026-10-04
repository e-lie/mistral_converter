import argparse
import json
from pathlib import Path

from mistral_converter.epub import build_epub
from mistral_converter.metadata import Metadata, resolve_metadata
from mistral_converter.ocr import ocr_document


def epub_command(args) -> list[Path]:
    stem = args.ocr_json.name.removesuffix(".json").removesuffix(".ocr")
    pages = json.loads(args.ocr_json.read_text(encoding="utf-8"))["pages"]
    overrides = Metadata(
        title=args.title,
        author=args.author,
        date=args.date,
        publisher=args.publisher,
        language=args.language,
    )
    metadata = resolve_metadata(
        pages, args.ocr_json.with_name(stem + ".meta.json"), overrides, stem
    )
    return [build_epub(pages, metadata, args.ocr_json.with_name(stem + ".epub"))]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mistral-converter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ocr = subparsers.add_parser("ocr", help="OCR a source document")
    ocr.add_argument("source", type=Path)
    ocr.set_defaults(handler=lambda args: ocr_document(args.source))

    epub = subparsers.add_parser("epub", help="Build an EPUB from an OCR response")
    epub.add_argument("ocr_json", type=Path)
    epub.add_argument("--title")
    epub.add_argument("--author")
    epub.add_argument("--language")
    epub.add_argument("--publisher")
    epub.add_argument("--date")
    epub.set_defaults(handler=epub_command)

    return parser


def main():
    args = build_parser().parse_args()
    for path in args.handler(args):
        print(path)
