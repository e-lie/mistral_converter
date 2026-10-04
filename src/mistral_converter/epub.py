import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ebooklib import epub

from mistral_converter.content import Chapter, Heading, body_markdown, split_chapters

@dataclass
class Metadata:
    title: str
    language: str = "fr"
    author: str | None = None
    publisher: str | None = None
    date: str | None = None
    identifier: str | None = None


def _build_toc(book_chapters: list[tuple[Chapter, str]]) -> list:
    """Nest headings by level into ebooklib TOC entries."""
    nodes: list[tuple[Heading, str, list]] = []
    roots: list[tuple[Heading, str, list]] = []
    stack: list[tuple[Heading, str, list]] = []
    for chapter, filename in book_chapters:
        headings = chapter.headings or [Heading(1, chapter.title, "")]
        for h in headings:
            node = (h, filename, [])
            while stack and stack[-1][0].level >= h.level:
                stack.pop()
            (stack[-1][2] if stack else roots).append(node)
            stack.append(node)
            nodes.append(node)

    def convert(node):
        h, filename, children = node
        href = f"{filename}#{h.anchor}" if h.anchor else filename
        if not children:
            return epub.Link(href, h.title, href)
        return (epub.Section(h.title, href), [convert(c) for c in children])

    return [convert(n) for n in roots]


def build_epub(ocr_json: Path, metadata: Metadata, output: Path) -> Path:
    """Build an EPUB from the page blocks and images of an OCR response."""
    response = json.loads(ocr_json.read_text(encoding="utf-8"))
    pages = response["pages"]

    book = epub.EpubBook()
    book.set_identifier(metadata.identifier or f"urn:mistral-converter:{metadata.title}")
    book.set_title(metadata.title)
    book.set_language(metadata.language)
    if metadata.author:
        book.add_author(metadata.author)
    if metadata.publisher:
        book.add_metadata("DC", "publisher", metadata.publisher)
    if metadata.date:
        book.add_metadata("DC", "date", metadata.date)

    seen_images: set[str] = set()
    for page in pages:
        for image in page.get("images") or []:
            data = image.get("image_base64")
            if not data or image["id"] in seen_images:
                continue
            seen_images.add(image["id"])
            media_type = data.split(";")[0].removeprefix("data:")
            book.add_item(
                epub.EpubItem(
                    uid=f"img-{image['id']}",
                    file_name=f"images/{image['id']}",
                    media_type=media_type,
                    content=base64.b64decode(data.split(",", 1)[1]),
                )
            )

    markdown, notes = body_markdown(pages)
    markdown = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"![\1](images/\2)", markdown)
    chapters = split_chapters(markdown, notes)

    items = []
    for i, chapter in enumerate(chapters, 1):
        item = epub.EpubHtml(
            title=chapter.title,
            file_name=f"chapter_{i:03d}.xhtml",
            lang=metadata.language,
            content=chapter.html,
        )
        book.add_item(item)
        items.append((chapter, item.file_name, item))

    book.toc = _build_toc([(c, f) for c, f, _ in items])
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *(item for _, _, item in items)]

    epub.write_epub(str(output), book)
    return output
