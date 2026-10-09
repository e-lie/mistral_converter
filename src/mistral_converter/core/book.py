import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Step(Enum):
    OCR = "ocr"
    FIX = "fix"
    EPUB = "epub"


_SUFFIXES = (".json", ".ocr", ".fixed", ".pdf", ".md", ".epub")


def write_atomic(path: Path, data: str | bytes) -> Path:
    """Write to a temporary file then rename, so the path exists only once complete."""
    handle, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data.encode("utf-8") if isinstance(data, str) else data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def write_json_atomic(path: Path, data) -> Path:
    return write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


@dataclass(frozen=True)
class Book:
    """A source document and its derived files, which share a stem in a Working folder."""

    folder: Path
    stem: str

    @classmethod
    def of(cls, path: Path) -> "Book":
        """Book owning any of its files (source document, OCR response, fixed response...)."""
        name = path.name
        for _ in range(3):
            for suffix in _SUFFIXES:
                if name.endswith(suffix) and name != suffix:
                    name = name.removesuffix(suffix)
                    break
            else:
                break
        return cls(path.parent, name)

    def _file(self, suffix: str) -> Path:
        return self.folder / (self.stem + suffix)

    @property
    def pdf(self) -> Path:
        return self._file(".pdf")

    @property
    def ocr_json(self) -> Path:
        return self._file(".ocr.json")

    @property
    def markdown(self) -> Path:
        return self._file(".md")

    @property
    def fixed_json(self) -> Path:
        return self._file(".fixed.ocr.json")

    @property
    def meta_json(self) -> Path:
        return self._file(".meta.json")

    @property
    def epub(self) -> Path:
        return self._file(".epub")

    def results(self, step: Step) -> list[Path]:
        return {
            Step.OCR: [self.ocr_json, self.markdown],
            Step.FIX: [self.fixed_json],
            Step.EPUB: [self.epub],
        }[step]

    def is_done(self, step: Step) -> bool:
        return all(path.exists() for path in self.results(step))

    def status(self) -> dict[Step, bool]:
        return {step: self.is_done(step) for step in Step}

    @property
    def best_ocr_json(self) -> Path:
        """The fixed OCR response when present, the original otherwise."""
        return self.fixed_json if self.fixed_json.exists() else self.ocr_json


@dataclass(frozen=True)
class WorkingFolder:
    """A directory holding source documents and everything derived from them."""

    path: Path

    def books(self) -> list[Book]:
        return [Book(self.path, pdf.stem) for pdf in sorted(self.path.glob("*.pdf"))]
