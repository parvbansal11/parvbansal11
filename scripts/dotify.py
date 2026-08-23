"""Turn a photo into a dot-matrix SVG portrait.

Dot size tracks local darkness, dot colour is sampled from the photo, and the
background stays transparent so a single file serves both GitHub themes.

    python scripts/dotify.py assets/cutout.png -o assets/portrait --cols 104
"""

import argparse
import math
import xml.sax.saxutils as esc
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def load(path, crop):
    img = Image.open(path).convert("RGBA")
    if crop:
        x0, y0, x1, y1 = crop
        w, h = img.size
        img = img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    return img


def sample(img, cols, cell_aspect):
    """Average the image down to one RGBA sample per grid cell."""
    w, h = img.size
    rows = max(1, round(cols * (h / w) / cell_aspect))
    small = img.resize((cols, rows), Image.LANCZOS)
    return np.asarray(small, dtype=np.float32) / 255.0, rows


def luminance(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def equalize(values, mask):
    """Flatten the histogram over the visible pixels only."""
    visible = values[mask]
    if visible.size < 8:
        return values
    ranks = np.argsort(np.argsort(visible)).astype(np.float32)
    out = values.copy()
    out[mask] = ranks / max(1.0, ranks.max())
    return out


def build(img, cols, cell_aspect, detail, gamma, do_equalize, alpha_floor, bands):
    grid, rows = sample(img, cols, cell_aspect)
    rgb, alpha = grid[..., :3], grid[..., 3]
    visible = alpha > alpha_floor

    lum = luminance(rgb)
    if do_equalize:
        lum = equalize(lum, visible)
    else:
        lo, hi = np.percentile(lum[visible], [2, 98]) if visible.any() else (0.0, 1.0)
        lum = np.clip((lum - lo) / max(1e-6, hi - lo), 0, 1)

    # Dark areas get fat dots, highlights get pinpricks.
    weight = np.power(1.0 - lum, gamma)
    weight = detail + (1.0 - detail) * weight
    radius = 0.5 * np.sqrt(np.clip(weight, 0.0, 1.0)) * np.clip(alpha / 0.85, 0, 1)

    # Lift very dark samples so they still read against a dark page.
    colour = np.clip(rgb * 0.86 + 0.14, 0, 1)
    return radius, colour, alpha, visible, rows


def to_svg(radius, colour, alpha, visible, rows, cols, cell_aspect, bands, sweep):
    step = 10.0
    width = cols * step
    height = rows * step * cell_aspect
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="dot matrix portrait">',
        "<title>portrait</title>",
    ]

    per_band = max(1, math.ceil(rows / bands))
    for band in range(bands):
        y0, y1 = band * per_band, min(rows, (band + 1) * per_band)
        if y0 >= y1:
            continue
        chunk = []
        for y in range(y0, y1):
            cy = (y + 0.5) * step * cell_aspect
            for x in range(cols):
                if not visible[y, x]:
                    continue
                r = radius[y, x] * step
                if r < 0.55:
                    continue
                cx = (x + 0.5) * step
                r8, g8, b8 = (colour[y, x] * 255).astype(int)
                op = min(1.0, float(alpha[y, x]) * 1.15)
                chunk.append(
                    f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.2f}" '
                    f'fill="#{r8:02x}{g8:02x}{b8:02x}"'
                    + (f' opacity="{op:.2f}"' if op < 0.98 else "")
                    + "/>"
                )
        if not chunk:
            continue
        if sweep:
            # SMIL, so it also plays inside an <img> on GitHub.
            reveal = (
                f'<animate attributeName="opacity" values="0;1" dur="0.45s" '
                f'begin="{0.045 * band:.2f}s" fill="freeze"/>'
            )
            parts.append(f'<g opacity="0">{reveal}' + "".join(chunk) + "</g>")
        else:
            parts.append("<g>" + "".join(chunk) + "</g>")

    parts.append("</svg>")
    return "".join(parts)


def parse_crop(text):
    if not text:
        return None
    vals = [float(v) for v in text.split(",")]
    if len(vals) != 4:
        raise argparse.ArgumentTypeError("crop takes x0,y0,x1,y1 as fractions")
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("-o", "--out", default="assets/portrait")
    ap.add_argument("--cols", type=int, default=104)
    ap.add_argument("--aspect", type=float, default=1.0, help="cell height / width")
    ap.add_argument("--detail", type=float, default=0.12, help="floor on dot size")
    ap.add_argument("--gamma", type=float, default=1.15)
    ap.add_argument("--equalize", action="store_true")
    ap.add_argument("--alpha-floor", type=float, default=0.35)
    ap.add_argument("--bands", type=int, default=22)
    ap.add_argument("--sweep", action="store_true",
                    help="staggered reveal; blank in first-frame-only renderers")
    ap.add_argument("--crop", type=parse_crop, default=None)
    args = ap.parse_args()

    img = load(args.image, args.crop)
    radius, colour, alpha, visible, rows = build(
        img, args.cols, args.aspect, args.detail, args.gamma,
        args.equalize, args.alpha_floor, args.bands,
    )
    svg = to_svg(radius, colour, alpha, visible, rows, args.cols,
                 args.aspect, args.bands, args.sweep)

    out = Path(args.out)
    out = out if out.suffix == ".svg" else out.with_suffix(".svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"{out}  {len(svg) / 1024:.0f} KB  {args.cols}x{rows} grid")


if __name__ == "__main__":
    main()
