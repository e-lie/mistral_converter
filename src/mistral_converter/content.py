import re
from dataclasses import dataclass, field

from markdown_it import MarkdownIt

FURNITURE_TYPES = {"header", "footer"}
FOOTNOTE_TYPE = "references"
CHAPTER_LEVELS = {1, 2}
PRELIMINARY_TITLE = "Préliminaires"
FINAL_PUNCTUATION = ".!?…»”\"':;"

_md = MarkdownIt("commonmark").enable("table")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_NOTE_START = re.compile(r"^\s*(\d+)\s*[.)]\s+", re.MULTILINE)
_SUPERSCRIPT_CALL = re.compile(r"\$\^\{(\d+)\}\$")
_LEFTOVER_SUPERSCRIPT = re.compile(r"\$\^\{([^}]*)\}\$")
# a number glued to the last word of a sentence, or following its final punctuation
_BARE_CALL = re.compile(
    r"(?<=[^\W\d_])(\d{1,3})(?=[.!?…»”]?(?:\s|$))|(?<=[.!?…»”])(\d{1,3})(?=\s|$)"
)


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


def parse_footnotes(content: str) -> dict[int, str]:
    """Split a `references` block into footnotes keyed by their printed number."""
    starts = list(_NOTE_START.finditer(content))
    notes = {}
    for match, following in zip(starts, [*starts[1:], None]):
        text = content[match.end() : following.start() if following else None]
        notes.setdefault(int(match.group(1)), " ".join(text.split()))
    return notes


def body_markdown(pages: list[dict]) -> tuple[str, dict[int, str]]:
    """Book body Markdown and footnotes; no page furniture, split paragraphs joined."""
    chunks: list[str] = []
    notes: dict[int, str] = {}
    last_text_ends_page = False
    for page in pages:
        page_blocks = [b for b in page.get("blocks") or [] if b["type"] not in FURNITURE_TYPES]
        for b in page_blocks:
            if b["type"] == FOOTNOTE_TYPE:
                for number, text in parse_footnotes(b["content"]).items():
                    notes.setdefault(number, text)
        blocks = [b for b in page_blocks if b["type"] != FOOTNOTE_TYPE]
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
    return "\n\n".join(chunks), notes


def _link_calls(markdown: str, numbers: set[int]) -> tuple[str, set[int]]:
    """Link footnote calls matching `numbers`; return the Markdown and the numbers used."""
    used: set[int] = set()

    def link(match: re.Match) -> str:
        number = int(next(g for g in match.groups() if g))
        if number not in numbers:
            return match.group(0)
        first = number not in used
        used.add(number)
        anchor = f' id="fnref-{number}"' if first else ""
        return f'<sup><a{anchor} href="#fn-{number}">{number}</a></sup>'

    lines = []
    for line in markdown.split("\n"):
        if not line.startswith("#"):
            line = _SUPERSCRIPT_CALL.sub(link, line)
            line = _BARE_CALL.sub(link, line)
        lines.append(line)
    return "\n".join(lines), used


def _footnotes_html(notes: dict[int, str]) -> str:
    items = "".join(
        f'<li value="{n}" id="fn-{n}">{_md.renderInline(text)} <a href="#fnref-{n}">↩</a></li>'
        for n, text in sorted(notes.items())
    )
    return f'<section class="footnotes"><hr/><ol>{items}</ol></section>' if items else ""


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


def split_chapters(markdown: str, notes: dict[int, str]) -> list[Chapter]:
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
        text, used = _link_calls("\n\n".join(chunks), set(notes))
        chapter.html = _render(text, chapter, counter)
        chapter.html += _footnotes_html({n: notes[n] for n in used})
        chapter.html = _LEFTOVER_SUPERSCRIPT.sub(r"<sup>\1</sup>", chapter.html)
        chapters.append(chapter)
    return chapters
