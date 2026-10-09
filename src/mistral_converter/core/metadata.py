import json
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from mistral_converter.core.book import write_json_atomic
from mistral_converter.core.content import body_markdown
from mistral_converter.core.mistral import MistralApi, MistralClient

METADATA_MODEL = "mistral-small-latest"
METADATA_PAGES = 10
DEFAULT_LANGUAGE = "fr"
PROMPT = (
    "Here is the text of the first pages of a book. Reply with a JSON object with the keys "
    '"title", "author", "date" (publication date), "publisher" and "language" (ISO 639-1 '
    "code). Use null for a value that is not in the text."
)


@dataclass
class Metadata:
    title: str | None = None
    author: str | None = None
    date: str | None = None
    publisher: str | None = None
    language: str | None = None

    def __post_init__(self):
        # the model or a hand-edited file may give numbers, e.g. a bare year
        for f in fields(self):
            value = getattr(self, f.name)
            setattr(self, f.name, str(value) if value not in (None, "") else None)


def infer_metadata(pages: list[dict], api: MistralApi | None = None) -> Metadata:
    """Ask a Mistral chat model for the book metadata from the first pages."""
    text, _ = body_markdown(pages[:METADATA_PAGES])
    api = api or MistralClient()
    data = json.loads(api.chat_json(METADATA_MODEL, f"{PROMPT}\n\n{text}"))
    return Metadata(**{f.name: data.get(f.name) or None for f in fields(Metadata)})


def _merge(*layers: Metadata) -> Metadata:
    """First non-empty value of each field, in layer order."""
    return Metadata(
        **{f.name: next((v for layer in layers if (v := getattr(layer, f.name))), None) for f in fields(Metadata)}
    )


def resolve_metadata(
    pages: list[dict],
    meta_path: Path,
    overrides: Metadata,
    fallback_title: str,
    api: MistralApi | None = None,
) -> Metadata:
    """CLI overrides, then the metadata file, then the model; fall back with a warning."""
    stored = Metadata()
    if meta_path.exists():
        stored = Metadata(**json.loads(meta_path.read_text(encoding="utf-8")))
    inferred = Metadata()
    if not meta_path.exists() and not all(asdict(overrides).values()):
        try:
            inferred = infer_metadata(pages, api)
            write_json_atomic(meta_path, asdict(inferred))
        except Exception as error:
            print(f"warning: metadata inference failed ({error})", file=sys.stderr)
    return _merge(
        overrides, stored, inferred, Metadata(title=fallback_title, language=DEFAULT_LANGUAGE)
    )
