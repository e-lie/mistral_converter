import re
from pathlib import Path

from mistral_converter.core.book import Book, WorkingFolder

_USER = re.compile(r"^[\w][\w.@-]*$")
_UNSAFE_STEM = re.compile(r"[^\w\- ]+")


class InvalidPath(ValueError):
    pass


def user_base(data_dir: Path, user: str) -> Path:
    if not _USER.match(user):
        raise InvalidPath("invalid user name")
    return data_dir / user


def working_folder(data_dir: Path, user: str, subfolder: str) -> WorkingFolder:
    """The user's Working folder for a subfolder name; refuses anything escaping the user's space."""
    base = user_base(data_dir, user).resolve()
    segments = subfolder.strip().split("/")
    if not all(s and s not in (".", "..") and not s.startswith(".") and "\\" not in s and "\x00" not in s for s in segments):
        raise InvalidPath("invalid folder name")
    path = (base / subfolder.strip()).resolve()
    if path == base or not path.is_relative_to(base):
        raise InvalidPath("invalid folder name")
    return WorkingFolder(path)


def subfolders(data_dir: Path, user: str) -> list[str]:
    base = user_base(data_dir, user)
    if not base.is_dir():
        return []
    return sorted({str(p.parent.relative_to(base)) for p in base.rglob("*.pdf")} - {"."})


def stem_from_filename(filename: str) -> str:
    stem = _UNSAFE_STEM.sub("_", Path(filename.replace("\\", "/")).stem).strip(" _")
    return stem or "book"


def delete_book(book: Book) -> None:
    for path in (book.pdf, book.ocr_json, book.markdown, book.fixed_json, book.meta_json, book.epub):
        path.unlink(missing_ok=True)
