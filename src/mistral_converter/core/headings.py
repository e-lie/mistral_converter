import copy
import json
import re
import sys

from mistral_converter.core.content import FOOTNOTE_TYPE, FURNITURE_TYPES
from mistral_converter.core.mistral import MistralApi, MistralClient

HEADING_FIX_MODEL = "mistral-large-latest"
EXCERPT_CHARS = 200
TOC_MAX_CHARS = 8000
PRINTED_TOC_TITLE = re.compile(
    r"\btable\b.*\b(mati[èe]res|contents)\b|\bsommaire\b", re.IGNORECASE
)
PROMPT = """\
Below are the headings of a book converted by OCR, in reading order. Their levels are \
inconsistent: a chapter number and its title may be separate headings of different levels, \
sections of one chapter may sit at different levels, running titles and stray lines may be \
marked as headings, and levels may shift from one chapter to the next. Do not trust the \
original levels: rebuild the hierarchy logically from the content of the headings.

How to reason:
- Spot the numbering series: "CHAPITRE PREMIER", "CHAPITRE II", "CHAPITRE III"...; \
"PREMIÈRE PARTIE", "DEUXIÈME PARTIE"...; "I.", "II.", "III."; "1.", "2."; "A.", "B.". All \
members of one series play the same role and must get the same level, wherever they are in \
the book, even if the OCR gave them different levels.
- A series that restarts (a new "I." after "III.") means a new parent began: the numbered \
headings belong to the closest preceding heading of the level above (for example the sections \
"I.", "II." under the chapter that precedes them). Check that the sequence is complete and \
in order.
- A chapter number and its title (for example "CHAPITRE PREMIER" followed by "VIE DE \
SPINOZA") are one heading: merge them.
- Level 1 is the top-level division of the book: chapters, or the parts when the book groups \
its chapters into parts. Each level below is nested in the previous one (a chapter inside a \
part, a section inside a chapter). Unnumbered headings such as an introduction, a preface, \
a conclusion or a bibliography sit at the level of the chapters.
- Headings that repeat a running title, or that are stray lines, are not real headings: \
demote them.{toc_hint}

Reply with a JSON object {{"edits": [...]}}. Each edit targets a heading by its "page" and \
"block" values and has an "action":
- {{"page": p, "block": b, "action": "set_level", "level": 1-6}}
- {{"page": p, "block": b, "action": "merge"}}: merge the heading with the heading that \
immediately follows it; the result keeps the level of the first one. After a merge, give the \
level of the merged heading on the first one.
- {{"page": p, "block": b, "action": "demote"}}: turn the heading into plain text
Only edit what needs fixing. Never rewrite heading text. There must remain at least one \
level 1 heading.
"""
TOC_HINT = (
    "\n- The printed table of contents of the book is given below: use it as the reference "
    "for the order and the hierarchy of the parts, chapters and sections."
)
TOC_MIN_LINES = 5
TOC_PAGE_NUMBER_SHARE = 0.5
TOC_SHORT_LINE = 100
_TRAILING_PAGE_NUMBER = re.compile(r"(?<!\w)(\d{1,4}|[ivxlcdm]{1,8})\s*$", re.IGNORECASE)


class HeadingFixError(Exception):
    pass


_LEVEL_PREFIX = re.compile(r"^(#{1,6})\s*")


def _is_body(block: dict) -> bool:
    return block["type"] not in FURNITURE_TYPES and block["type"] != FOOTNOTE_TYPE


def _title_level(block: dict) -> int | None:
    match = _LEVEL_PREFIX.match(block["content"].lstrip())
    return len(match.group(1)) if match else None


def _title_text(block: dict) -> str:
    """Heading text on a single line, without the Markdown level prefix."""
    lines = [_LEVEL_PREFIX.sub("", line.strip()) for line in block["content"].splitlines()]
    return " ".join(line for line in lines if line)


def _body_blocks(pages: list[dict]) -> list[tuple[int, int, dict]]:
    return [
        (p, b, block)
        for p, page in enumerate(pages)
        for b, block in enumerate(page.get("blocks") or [])
        if _is_body(block)
    ]


def _entry_lines(text: str) -> list[str]:
    lines = [line.strip().rstrip("|").strip() for line in text.splitlines()]
    return [line for line in lines if line]


def _numbered_share(lines: list[str]) -> float:
    return sum(1 for line in lines if _TRAILING_PAGE_NUMBER.search(line)) / len(lines)


def looks_like_toc(text: str) -> bool:
    """Several lines, most of them ending with a page number."""
    lines = _entry_lines(text)
    return len(lines) >= TOC_MIN_LINES and _numbered_share(lines) >= TOC_PAGE_NUMBER_SHARE


def _continues_toc(block: dict) -> bool:
    """Titles and table of contents entries continue a printed table of contents; prose ends it."""
    if block["type"] == "title":
        return True
    lines = _entry_lines(block["content"])
    if len(lines) == 1:
        return len(lines[0]) < TOC_SHORT_LINE or _numbered_share(lines) > 0
    return bool(lines) and _numbered_share(lines) > TOC_PAGE_NUMBER_SHARE


