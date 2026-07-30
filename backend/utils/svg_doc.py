"""SVG document parsing, sanitization, sizing, and linting.

An `.svg` media item is a single **self-contained** file: no external references,
no script, no remote fonts. Rasters must be embedded as data URIs. Every ingest
path (agent tool, scanner, upload) runs the text through `sanitize()` before it
becomes a media item.

This is a safety boundary, not just a tidiness pass — imported SVGs come from
anywhere, and the viewer renders them through `<img>` precisely so that a miss
here is not the only thing standing between a hostile file and the app.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from core.logging import get_logger

log = get_logger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Parsing guardrails
MAX_SVG_BYTES = 20 * 1024 * 1024

DEFAULT_SIZE = 512
MIN_DIMENSION = 1
MAX_DIMENSION = 20000

# Elements that can execute or reach outside the document
_FORBIDDEN_TAGS = {"script", "foreignObject", "handler", "audio", "video", "iframe"}

# Animation elements — allowed, but flagged: thumbnails and every export path
# capture a static frame, so an animated SVG will not look the way it does live.
_ANIMATION_TAGS = {"animate", "animateTransform", "animateMotion", "animateColor", "set"}

_HREF_ATTRS = ("href", f"{{{XLINK_NS}}}href")

# url(...) pointing anywhere but this document — a fragment or a data URI is local,
# everything else (absolute, relative, protocol-relative) reaches outside.
_EXTERNAL_URL_RE = re.compile(r"url\(\s*['\"]?\s*(?!#|data:)", re.IGNORECASE)
_EXTERNAL_URL_FULL_RE = re.compile(r"url\(\s*['\"]?\s*(?!#|data:)[^)]*\)", re.IGNORECASE)
_CSS_IMPORT_RE = re.compile(r"@import\b[^;]*;?", re.IGNORECASE)
_KEYFRAMES_RE = re.compile(r"@keyframes\b", re.IGNORECASE)
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>[]*(\[[^\]]*\])?[^>]*>", re.IGNORECASE | re.DOTALL)
_XML_PI_RE = re.compile(r"<\?xml-stylesheet[^>]*\?>", re.IGNORECASE)
_LENGTH_RE = re.compile(r"^\s*([+-]?[\d.]+(?:[eE][+-]?\d+)?)\s*([a-z%]*)\s*$", re.IGNORECASE)

# Absolute unit → px, matching the CSS reference pixel
_UNIT_SCALE = {
    "": 1.0, "px": 1.0, "pt": 96.0 / 72.0, "pc": 16.0,
    "in": 96.0, "cm": 96.0 / 2.54, "mm": 96.0 / 25.4, "q": 96.0 / 101.6,
}


class SvgParseError(ValueError):
    """Raised when SVG text is not well-formed XML or is not an SVG document."""


@dataclass
class SvgDoc:
    root: ET.Element
    width: int
    height: int
    warnings: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def is_animated(self) -> bool:
        return any(w.startswith("Animated") for w in self.warnings)


def _localname(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _parse_length(value: Optional[str]) -> Optional[float]:
    """Parse an SVG length to px. Returns None for percentages and junk."""
    if not value:
        return None
    m = _LENGTH_RE.match(value)
    if not m:
        return None
    try:
        number = float(m.group(1))
    except ValueError:
        return None
    scale = _UNIT_SCALE.get(m.group(2).lower())
    if scale is None:  # % or em/rem/ex — not resolvable without a viewport
        return None
    return number * scale


def _parse_viewbox(value: Optional[str]) -> Optional[tuple[float, float, float, float]]:
    if not value:
        return None
    parts = re.split(r"[\s,]+", value.strip())
    if len(parts) != 4:
        return None
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError:
        return None
    if w <= 0 or h <= 0:
        return None
    return x, y, w, h


def parse_svg(text: str) -> ET.Element:
    """Parse SVG text into an element tree.

    Rejects DOCTYPE declarations outright: they are the entity-expansion attack
    surface, and no legitimate SVG we author or consume needs one.
    """
    if not text or not text.strip():
        raise SvgParseError("SVG is empty")
    if len(text.encode("utf-8", errors="ignore")) > MAX_SVG_BYTES:
        raise SvgParseError(f"SVG exceeds the {MAX_SVG_BYTES // (1024 * 1024)}MB limit")
    if _DOCTYPE_RE.search(text):
        text = _DOCTYPE_RE.sub("", text)

    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        line, col = getattr(e, "position", (0, 0))
        raise SvgParseError(f"SVG is not well-formed XML at line {line}, column {col}: {e}") from e

    if _localname(root.tag) != "svg":
        raise SvgParseError(
            f"Root element is <{_localname(root.tag) or '?'}>, expected <svg>"
        )
    return root


def intrinsic_size(root: ET.Element) -> tuple[int, int]:
    """Resolve the document's nominal pixel size.

    width/height attributes win; viewBox is the fallback; a square default is the
    last resort. Percentage sizes fall through to viewBox, which is why a viewBox
    is normalized onto every document we store.
    """
    w = _parse_length(root.get("width"))
    h = _parse_length(root.get("height"))
    vb = _parse_viewbox(root.get("viewBox"))

    if w is None or h is None:
        if vb:
            vb_w, vb_h = vb[2], vb[3]
            if w is None and h is None:
                w, h = vb_w, vb_h
            elif w is None:
                w = h * (vb_w / vb_h)
            else:
                h = w * (vb_h / vb_w)
        else:
            w = w if w is not None else DEFAULT_SIZE
            h = h if h is not None else DEFAULT_SIZE

    def clamp(v: float) -> int:
        return max(MIN_DIMENSION, min(MAX_DIMENSION, int(round(v)) or MIN_DIMENSION))

    return clamp(w), clamp(h)


def ensure_viewbox(root: ET.Element) -> None:
    """Guarantee a viewBox so the document scales cleanly at any export size."""
    if _parse_viewbox(root.get("viewBox")):
        return
    w, h = intrinsic_size(root)
    root.set("viewBox", f"0 0 {w} {h}")


def _build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _href_is_local(value: str) -> bool:
    """Local = a fragment reference or an embedded data URI. Nothing else."""
    v = value.strip()
    return v.startswith("#") or v.lower().startswith("data:")


def sanitize(root: ET.Element) -> tuple[list[str], list[str]]:
    """Strip everything that can execute or reach outside the document.

    Mutates `root` in place. Returns (removed, warnings).
    """
    removed: list[str] = []
    warnings: list[str] = []
    parents = _build_parent_map(root)

    for el in list(root.iter()):
        tag = _localname(el.tag)

        if tag in _FORBIDDEN_TAGS:
            parent = parents.get(el)
            if parent is not None:
                parent.remove(el)
                removed.append(f"<{tag}> element")
            continue

        if tag in _ANIMATION_TAGS:
            warnings.append(
                "Animated SVG: thumbnails and exports capture a static frame"
            )

        for name, value in list(el.attrib.items()):
            local = _localname(name) if "}" in str(name) else str(name)

            if local.lower().startswith("on"):
                del el.attrib[name]
                removed.append(f"{local} event handler")
                continue

            if name in _HREF_ATTRS and not _href_is_local(value):
                if tag == "image":
                    parent = parents.get(el)
                    if parent is not None:
                        parent.remove(el)
                        removed.append("<image> with an external source")
                    break
                del el.attrib[name]
                removed.append(f"external {local} reference")
                continue

            if "url(" in value and _EXTERNAL_URL_RE.search(value):
                del el.attrib[name]
                removed.append(f"external url() in {local}")
                continue

            if value.strip().lower().startswith("javascript:"):
                del el.attrib[name]
                removed.append(f"javascript: URI in {local}")

        if tag == "style" and el.text:
            css = el.text
            if _CSS_IMPORT_RE.search(css):
                css = _CSS_IMPORT_RE.sub("", css)
                removed.append("@import in <style>")
            if _EXTERNAL_URL_FULL_RE.search(css):
                css = _EXTERNAL_URL_FULL_RE.sub("none", css)
                removed.append("external url() in <style>")
            if _KEYFRAMES_RE.search(css):
                warnings.append(
                    "Animated SVG: thumbnails and exports capture a static frame"
                )
            el.text = css

    # Collapse duplicates while keeping first-seen order
    return list(dict.fromkeys(removed)), list(dict.fromkeys(warnings))


def lint(root: ET.Element) -> list[str]:
    """Report portability problems that sanitize() does not fix.

    These are advisory: the document renders, but may not render the same way
    somewhere else.
    """
    issues: list[str] = []
    fonts_used = set()

    for el in root.iter():
        tag = _localname(el.tag)
        if tag == "text" or tag == "tspan":
            family = el.get("font-family") or ""
            style = el.get("style") or ""
            m = re.search(r"font-family\s*:\s*([^;]+)", style)
            if m:
                family = m.group(1)
            if family:
                fonts_used.add(family.split(",")[0].strip().strip("'\""))
            else:
                fonts_used.add("(inherited)")

    if fonts_used:
        issues.append(
            f"<text> depends on fonts not embedded in the file ({', '.join(sorted(fonts_used))}) — "
            "convert text to paths so it renders identically everywhere"
        )

    return issues


# Ink tone ────────────────────────────────────────────────────────────────────

# Shapes that actually put paint on the canvas. Containers (<g>, <defs>) only
# pass paint down, and anything inside <defs>/<clipPath>/<mask> never paints
# directly.
_PAINTING_TAGS = {
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "use", "image",
}
_NON_PAINTING_CONTAINERS = {"defs", "clipPath", "mask", "symbol", "marker", "pattern"}

# The subset of CSS named colors worth resolving: the ones people actually type
# into an icon. Anything else falls through to "unknown", which lands the
# document in "mixed" — a checkerboard, which is never wrong.
_NAMED_COLORS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
    "orange": (255, 165, 0), "purple": (128, 0, 128), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "silver": (192, 192, 192), "navy": (0, 0, 128),
    "teal": (0, 128, 128), "cyan": (0, 255, 255), "aqua": (0, 255, 255),
    "magenta": (255, 0, 255), "fuchsia": (255, 0, 255), "lime": (0, 255, 0),
    "maroon": (128, 0, 0), "olive": (128, 128, 0), "pink": (255, 192, 203),
    "brown": (165, 42, 42), "gold": (255, 215, 0), "indigo": (75, 0, 130),
}

_RGB_FUNC_RE = re.compile(
    r"^rgba?\(\s*([\d.]+%?)[\s,]+([\d.]+%?)[\s,]+([\d.]+%?)", re.IGNORECASE
)


def _parse_color(value: Optional[str]) -> tuple[int, int, int] | None | str:
    """Resolve a paint value to RGB.

    Returns an (r, g, b) tuple, ``None`` when the value paints nothing, or the
    string ``"unknown"`` when it paints something this function cannot reduce to
    a single color (a gradient, a pattern, a CSS variable).

    ``currentColor`` resolves to black: the viewer renders through ``<img>``,
    where the document has no inherited ``color`` and CSS's initial value —
    black — is what the renderer uses. This is not an approximation; it is
    exactly what the person sees.
    """
    if value is None:
        return "unknown"
    v = value.strip().lower()
    if not v or v in ("none", "transparent"):
        return None
    if v in ("currentcolor", "inherit", "initial", "unset"):
        return (0, 0, 0)
    if v.startswith("url(") or v.startswith("var("):
        return "unknown"
    if v.startswith("#"):
        h = v[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h[:3])
        if len(h) in (6, 8):
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except ValueError:
                return "unknown"
        return "unknown"
    m = _RGB_FUNC_RE.match(v)
    if m:
        channels = []
        for part in m.groups():
            try:
                channels.append(
                    int(float(part[:-1]) * 255 / 100) if part.endswith("%") else int(float(part))
                )
            except ValueError:
                return "unknown"
        r, g, b = (max(0, min(255, c)) for c in channels)
        return (r, g, b)
    if v in _NAMED_COLORS:
        return _NAMED_COLORS[v]
    return "unknown"


def _style_declarations(el: ET.Element) -> dict[str, str]:
    style = el.get("style") or ""
    out: dict[str, str] = {}
    for decl in style.split(";"):
        if ":" in decl:
            name, _, val = decl.partition(":")
            out[name.strip().lower()] = val.strip()
    return out


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def ink_tone(root: ET.Element) -> str:
    """Classify the document's paint as ``dark``, ``light``, or ``mixed``.

    This is what lets a viewer pick a ground without asking: a black mark needs
    a light backdrop and a white mark needs a dark one, and getting it wrong
    means showing the person an empty rectangle.

    It reads the declared paint rather than rasterizing — an icon or a logo
    states its colors in a handful of attributes, and a parse costs nothing next
    to a browser round trip. Anything it cannot reduce to flat colors (a
    gradient, a stylesheet rule, an embedded raster) is reported as ``mixed``,
    which draws the checkerboard.
    """
    luminances: list[float] = []
    unknown = False

    def walk(el: ET.Element, fill: Optional[str], stroke: Optional[str]) -> None:
        nonlocal unknown
        tag = _localname(el.tag)
        if tag in _NON_PAINTING_CONTAINERS:
            return

        decls = _style_declarations(el)
        own_fill = decls.get("fill", el.get("fill"))
        own_stroke = decls.get("stroke", el.get("stroke"))
        eff_fill = own_fill if own_fill is not None else fill
        eff_stroke = own_stroke if own_stroke is not None else stroke

        if tag in _PAINTING_TAGS:
            if tag == "image":
                # An embedded raster can be anything at all.
                unknown = True
            for paint, is_fill in ((eff_fill, True), (eff_stroke, False)):
                # An unspecified fill paints black (the SVG initial value); an
                # unspecified stroke paints nothing.
                if paint is None:
                    if is_fill:
                        luminances.append(0.0)
                    continue
                color = _parse_color(paint)
                if color is None:
                    continue
                if color == "unknown":
                    unknown = True
                    continue
                luminances.append(_relative_luminance(color))

        for child in el:
            walk(child, eff_fill, eff_stroke)

    walk(root, None, None)

    if unknown or not luminances:
        return "mixed"
    if max(luminances) < 0.4:
        return "dark"
    if min(luminances) > 0.6:
        return "light"
    return "mixed"


def serialize(root: ET.Element) -> str:
    """Serialize back to SVG text with clean namespace prefixes.

    No XML declaration: the stored file doubles as the inline-embed payload, and
    a declaration is invalid mid-HTML.
    """
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    if not root.get("xmlns") and not root.tag.startswith("{"):
        root.set("xmlns", SVG_NS)
    return ET.tostring(root, encoding="unicode")


def prepare(text: str) -> SvgDoc:
    """Full ingest pipeline: parse → sanitize → normalize → size → lint.

    The single entry point every producer of SVG media should call.
    """
    text = _XML_PI_RE.sub("", text)
    root = parse_svg(text)
    removed, warnings = sanitize(root)
    ensure_viewbox(root)
    width, height = intrinsic_size(root)
    warnings = warnings + lint(root)
    return SvgDoc(root=root, width=width, height=height, warnings=warnings, removed=removed)


def prepare_text(text: str) -> tuple[str, SvgDoc]:
    """`prepare()` plus the sanitized text, ready to write to disk."""
    doc = prepare(text)
    return serialize(doc.root), doc


def read_svg_file(path) -> str:
    """Read an .svg file as text, tolerating a BOM."""
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8-sig")
