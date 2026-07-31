#!/usr/bin/env python3
"""
Generate app icons with optional channel badge overlay.

Usage:
    python scripts/generate-icons.py                    # No badge (production)
    python scripts/generate-icons.py --channel canary   # Purple "CANARY" badge
    python scripts/generate-icons.py --channel beta     # Blue "BETA" badge
    python scripts/generate-icons.py --channel debug    # Red "DEBUG" badge

Writes into src-tauri/icons/ by default, which is committed and must stay at the
production icon so a plain `cargo tauri build` works from a fresh clone. Local
badged builds pass --out to write into an ignored directory instead; see the
`stimma` CLI, which generates and points Tauri at them via a --config override.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
ICONS_DIR = REPO_ROOT / "src-tauri" / "icons"
BASE_ICON = ICONS_DIR / "icon-base.png"
MACOS_BASE_ICON = ICONS_DIR / "icon-macos-base.png"  # HIG-compliant 1024x1024 with squircle + padding

# macOS 26 (Tahoe) Liquid Glass icon source. Compiled by actool into Assets.car,
# which the system prefers over icon.icns whenever CFBundleIconName is set.
# icon.icns remains the icon on macOS 15 and earlier.
ICON_COMPOSER_DOC = ICONS_DIR / "Stimma.icon"
# Name actool registers the icon under; must match CFBundleIconName in Info.plist.
APP_ICON_NAME = "Stimma"

# One colour per separately-installable channel, so a glance at the Dock says
# which build you're looking at.
CHANNEL_BADGES = {
    "canary": {"color": (168, 85, 247), "label": "CANARY"},  # Purple
    "beta":   {"color": (59, 130, 246),  "label": "BETA"},    # Blue
    "debug":  {"color": (220, 38, 38),   "label": "DEBUG"},   # Red
}

# All output sizes needed by Tauri
PNG_OUTPUTS = {
    "icon.png": None,           # Same as source
    "32x32.png": (32, 32),
    "128x128.png": (128, 128),
    "128x128@2x.png": (256, 256),
    "Square30x30Logo.png": (30, 30),
    "Square44x44Logo.png": (44, 44),
    "Square71x71Logo.png": (71, 71),
    "Square89x89Logo.png": (89, 89),
    "Square107x107Logo.png": (107, 107),
    "Square142x142Logo.png": (142, 142),
    "Square150x150Logo.png": (150, 150),
    "Square284x284Logo.png": (284, 284),
    "Square310x310Logo.png": (310, 310),
    "StoreLogo.png": (50, 50),
}

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a bold font at the given size, with platform fallbacks."""
    for path in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def add_badge(img: Image.Image, channel: str) -> Image.Image:
    """Composite a channel badge onto the bottom of the icon.

    For HIG icons (with padding/squircle), the badge is positioned within the
    visible content area, not at the absolute canvas edge.
    """
    badge_info = CHANNEL_BADGES.get(channel)
    if not badge_info:
        return img

    img = img.copy()
    _draw_badge(img, channel, inset_frac=0.10)
    return img


def render_badge_layer(channel: str, size: int = 1024) -> Image.Image:
    """Render the channel badge alone on a transparent canvas.

    Used as a standalone layer in the Icon Composer document, where the squircle
    and its padding are drawn by the system rather than baked into the artwork.
    """
    # Smaller than the legacy badge: here the canvas is the full squircle rather
    # than the ~80% content box, so the same fraction would read much larger.
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    _draw_badge(img, channel, inset_frac=0.10, font_frac=0.068)
    return img


