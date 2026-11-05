"""Interactive HTML explainers: context building, output checks, hardening.

An explainer is one self-contained HTML page written by the chat model from a
notebook's sources. It is stored as a note attachment (see migration 103) and
flagged ``explainer`` (migration 104) so the viewer may run its scripts.

Safety model (ADR-015):

- The page is shown in an iframe sandboxed with ``allow-scripts`` only, so it
  runs in an opaque origin and can never read the app's token or call the API.
- :func:`harden_html` injects a Content-Security-Policy that blocks subresource
  requests (remote scripts, styles, fonts, images, fetch, XHR, beacons,
  websockets, form posts). CSPs combine restrictively, so a policy the model
  writes itself cannot loosen it. It also strips resource hints and
  ``<meta http-equiv=refresh>`` (defence in depth; CSP doesn't cover hints).
- Navigating the frame itself to an outside URL is not covered by the frame's
  CSP; the app's own ``frame-src`` policy (``frontend/next.config.ts``) blocks it.
- The same policy is sent as a header when the file is served.

Source text is untrusted: the prompt keeps instructions in the system message
and passes sources only inside delimited data blocks.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from typing import List, Sequence, Tuple

from open_notebook.exceptions import IncompleteGenerationError, InvalidInputError

# Total characters of source text sent to the model (roughly 4 chars/token, so
# ~60k tokens), shared evenly between sources. Override with
# OPEN_NOTEBOOK_EXPLAINER_CONTEXT_CHARS.
DEFAULT_CONTEXT_CHARS = 240_000
MIN_PER_SOURCE_CHARS = 2_000
# Output budget for the HTML page. Override with OPEN_NOTEBOOK_EXPLAINER_MAX_TOKENS
# (lower it for models with a small output limit).
DEFAULT_MAX_TOKENS = 16_000
MAX_INSTRUCTIONS_CHARS = 2_000
# The note's text content (used for search, embeddings and chat context).
MAX_NOTE_TEXT_CHARS = 50_000

TRUNCATION_NOTICE = "\n\n[Source truncated to fit the explainer context budget.]"

EXPLAINER_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; font-src data:; media-src data:; connect-src 'none'; "
    "form-action 'none'; base-uri 'none'"
)
# Header form: also sandbox the page when the file URL is opened directly.
EXPLAINER_CSP_HEADER = f"sandbox allow-scripts; {EXPLAINER_CSP}"

_CSP_META = f'<meta http-equiv="Content-Security-Policy" content="{EXPLAINER_CSP}">'

_FENCE = re.compile(r"```(?:html)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_DOC_START = re.compile(r"<!doctype\s+html|<html[\s>]", re.IGNORECASE)
_HEAD_OPEN = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)
_HTML_OPEN = re.compile(r"<html(\s[^>]*)?>", re.IGNORECASE)
_RESOURCE_HINT = re.compile(
    r"<link\b[^>]*\brel\s*=\s*[\"']?[^\"'>]*"
    r"\b(?:preconnect|dns-prefetch|prefetch|prerender|modulepreload|preload)\b[^>]*>",
    re.IGNORECASE,
)
_META_REFRESH = re.compile(
    r"<meta\b[^>]*\bhttp-equiv\s*=\s*[\"']?\s*refresh\b[^>]*>", re.IGNORECASE
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n\s*\n+")


def context_chars() -> int:
    return _int_env("OPEN_NOTEBOOK_EXPLAINER_CONTEXT_CHARS", DEFAULT_CONTEXT_CHARS)


def max_output_tokens() -> int:
    return _int_env("OPEN_NOTEBOOK_EXPLAINER_MAX_TOKENS", DEFAULT_MAX_TOKENS)


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


def build_sources_block(
    sources: Sequence[Tuple[str, str, str]], budget_chars: int
) -> str:
    """Render ``(id, title, text)`` sources as delimited data blocks.

    Sources without text are skipped. The budget is shared evenly; a source
    that needs less than its share leaves the rest to the others.
    """
    usable = [(sid, title, text.strip()) for sid, title, text in sources if text]
    usable = [s for s in usable if s[2]]
    if not usable:
        raise InvalidInputError(
            "This notebook has no source text yet. Add sources (and wait for them "
            "to finish processing) before generating an explainer."
        )

    # Hand out the budget smallest-first so short sources don't waste it.
    remaining = max(budget_chars, MIN_PER_SOURCE_CHARS * len(usable))
    limits = {}
    order = sorted(range(len(usable)), key=lambda i: len(usable[i][2]))
    for pos, i in enumerate(order):
        share = remaining // (len(usable) - pos)
        take = min(len(usable[i][2]), max(share, MIN_PER_SOURCE_CHARS))
        limits[i] = take
        remaining -= take

    parts: List[str] = []
    for i, (sid, title, text) in enumerate(usable, start=0):
        body = text
        if len(body) > limits[i]:
            body = body[: limits[i]].rstrip() + TRUNCATION_NOTICE
        parts.append(
            f'<source n="{i + 1}" id="{_attr(sid)}" title="{_attr(title)}">\n'
            f"{body}\n</source>"
        )
    return "\n\n".join(parts)


def _attr(value: str) -> str:
    return (
        (value or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    )


def extract_html(text: str) -> str:
    """Pull the HTML document out of a model reply, or raise.

    Accepts a bare document or one wrapped in a code fence (with or without
    chatter around it). A reply that stops before ``</html>`` was cut off by the
    output limit and is rejected rather than saved half-finished.
    """
    candidate = (text or "").strip()
    fenced = _FENCE.search(candidate)
    if fenced and _DOC_START.search(fenced.group(1)):
        candidate = fenced.group(1).strip()
    else:
        # Unterminated fence (reply cut off) or prose before the document.
        candidate = re.sub(r"^```(?:html)?\s*\n", "", candidate, flags=re.IGNORECASE)

    start = _DOC_START.search(candidate)
    if not start:
        raise IncompleteGenerationError(
            "The model did not return an HTML document. Try again, or pick a "
            "stronger default chat model."
        )
    candidate = candidate[start.start() :]
    end = candidate.lower().rfind("</html>")
    if end == -1:
        raise IncompleteGenerationError(
            "The explainer was cut off before it finished (the model hit its output "
            "limit). Try again with fewer or shorter sources, a model with a larger "
            "output limit, or raise OPEN_NOTEBOOK_EXPLAINER_MAX_TOKENS."
        )
    return candidate[: end + len("</html>")]


def harden_html(html: str) -> str:
    """Strip resource hints and refresh redirects, then insert the no-network
    CSP as the first element of ``<head>``.

    CSP does not govern ``<link rel=preconnect|dns-prefetch>`` (a hint can leak a
    hostname) or every navigation, so those tags are removed. This is regex on
    model output: defence in depth only. Navigation away from the frame is
    blocked by the app's ``frame-src`` policy (ADR-015).
    """
    html = _RESOURCE_HINT.sub("", html)
    html = _META_REFRESH.sub("", html)
    head = _HEAD_OPEN.search(html)
    if head:
        return html[: head.end()] + _CSP_META + html[head.end() :]
    root = _HTML_OPEN.search(html)
    if root:
        return html[: root.end()] + f"<head>{_CSP_META}</head>" + html[root.end() :]
    return f"<head>{_CSP_META}</head>" + html


def html_title(html: str) -> str:
    match = _TITLE.search(html)
    if not match:
        return ""
    return _WS.sub(" ", _TextExtractor.run(match.group(1))).strip()


def html_to_text(html: str) -> str:
    """Readable text of the page (scripts and styles dropped) for the note body."""
    text = _TextExtractor.run(html)
    text = "\n".join(_WS.sub(" ", line).strip() for line in text.splitlines())
    text = _BLANKS.sub("\n\n", text).strip()
    return text[:MAX_NOTE_TEXT_CHARS]


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "template", "noscript", "svg", "head"}
    _BLOCK = {
        "p", "div", "section", "article", "header", "footer", "li", "tr", "br",
        "h1", "h2", "h3", "h4", "h5", "h6", "details", "summary", "dt", "dd",
        "table", "ul", "ol", "blockquote", "pre", "figure", "figcaption",
    }  # fmt: skip

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    @classmethod
    def run(cls, html: str) -> str:
        parser = cls()
        parser.feed(html)
        parser.close()
        return "".join(parser.parts)

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)
