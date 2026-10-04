import argparse
from pathlib import Path

from mistral_converter.ocr import ocr_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mistral-converter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ocr = subparsers.add_parser("ocr", help="OCR a source document")
    ocr.add_argument("source", type=Path)
    ocr.set_defaults(handler=lambda args: ocr_document(args.source))

    return parser


def main():
    args = build_parser().parse_args()
    for path in args.handler(args):
        print(path)
