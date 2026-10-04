import re
from dataclasses import dataclass, field

from markdown_it import MarkdownIt

FURNITURE_TYPES = {"header", "footer"}
CHAPTER_LEVELS = {1, 2}
PRELIMINARY_TITLE = "Préliminaires"
FINAL_PUNCTUATION = ".!?…»”\"':;"

_md = MarkdownIt("commonmark").enable("table")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Heading:
    level: int
    title: str
    anchor: str


@dataclass
class Chapter:
    title: str
    html: str = ""
    headings: list[Heading] = field(default_factory=list)


def _block_markdown(block: dict) -> str:
    content = block["content"].strip()
    if block["type"] == "title":
        # OCR titles may span several lines; an ATX heading is a single line
        first, *rest = content.splitlines()
        if _HEADING.match(first):
            return " ".join([first, *(line.strip() for line in rest)])
    return content


def _ends_paragraph(text: str) -> bool:
    return text.rstrip("*_) ").endswith(tuple(FINAL_PUNCTUATION))


def _continues_paragraph(text: str) -> bool:
    return text[:1].islower()


def body_markdown(pages: list[dict]) -> str:
    """Markdown of the book body: no page furniture, split paragraphs joined."""
    chunks: list[str] = []
    last_text_ends_page = False
    for page in pages:
        blocks = [b for b in page.get("blocks") or [] if b["type"] not in FURNITURE_TYPES]
        for i, block in enumerate(blocks):
            markdown = _block_markdown(block)
            if (
                i == 0
                and last_text_ends_page
                and block["type"] == "text"
                and _continues_paragraph(markdown)
            ):
                previous = chunks[-1]
                if previous.endswith("-") and previous[-2:-1].isalpha():
                    chunks[-1] = previous[:-1] + markdown
                else:
                    chunks[-1] = previous + " " + markdown
            else:
                chunks.append(markdown)
        last = blocks[-1] if blocks else None
        last_text_ends_page = (
            last is not None
            and last["type"] == "text"
            and not _ends_paragraph(chunks[-1])
        )
    return "\n\n".join(chunks)


def _render(markdown: str, chapter: Chapter, counter: list[int]) -> str:
    tokens = _md.parse(markdown)
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            counter[0] += 1
            anchor = f"h{counter[0]}"
            token.attrSet("id", anchor)
            title = tokens[i + 1].content
            chapter.headings.append(Heading(int(token.tag[1]), title, anchor))
    return _md.renderer.render(tokens, _md.options, {})


def split_chapters(markdown: str) -> list[Chapter]:
    """Cut the Markdown into chapters opened by each level 1 or 2 heading."""
    sections: list[tuple[str, list[str]]] = [(PRELIMINARY_TITLE, [])]
    for chunk in markdown.split("\n\n"):
        match = _HEADING.match(chunk.strip().splitlines()[0]) if chunk.strip() else None
        if match and len(match.group(1)) in CHAPTER_LEVELS:
            sections.append((match.group(2).strip(), []))
        sections[-1][1].append(chunk)

    counter = [0]
    chapters = []
    for title, chunks in sections:
        if not any(c.strip() for c in chunks):
            continue
        chapter = Chapter(title)
        chapter.html = _render("\n\n".join(chunks), chapter, counter)
        chapters.append(chapter)
    return chapters
