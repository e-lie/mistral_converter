import copy
import json
import os
import re
import sys

from mistralai.client import Mistral

from mistral_converter.content import FOOTNOTE_TYPE, FURNITURE_TYPES

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
marked as headings, and levels may shift from one chapter to the next.

Goal: level 1 is a chapter (its number and title form one heading), levels 2 to 6 are \
sections nested in a chapter.{toc_hint}

Reply with a JSON object {{"edits": [...]}}. Each edit targets a heading by its "page" and \
"block" values and has an "action":
- {{"page": p, "block": b, "action": "set_level", "level": 1-6}}
- {{"page": p, "block": b, "action": "merge"}}: merge the heading with the heading that \
immediately follows it (for example "CHAPITRE PREMIER" and its title); the result keeps the \
level of the first one
- {{"page": p, "block": b, "action": "demote"}}: the heading is not a real heading (running \
title, stray line); turn it into plain text
Only edit what needs fixing. Never rewrite heading text. There must remain at least one \
level 1 heading.
"""
TOC_HINT = " The printed table of contents of the book is given below; follow its structure."
EDGE_PAGES_HINT = (
    " The first and last pages of the book are given below: if something in them looks like "
    "a printed table of contents, follow its structure."
)
EDGE_PAGES = 10
TOC_MIN_LINES = 5
TOC_PAGE_NUMBER_SHARE = 0.5
_TRAILING_PAGE_NUMBER = re.compile(r"(\d{1,4}|[ivxlcdm]{1,8})\s*$", re.IGNORECASE)


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


def looks_like_toc(text: str) -> bool:
    """Several lines, most of them ending with a page number."""
    lines = [line.strip().rstrip("|").strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    numbered = sum(1 for line in lines if _TRAILING_PAGE_NUMBER.search(line))
    return len(lines) >= TOC_MIN_LINES and numbered / len(lines) >= TOC_PAGE_NUMBER_SHARE


def edge_pages_text(pages: list[dict]) -> str:
    """Body text of the first and last pages, to look for a table of contents without a title."""
    indexes = sorted({*range(min(EDGE_PAGES, len(pages))), *range(max(0, len(pages) - EDGE_PAGES), len(pages))})
    return "\n\n".join(
        f"[page {i}]\n" + "\n\n".join(b["content"].strip() for b in pages[i].get("blocks") or [] if _is_body(b))
        for i in indexes
    )


def detect_printed_toc(pages: list[dict]) -> str | None:
    """Text from a table of contents heading up to the next title, size-capped; None if it does not look like one."""
    blocks = _body_blocks(pages)
    for i, (_, _, block) in enumerate(blocks):
        if block["type"] == "title" and PRINTED_TOC_TITLE.search(_title_text(block)):
            parts = []
            for _, _, following in blocks[i + 1 :]:
                if following["type"] == "title":
                    break
                parts.append(following["content"].strip())
            text = "\n".join(parts)
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


def propose_edits(pages: list[dict]) -> list[dict]:
    """Ask the model for heading edits; raise HeadingFixError on failure or invalid answer."""
    toc = detect_printed_toc(pages)
    prompt = PROMPT.format(toc_hint=TOC_HINT if toc else EDGE_PAGES_HINT)
    parts = [prompt, "Headings:", json.dumps(describe_headings(pages), ensure_ascii=False)]
    if toc:
        parts += ["Printed table of contents:", toc]
    else:
        parts += ["First and last pages:", edge_pages_text(pages)]
    try:
        client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
        response = client.chat.complete(
            model=HEADING_FIX_MODEL,
            messages=[{"role": "user", "content": "\n\n".join(parts)}],
            response_format={"type": "json_object"},
        )
        edits = json.loads(response.choices[0].message.content)["edits"]
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


def fix_headings(pages: list[dict]) -> list[dict]:
    """Fixed copy of the pages: LLM-proposed heading edits, applied deterministically."""
    return apply_edits(pages, propose_edits(pages))