def detect_printed_toc(pages: list[dict]) -> str | None:
    """Text of the printed table of contents, size-capped; None if no heading starts one.

    Starts at a table of contents heading and goes on through the titles and entries that
    follow, until prose; the result must look like a table of contents.
    """
    blocks = _body_blocks(pages)
    for i, (_, _, block) in enumerate(blocks):
        if block["type"] == "title" and PRINTED_TOC_TITLE.search(_title_text(block)):
            entries = []
            for _, _, following in blocks[i + 1 :]:
                if not _continues_toc(following):
                    break
                entries.append(following)
            while entries and entries[-1]["type"] == "title":
                entries.pop()  # a title right before the prose opens the next section
            text = "\n".join(
                _title_text(e) if e["type"] == "title" else e["content"].strip() for e in entries
            )
            if looks_like_toc(text):
                return text[:TOC_MAX_CHARS]
    return None


def describe_headings(pages: list[dict]) -> list[dict]:
    """Each title block with its position, level, text and a short excerpt of what follows."""
    blocks = _body_blocks(pages)
    headings = []
    for i, (p, b, block) in enumerate(blocks):
        if block["type"] != "title":
            continue
        excerpt = ""
        for _, _, following in blocks[i + 1 :]:
            if following["type"] == "title" or len(excerpt) >= EXCERPT_CHARS:
                break
            excerpt += " " + " ".join(following["content"].split())
        headings.append(
            {
                "page": p,
                "block": b,
                "level": _title_level(block),
                "text": _title_text(block),
                "excerpt": excerpt.strip()[:EXCERPT_CHARS],
            }
        )
    return headings


def propose_edits(pages: list[dict], api: MistralApi | None = None) -> list[dict]:
    """Ask the model for heading edits; raise HeadingFixError on failure or invalid answer."""
    toc = detect_printed_toc(pages)
    prompt = PROMPT.format(toc_hint=TOC_HINT if toc else "")
    parts = [prompt, "Headings:", json.dumps(describe_headings(pages), ensure_ascii=False)]
    if toc:
        parts += ["Printed table of contents:", toc]
    try:
        api = api or MistralClient()
        edits = json.loads(api.chat_json(HEADING_FIX_MODEL, "\n\n".join(parts)))["edits"]
    except Exception as error:
        raise HeadingFixError(f"heading fix failed ({error})") from error
    if not isinstance(edits, list):
        raise HeadingFixError("heading fix failed (edits is not a list)")
    return edits


def _warn(edit, reason: str) -> None:
    print(f"warning: heading edit ignored ({reason}): {edit}", file=sys.stderr)


def _set_level(block: dict, level: int) -> None:
    first, *rest = block["content"].strip().splitlines() or [""]
    block["content"] = "\n".join([f"{'#' * level} {_LEVEL_PREFIX.sub('', first)}", *rest])


def apply_edits(pages: list[dict], edits: list[dict]) -> list[dict]:
    """Copy of the pages with the heading edits applied; the input is not modified.

    Invalid edits are skipped with a warning. Raises HeadingFixError if the result
    has no level 1 heading.
    """
    fixed = copy.deepcopy(pages)
    order = _body_blocks(fixed)
    by_position = {(p, b): i for i, (p, b, _) in enumerate(order)}
    removed: set[int] = set()
    absorbed_by: dict[int, int] = {}

    for edit in edits:
        try:
            index = by_position.get((edit["page"], edit["block"]))
            action = edit["action"]
        except (KeyError, TypeError):
            _warn(edit, "malformed")
            continue
        if index is not None and action == "set_level":
            # the model may give the level of a heading already merged into the previous one
            while index in absorbed_by:
                index = absorbed_by[index]
        if index is None or index in removed:
            _warn(edit, "unknown block")
            continue
        block = order[index][2]
        if block["type"] != "title":
            _warn(edit, "not a title")
        elif action == "set_level":
            level = edit.get("level")
            if isinstance(level, int) and not isinstance(level, bool) and 1 <= level <= 6:
                _set_level(block, level)
            else:
                _warn(edit, "level outside 1-6")
        elif action == "demote":
            block["type"] = "text"
            block["content"] = _title_text(block)
        elif action == "merge":
            following = next(
                (i for i in range(index + 1, len(order)) if i not in removed), None
            )
            if following is None or order[following][2]["type"] != "title":
                _warn(edit, "no title to merge with")
                continue
            level = _title_level(block) or 1
            block["content"] = f"{'#' * level} {_title_text(block)} {_title_text(order[following][2])}"
            removed.add(following)
            absorbed_by[following] = index
        else:
            _warn(edit, "unknown action")

    gone = {id(order[i][2]) for i in removed}
    for page in fixed:
        if page.get("blocks"):
            page["blocks"] = [b for b in page["blocks"] if id(b) not in gone]

    if not any(
        b["type"] == "title" and _title_level(b) == 1 for _, _, b in _body_blocks(fixed)
    ):
        raise HeadingFixError("the fixed response has no level 1 heading")
    return fixed


def fix_headings(pages: list[dict], api: MistralApi | None = None) -> list[dict]:
    """Fixed copy of the pages: LLM-proposed heading edits, applied deterministically."""
    return apply_edits(pages, propose_edits(pages, api))
