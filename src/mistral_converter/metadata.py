import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from mistralai.client import Mistral

from mistral_converter.content import body_markdown

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


def infer_metadata(pages: list[dict]) -> Metadata:
    """Ask a Mistral chat model for the book metadata from the first pages."""
    text, _ = body_markdown(pages[:METADATA_PAGES])
    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    response = client.chat.complete(
        model=METADATA_MODEL,
        messages=[{"role": "user", "content": f"{PROMPT}\n\n{text}"}],
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return Metadata(**{f.name: data.get(f.name) or None for f in fields(Metadata)})


def _merge(*layers: Metadata) -> Metadata:
    """First non-empty value of each field, in layer order."""
    return Metadata(
        **{f.name: next((v for layer in layers if (v := getattr(layer, f.name))), None) for f in fields(Metadata)}
    )


def resolve_metadata(
    pages: list[dict], meta_path: Path, overrides: Metadata, fallback_title: str
) -> Metadata:
    """CLI overrides, then the metadata file, then the model; fall back with a warning."""
    stored = Metadata()
    if meta_path.exists():
        stored = Metadata(**json.loads(meta_path.read_text(encoding="utf-8")))
    inferred = Metadata()
    if not meta_path.exists() and not all(asdict(overrides).values()):
        try:
            inferred = infer_metadata(pages)
            meta_path.write_text(
                json.dumps(asdict(inferred), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as error:
            print(f"warning: metadata inference failed ({error})", file=sys.stderr)
    return _merge(
        overrides, stored, inferred, Metadata(title=fallback_title, language=DEFAULT_LANGUAGE)
    )
