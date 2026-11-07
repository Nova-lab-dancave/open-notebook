"""Infographics: one static SVG poster written by the chat model from a notebook.

Styles and layouts are adapted from the ``baoyu-infographic`` skill in
JimLiu/baoyu-skills (MIT licence, (c) Jim Liu), rewritten for vector output:
that skill drives a raster image model, here the chat model draws SVG.

Safety model (ADR-016):

- :func:`sanitize_svg` parses the reply with ``defusedxml`` (no DTDs or
  entities) and rebuilds it from an allow-list: drawing, text, gradient,
  pattern and filter elements only. Scripts, ``foreignObject``, links,
  animation, images, event handlers and every reference that is not a local
  ``#fragment`` are dropped. The result can't run code or load anything.
- The app shows it as an ``<img>`` (scripts never run there anyway) and serves
  the file with a ``sandbox`` CSP that blocks everything except inline styles.
- Source text is untrusted: instructions stay in the system message and sources
  are passed only inside delimited data blocks (shared with explainers).

A note whose attachment is ``image/svg+xml`` is an infographic: uploads can't
be SVG (``ALLOWED_TYPES`` in ``note_files``), so only this generator makes them.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from open_notebook.exceptions import IncompleteGenerationError

SVG_MIME = "image/svg+xml"
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Source text budget (chars, shared between sources). An infographic holds far
# less than an explainer, so it needs less input. Override with
# OPEN_NOTEBOOK_INFOGRAPHIC_CONTEXT_CHARS.
DEFAULT_CONTEXT_CHARS = 160_000
# Output budget. A dense poster is ~10-20k tokens of SVG plus any hidden
# reasoning. Override with OPEN_NOTEBOOK_INFOGRAPHIC_MAX_TOKENS.
DEFAULT_MAX_TOKENS = 32_000
MAX_INSTRUCTIONS_CHARS = 2_000
MAX_NOTE_TEXT_CHARS = 20_000

# Served with the file: no scripts, no requests, inline styles only. The
# ``sandbox`` directive also covers someone opening the file URL directly.
INFOGRAPHIC_CSP_HEADER = (
    "sandbox; default-src 'none'; style-src 'unsafe-inline'; "
    "img-src data:; font-src data:"
)


@dataclass(frozen=True)
class Option:
    name: str
    guidance: str


# Visual styles that translate to vector art. baoyu's raster-only looks
# (claymation, LEGO, watercolour, knolling, origami) are left out.
STYLES: Dict[str, Option] = {
    "clean-editorial": Option(
        "Clean editorial",
        "Modern magazine infographic. Off-white background (#FAFAF7), near-black "
        "text (#1A1A1A), one strong accent (deep teal #0F766E) plus one warm "
        "secondary (#E07A2F). Generous whitespace, a strict column grid, thin "
        "rules between modules, large confident numerals for key figures. "
        "Sans-serif headings (bold, tight), clean sans-serif body.",
    ),
    "craft-handmade": Option(
        "Hand-drawn craft",
        "Hand-drawn paper-craft feel. Cream paper background (#FFF8F0) with warm "
        "pastel blocks like cut construction paper, soft offset drop shadows, "
        "slightly irregular shapes (draw with paths that wobble a little, not "
        "perfect rectangles), simple cartoon icons built from basic shapes. "
        "Rounded casual typography; keywords highlighted with marker-style "
        "underlines.",
    ),
    "chalkboard": Option(
        "Chalkboard",
        "Classroom chalkboard. Background #1C2B1C or #1A1A1A with a faint "
        "texture (feTurbulence noise at low opacity). Chalk-white text "
        "(#F5F5F5) and coloured-chalk accents: yellow #FFE566, pink #FF9999, "
        "blue #66B3FF, green #90EE90. Sketchy imperfect strokes, doodled arrows, "
        "underlines, circles and stars. No gradients or gloss.",
    ),
    "technical-schematic": Option(
        "Blueprint",
        "Engineering blueprint. Deep blue background (#1E3A5F) with a fine grid "
        "pattern, white and light-cyan line work, amber highlights (#F59E0B). "
        "Precise geometry, consistent stroke weights, dimension lines, callout "
        "leaders and small technical annotations. ALL-CAPS labels in a clean "
        "sans-serif or monospace.",
    ),
    "subway-map": Option(
        "Transit map",
        "Metro map. White or light grey background. Thick coloured route lines "
        "(red, blue, green, yellow, orange) at 45 and 90 degree angles only, "
        "round station markers with white fill, interchange rings where ideas "
        "connect, route badges with numbers. Clean sans-serif station labels.",
    ),
    "corporate-memphis": Option(
        "Flat vector",
        "Flat corporate illustration. Bright, friendly palette (violet #6C5CE7, "
        "coral #FF7675, yellow #FDCB6E, teal #00B894) on white. Flat shapes with "
        "no outlines, simple geometric people and objects, playful blobs and "
        "confetti shapes in the background. Bold rounded sans-serif headings.",
    ),
    "cyberpunk-neon": Option(
        "Neon",
        "Cyberpunk neon. Near-black background (#0B0B1A) with a faint grid. "
        "Glowing magenta (#FF2BD6), cyan (#00F0FF) and acid-yellow (#E6FF00) "
        "lines and text, glow via feGaussianBlur merged under the shape. "
        "Angular panels with cut corners, HUD-style brackets and scan lines. "
        "Monospace or condensed sans-serif labels.",
    ),
    "aged-academia": Option(
        "Vintage academic",
        "Victorian science plate. Sepia parchment background (#F2E6CF) with a "
        "subtle texture, ink-brown line work (#3E2C1C), muted red and "
        "olive-green accents. Fine hatching, ornamental rules and corner "
        "flourishes, numbered figure captions. Serif typography with small caps.",
    ),
    "kawaii": Option(
        "Kawaii",
        "Japanese cute. Soft pastel palette (pink #FFC8DD, lavender #CDB4DB, mint "
        "#BDE0FE, butter #FFF3B0) on a light background. Rounded bubbly shapes, "
        "small smiling faces on icons, sparkles and hearts as decoration, "
        "thick soft outlines. Round friendly typography.",
    ),
    "pixel-art": Option(
        "Pixel art",
        "Retro 8-bit game. Everything built from square pixels on an 8px grid "
        "(use rect elements and shape-rendering=crispEdges). Limited bright "
        "palette on a dark navy background, chunky pixel icons, game-style "
        "panels and health-bar meters for numbers. Monospace labels.",
    ),
    "ikea-manual": Option(
        "Instruction manual",
        "Flat-pack assembly manual. White background, black uniform-weight line "
        "art, no colour except one sparing accent. Numbered step circles, simple "
        "stick-figure people, arrows showing motion, minimal words.",
    ),
    "bold-graphic": Option(
        "Comic pop",
        "Comic-book pop art. Thick black outlines, primary colours (red #E63946, "
        "yellow #FFD60A, blue #1D4ED8), halftone dot patterns, starburst "
        "callouts and speech-bubble labels. Heavy condensed uppercase headings.",
    ),
    "morandi-journal": Option(
        "Journal doodle",
        "Bullet-journal page. Warm off-white background, muted Morandi tones "
        "(dusty rose #C9A9A6, sage #A3B18A, clay #B08968, slate #6B7B8C). "
        "Hand-drawn doodles, washi-tape strips on module corners, dotted "
        "dividers, small handwritten-style annotations.",
    ),
    "ui-wireframe": Option(
        "Wireframe",
        "Greyscale UI wireframe. Light grey background, white cards with 1px "
        "grey borders, placeholder-style boxes and crossed image frames, one "
        "blue accent for emphasis. Clean system sans-serif, small uppercase "
        "section labels.",
    ),
}
DEFAULT_STYLE = "clean-editorial"

# Information structures. "auto" lets the model pick from the material.
LAYOUTS: Dict[str, Option] = {
    "auto": Option(
        "Best fit",
        "Choose the layout below that best fits the material (bento grid when "
        "unsure) and follow it.",
    ),
    "bento-grid": Option(
        "Bento grid",
        "A grid of rectangular modules of mixed sizes. The most important idea "
        "gets the largest tile; each tile holds one idea with a heading, an "
        "icon or mini-chart and a line or two of text.",
    ),
    "linear-progression": Option(
        "Timeline / steps",
        "A single path of numbered steps or dated events running top to bottom "
        "(portrait) or left to right (landscape), with markers on the line and "
        "a short label and note at each.",
    ),
    "binary-comparison": Option(
        "A vs B",
        "Two halves side by side (or top and bottom) with contrasting colours, "
        "matching rows so each point lines up against its counterpart, and a "
        "verdict or summary strip at the bottom.",
    ),
    "comparison-matrix": Option(
        "Comparison table",
        "A table: options as columns, criteria as rows, with icons, ratings or "
        "short values in the cells and the strongest cell in each row "
        "highlighted.",
    ),
    "hierarchical-layers": Option(
        "Pyramid / layers",
        "Stacked layers (a pyramid or stack) from foundation to top, each layer "
        "labelled with a short description to the side.",
    ),
    "tree-branching": Option(
        "Tree",
        "A root concept branching into categories and sub-items, with clean "
        "orthogonal or curved connectors and aligned levels.",
    ),
    "hub-spoke": Option(
        "Hub and spoke",
        "A central concept in a prominent hub with 4-8 spokes radiating to "
        "nodes, each node with an icon, a label and a one-line description.",
    ),
    "funnel": Option(
        "Funnel",
        "A funnel narrowing through 3-6 stages, each stage labelled with its "
        "name and figure or description, widest at the top.",
    ),
    "iceberg": Option(
        "Iceberg",
        "An iceberg at a waterline: the visible, obvious points above water, "
        "the larger hidden causes or details below.",
    ),
    "circular-flow": Option(
        "Cycle",
        "4-8 stages arranged in a circle joined by arrows that show the cycle's "
        "direction, with the cycle's name in the centre.",
    ),
    "venn-diagram": Option(
        "Venn diagram",
        "Two or three overlapping translucent circles; what is unique to each "
        "in its own region and what is shared in the overlaps.",
    ),
    "winding-roadmap": Option(
        "Roadmap",
        "A winding road or path with milestone flags along it, from the start "
        "to the goal, each milestone with a short label.",
    ),
    "dashboard": Option(
        "Dashboard",
        "A row of big-number KPI cards at the top, then panels with simple "
        "charts (bars, donuts, sparklines) drawn in SVG from figures in the "
        "sources only.",
    ),
}
DEFAULT_LAYOUT = "auto"

# Canvas sizes (SVG user units) per aspect.
ASPECTS: Dict[str, Tuple[int, int]] = {
    "portrait": (1080, 1920),
    "landscape": (1920, 1080),
    "square": (1440, 1440),
}
DEFAULT_ASPECT = "portrait"


def context_chars() -> int:
    return _int_env("OPEN_NOTEBOOK_INFOGRAPHIC_CONTEXT_CHARS", DEFAULT_CONTEXT_CHARS)


def max_output_tokens() -> int:
    return _int_env("OPEN_NOTEBOOK_INFOGRAPHIC_MAX_TOKENS", DEFAULT_MAX_TOKENS)


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


# --- Extracting the SVG from a model reply -----------------------------------

_FENCE = re.compile(r"```(?:svg|xml|html)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_SVG_START = re.compile(r"<svg[\s>]", re.IGNORECASE)


def extract_svg(text: str) -> str:
    """Pull the ``<svg>…</svg>`` document out of a model reply, or raise.

    A reply that stops before ``</svg>`` was cut off by the output limit and is
    rejected rather than saved half-drawn.
    """
    candidate = (text or "").strip()
    fenced = _FENCE.search(candidate)
    if fenced and _SVG_START.search(fenced.group(1)):
        candidate = fenced.group(1)
    start = _SVG_START.search(candidate)
    if not start:
        raise IncompleteGenerationError(
            "The model did not return an SVG image. Try again, or pick a stronger "
            "default chat model."
        )
    candidate = candidate[start.start() :]
    end = candidate.lower().rfind("</svg>")
    if end == -1:
        raise IncompleteGenerationError(
            "The infographic was cut off before it finished (the model hit its "
            "output limit; hidden reasoning counts towards it). Try again, pick a "
            "simpler layout, or raise OPEN_NOTEBOOK_INFOGRAPHIC_MAX_TOKENS."
        )
    return candidate[: end + len("</svg>")]


# --- Sanitising ---------------------------------------------------------------

_ALLOWED_ELEMENTS = {
    "svg", "g", "defs", "title", "desc", "symbol", "use", "style",
    "rect", "circle", "ellipse", "line", "polyline", "polygon", "path",
    "text", "tspan", "textPath",
    "linearGradient", "radialGradient", "stop", "pattern", "clipPath", "mask",
    "marker", "filter",
    "feBlend", "feColorMatrix", "feComponentTransfer", "feComposite",
    "feDisplacementMap", "feDropShadow", "feFlood", "feFuncA", "feFuncB",
    "feFuncG", "feFuncR", "feGaussianBlur", "feMerge", "feMergeNode",
    "feMorphology", "feOffset", "feTurbulence",
}  # fmt: skip

# Any url(...) that is not a local fragment reference.
_REMOTE_URL = re.compile(r"url\(\s*(?![\"']?#)", re.IGNORECASE)
_CSS_DANGER = re.compile(r"@import|expression\s*\(|javascript:|behavior\s*:", re.I)
_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_DOCTYPE = re.compile(r"<!DOCTYPE[^\[>]*(?:\[.*?\])?\s*>", re.IGNORECASE | re.DOTALL)
_BARE_AMP = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]*;)")
_NAMED_ENTITY = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}
_NUMBER = re.compile(r"^\s*([0-9.]+)")


def sanitize_svg(svg: str, aspect: str = DEFAULT_ASPECT) -> str:
    """Parse model-written SVG safely and rebuild it from an allow-list.

    Raises :class:`IncompleteGenerationError` if it isn't well-formed SVG.
    Ensures ``viewBox``, ``width`` and ``height`` are set (an ``<img>`` and the
    PNG export need an intrinsic size).
    """
    text = _XML_DECL.sub("", svg)
    text = _DOCTYPE.sub("", text)
    text = _NAMED_ENTITY.sub(_entity_to_char, text)  # &nbsp; etc. aren't XML
    text = _BARE_AMP.sub("&amp;", text)
    try:
        root = SafeET.fromstring(text)
    except (ET.ParseError, DefusedXmlException) as e:
        raise IncompleteGenerationError(
            "The model returned a broken SVG image. Try again, or pick a stronger "
            "default chat model."
        ) from e
    if _local(root.tag) != "svg":
        raise IncompleteGenerationError("The model did not return an SVG image.")

    clean = _clean(root)
    assert clean is not None
    _ensure_size(clean, aspect)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return ET.tostring(clean, encoding="unicode")


def _entity_to_char(match: re.Match) -> str:
    name = match.group(1)
    if name in _XML_ENTITIES:
        return match.group(0)
    char = html.unescape(f"&{name};")
    if char == f"&{name};":
        return f"&amp;{name};"  # unknown entity: keep it as visible text
    return html.escape(char, quote=False)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _clean(el: ET.Element) -> Optional[ET.Element]:
    name = _local(el.tag)
    if name not in _ALLOWED_ELEMENTS:
        return None
    out = ET.Element(f"{{{SVG_NS}}}{name}")
    for key, value in el.attrib.items():
        attr = _safe_attr(key, value)
        if attr:
            out.set(*attr)
    if name == "style":
        css = el.text or ""
        out.text = "" if _CSS_DANGER.search(css) or _REMOTE_URL.search(css) else css
        return out
    out.text = el.text
    for child in el:
        kept = _clean(child)
        if kept is not None:
            kept.tail = child.tail
            out.append(kept)
        elif child.tail:
            # Keep text that followed a dropped element.
            if len(out):
                out[-1].tail = (out[-1].tail or "") + child.tail
            else:
                out.text = (out.text or "") + child.tail
    return out


def _safe_attr(key: str, value: str) -> Optional[Tuple[str, str]]:
    ns = key[1:].split("}", 1)[0] if key.startswith("{") else ""
    name = _local(key)
    lowered = name.lower()
    if ns and ns not in (SVG_NS, XLINK_NS):
        return None  # foreign namespaces (sodipodi, inkscape, xml:base, …)
    if lowered.startswith("on"):
        return None
    if lowered == "href":
        # Local references only (<use href="#icon">, gradients, textPath).
        if not value.strip().startswith("#"):
            return None
        return (f"{{{XLINK_NS}}}href" if ns == XLINK_NS else "href", value)
    if _REMOTE_URL.search(value) or "javascript:" in value.lower():
        return None
    if lowered == "style" and _CSS_DANGER.search(value):
        return None
    return (name, value)


def _ensure_size(root: ET.Element, aspect: str) -> None:
    width, height = ASPECTS.get(aspect, ASPECTS[DEFAULT_ASPECT])
    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) == 4:
        try:
            width, height = int(float(box[2])), int(float(box[3]))
        except ValueError:
            box = []
    if len(box) != 4 or width <= 0 or height <= 0:
        width, height = ASPECTS.get(aspect, ASPECTS[DEFAULT_ASPECT])
        root.set("viewBox", f"0 0 {width} {height}")
    for attr, size in (("width", width), ("height", height)):
        match = _NUMBER.match(root.get(attr) or "")
        if not match or (root.get(attr) or "").strip().endswith("%"):
            root.set(attr, str(size))


# --- Reading it back ----------------------------------------------------------


def svg_title(svg: str) -> str:
    """Text of the root ``<title>``, if any."""
    root = SafeET.fromstring(svg)
    for child in root:
        if _local(child.tag) == "title":
            return " ".join(" ".join(child.itertext()).split())
    return ""


def svg_text(svg: str) -> str:
    """The poster's words, one text element per line, for the note body
    (search, embeddings, chat context)."""
    root = SafeET.fromstring(svg)
    lines: List[str] = []
    for el in root.iter():
        name = _local(el.tag)
        if name not in ("title", "desc", "text"):
            continue
        # Each <tspan> is usually its own visual line: keep a space between them.
        line = " ".join(" ".join(el.itertext()).split())
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return "\n".join(lines)[:MAX_NOTE_TEXT_CHARS]