def _draw_badge(img: Image.Image, channel: str, inset_frac: float, font_frac: float = 0.09) -> None:
    """Draw the channel badge in-place, centered `inset_frac` up from the bottom."""
    badge_info = CHANNEL_BADGES[channel]

    draw = ImageDraw.Draw(img)
    w, h = img.size

    label = badge_info["label"]
    bg_color = badge_info["color"]

    # Scale badge relative to icon size
    font_size = max(int(h * font_frac), 12)
    font = _get_font(font_size)

    # Measure text
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Badge dimensions with padding
    pad_x = int(text_w * 0.4)
    pad_y = int(text_h * 0.25)
    badge_w = text_w + pad_x * 2
    badge_h = text_h + pad_y * 2

    # Position: bottom-center of the visible icon area
    inset = int(h * inset_frac)
    bx = (w - badge_w) // 2
    by = h - inset - badge_h - int(h * 0.02)

    # Draw rounded rectangle badge
    badge_rect = [bx, by, bx + badge_w, by + badge_h]
    radius = int(badge_h * 0.3)

    # Draw badge background with dark border for contrast
    border = max(int(h * 0.005), 1)
    draw.rounded_rectangle(
        [badge_rect[0] - border, badge_rect[1] - border,
         badge_rect[2] + border, badge_rect[3] + border],
        radius=radius + border,
        fill=(0, 0, 0, 180),
    )
    draw.rounded_rectangle(badge_rect, radius=radius, fill=(*bg_color, 255))

    # Draw text centered in badge
    text_x = bx + (badge_w - text_w) // 2
    text_y = by + (badge_h - text_h) // 2 - bbox[1]  # Adjust for font baseline
    draw.text((text_x, text_y), label, fill=(255, 255, 255, 255), font=font)


def generate_icns(source_img: Image.Image, output_path: Path) -> None:
    """Generate .icns file. Uses iconutil on macOS, falls back to Pillow save."""
    if platform.system() == "Darwin" and shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmpdir:
            iconset = Path(tmpdir) / "icon.iconset"
            iconset.mkdir()

            # iconutil requires specific filenames and sizes
            icon_sizes = [
                ("icon_16x16.png", 16),
                ("icon_16x16@2x.png", 32),
                ("icon_32x32.png", 32),
                ("icon_32x32@2x.png", 64),
                ("icon_128x128.png", 128),
                ("icon_128x128@2x.png", 256),
                ("icon_256x256.png", 256),
                ("icon_256x256@2x.png", 512),
                ("icon_512x512.png", 512),
                ("icon_512x512@2x.png", 1024),
            ]

            for name, size in icon_sizes:
                resized = source_img.resize((size, size), Image.LANCZOS)
                resized.save(iconset / name, "PNG")

            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset), "-o", str(output_path)],
                check=True,
                capture_output=True,
            )
    else:
        # Fallback: save as PNG with .icns extension (not ideal but functional)
        source_img.save(output_path, "PNG")


def generate_ico(source_img: Image.Image, output_path: Path) -> None:
    """Generate .ico file with multiple resolutions."""
    sizes = [(s, s) for s in ICO_SIZES]
    imgs = [source_img.resize(s, Image.LANCZOS) for s in sizes]
    # Use the largest image as the base — PIL's ICO encoder uses the base
    # image size to filter, so starting from 16x16 drops all larger sizes.
    imgs[-1].save(output_path, format="ICO", append_images=imgs[:-1])


