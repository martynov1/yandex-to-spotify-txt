"""Generate the app icon. Run once; result is committed under assets/.

    python scripts/generate_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

GREEN = "#1ED760"
BLACK = "#000000"
SHADOW = (0, 0, 0, 60)

SIZE = 1024
RADIUS = 240


def _draw_icon(size: int = SIZE) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Squircle background.
    draw.rounded_rectangle((0, 0, size, size), radius=int(RADIUS * size / SIZE), fill=GREEN)

    # Play triangle. For a right-pointing triangle the visual center sits left of
    # the bounding-box center, so we shift the base/apex right until the centroid
    # lands near the icon center.
    s = size
    base_x = s * 0.33
    apex_x = s * 0.83
    top_y = s * 0.20
    bot_y = s * 0.80
    triangle = [(base_x, top_y), (base_x, bot_y), (apex_x, s * 0.5)]
    draw.polygon(triangle, fill=BLACK)

    return img


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "src" / "yandex_to_spotify" / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Master 1024 for macOS .icns / general high-res use.
    master = _draw_icon(1024)
    master.save(out_dir / "icon.png", "PNG")

    # Smaller variants for tk iconphoto (it picks the closest match per-DPI).
    for s in (256, 128, 64, 32):
        _draw_icon(s).save(out_dir / f"icon_{s}.png", "PNG")

    print(f"icons written to {out_dir}")


if __name__ == "__main__":
    main()