def generate_assets_car(channel: str, output_path: Path) -> bool:
    """Compile the Icon Composer document into Assets.car for macOS 26 (Tahoe).

    Returns True if Assets.car was written. Compiling needs actool from Xcode 26
    on macOS; elsewhere the existing Assets.car (if any) is left untouched.
    """
    if not ICON_COMPOSER_DOC.exists():
        print(f"Warning: {ICON_COMPOSER_DOC.name} not found — skipping Assets.car")
        return False

    if platform.system() != "Darwin" or not shutil.which("xcrun"):
        print("Skipping Assets.car (not macOS)")
        return False

    # icon.svg is the canonical mark; keep the document's copy in step with it so
    # editing the document in Icon Composer never diverges from the other outputs.
    source_svg = ICONS_DIR / "icon.svg"
    if source_svg.exists():
        shutil.copy2(source_svg, ICON_COMPOSER_DOC / "Assets" / "pinwheel.svg")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        doc = tmp / ICON_COMPOSER_DOC.name
        shutil.copytree(ICON_COMPOSER_DOC, doc)

        # The badge rides in its own group so the glass/shadow treatment applied
        # to the logo doesn't smear the label text.
        if channel in CHANNEL_BADGES:
            render_badge_layer(channel).save(doc / "Assets" / "badge.png", "PNG")
            spec = json.loads((doc / "icon.json").read_text())
            spec["groups"].append({
                "layers": [{"image-name": "badge.png", "name": "Channel badge"}],
                "shadow": {"kind": "neutral", "opacity": 0.0},
                "translucency": {"enabled": False, "value": 0.5},
            })
            (doc / "icon.json").write_text(json.dumps(spec, indent=2))

        compiled = tmp / "compiled"
        compiled.mkdir()
        result = subprocess.run(
            [
                "xcrun", "actool", str(doc),
                "--compile", str(compiled),
                "--output-format", "human-readable-text",
                "--notices", "--warnings", "--errors",
                "--output-partial-info-plist", str(tmp / "partial.plist"),
                "--app-icon", APP_ICON_NAME,
                "--include-all-app-icons",
                "--development-region", "en",
                "--target-device", "mac",
                "--minimum-deployment-target", "26.0",
                "--platform", "macosx",
            ],
            capture_output=True,
            text=True,
        )

        car = compiled / "Assets.car"
        if result.returncode != 0 or not car.exists():
            print("Warning: actool failed — Assets.car not regenerated.")
            print((result.stderr or result.stdout).strip()[:2000])
            return False

        # actool also emits a legacy .icns here, but it only carries 16pt and
        # 128pt renditions. generate_icns() keeps producing the full-size one.
        shutil.copy2(car, output_path)
        return True


def main():
    parser = argparse.ArgumentParser(description="Generate app icons with optional channel badge")
    parser.add_argument("--channel", default="production",
                        help="Release channel: production (no badge), canary, beta, debug")
    parser.add_argument("--out", type=Path, default=ICONS_DIR,
                        help="Directory to write generated icons into (default: src-tauri/icons)")
    args = parser.parse_args()

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not BASE_ICON.exists():
        print(f"Error: Base icon not found at {BASE_ICON}")
        raise SystemExit(1)

    # Load base icons
    base = Image.open(BASE_ICON).convert("RGBA")
    print(f"Base icon: {base.size[0]}x{base.size[1]}")

    # Use HIG-compliant base for macOS (squircle + white bg + proper padding)
    if MACOS_BASE_ICON.exists():
        macos_base = Image.open(MACOS_BASE_ICON).convert("RGBA")
        print(f"macOS HIG base: {macos_base.size[0]}x{macos_base.size[1]}")
    else:
        print(f"Warning: macOS HIG base not found at {MACOS_BASE_ICON}, using raw base")
        macos_base = base

    # Apply badge if needed
    if args.channel in CHANNEL_BADGES:
        macos_icon = add_badge(macos_base, args.channel)
        win_icon = add_badge(base, args.channel)
        print(f"Applied {args.channel} badge ({CHANNEL_BADGES[args.channel]['label']})")
    else:
        macos_icon = macos_base
        win_icon = base
        print("No badge (production)")

    # Generate PNG outputs (used by Tauri for various platforms)
    for filename, size in PNG_OUTPUTS.items():
        output = out_dir / filename
        # Use raw base for Windows Store logos, HIG base for general PNGs
        is_windows = filename.startswith("Square") or filename == "StoreLogo.png"
        src = win_icon if is_windows else macos_icon
        if size:
            resized = src.resize(size, Image.LANCZOS)
        else:
            resized = src
        resized.save(output, "PNG")
        sz = size or src.size
        print(f"  {filename} ({sz[0]}x{sz[1]})")

    # Generate ICO (Windows — use raw base)
    generate_ico(win_icon, out_dir / "icon.ico")
    print(f"  icon.ico ({len(ICO_SIZES)} sizes)")

    # Generate ICNS (macOS 15 and earlier — use HIG base)
    generate_icns(macos_icon, out_dir / "icon.icns")
    print(f"  icon.icns")

    # Generate Assets.car (macOS 26+ Liquid Glass icon)
    if generate_assets_car(args.channel, out_dir / "Assets.car"):
        print(f"  Assets.car")

    print("Done.")


if __name__ == "__main__":
    main()
