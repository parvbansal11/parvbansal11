"""Extend the Vision cutout with a region it refuses to call foreground.

VNGenerateForegroundInstanceMaskRequest returns people, not the objects they are
touching, so a laptop in the near foreground gets matted out with the room. This
adds it back as a half-plane bounded by a straight edge you measure once.

    python scripts/matte.py assets/source.jpg assets/me.png -o assets/me-full.png \
        --keep-right-of 1178,0,1047,940 --drop-bright
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def above_line(shape, x0, y0, x1, y1):
    """True above the line through the two points, only right of x0."""
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w]
    if x1 == x0:
        return np.zeros((h, w), bool)
    edge = y0 + (y1 - y0) * (xs - x0) / (x1 - x0)
    return (ys < edge) & (xs >= x0)


def line_mask(shape, x0, y0, x1, y1):
    """True on the right-hand side of the line through the two points."""
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w]
    if y1 == y0:
        return xs >= x0
    edge = x0 + (x1 - x0) * (ys - y0) / (y1 - y0)
    return xs >= edge


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("cutout", help="RGBA png from scripts/cutout.swift")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--keep-right-of", required=True, metavar="x0,y0,x1,y1")
    ap.add_argument("--drop-above", metavar="x0,y0,x1,y1",
                    help="cut everything above this line, right of x0")
    ap.add_argument("--drop-bright", action="store_true",
                    help="strip blown-out sky or window inside the kept region")
    ap.add_argument("--bright-rows", type=int, default=120,
                    help="only look for that brightness in the top N rows")
    ap.add_argument("--no-trim", action="store_true")
    args = ap.parse_args()

    src = Image.open(args.source).convert("RGB")
    w, h = src.size
    rgb = np.asarray(src, dtype=np.float32) / 255.0

    cut = Image.open(args.cutout).convert("RGBA")
    if cut.size != (w, h):
        cut = cut.resize((w, h), Image.LANCZOS)
    person = np.asarray(cut.getchannel("A"), dtype=np.float32) / 255.0

    x0, y0, x1, y1 = (float(v) for v in args.keep_right_of.split(","))
    keep = line_mask((h, w), x0, y0, x1, y1)

    if args.drop_above:
        ax0, ay0, ax1, ay1 = (float(v) for v in args.drop_above.split(","))
        keep &= ~above_line((h, w), ax0, ay0, ax1, ay1)

    if args.drop_bright:
        # The window above the laptop is the one bright, saturated thing inside
        # the half-plane; everything else there is lid in shadow.
        mx, mn = rgb.max(2), rgb.min(2)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
        window = (mx > 0.58) & (sat > 0.22)
        window[args.bright_rows:] = False
        window = ndimage.binary_closing(window, np.ones((9, 9)))
        keep &= ~window

    mask = np.maximum(person, keep.astype(np.float32))
    solid = mask > 0.1
    solid = ndimage.binary_closing(solid, np.ones((7, 7)))
    solid = ndimage.binary_fill_holes(solid)
    mask = np.where(solid, np.maximum(mask, 1.0), mask)
    # soften the join so the dot grid does not read a hard seam
    mask = ndimage.gaussian_filter(mask, 1.2)

    out = np.dstack([rgb, np.clip(mask, 0, 1)[..., None]])
    img = Image.fromarray((out * 255).astype(np.uint8), "RGBA")

    if not args.no_trim:
        box = img.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
        if box:
            img = img.crop(box)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(f"{args.out}  {img.size[0]}x{img.size[1]}  coverage {solid.mean():.3f}")


if __name__ == "__main__":
    main()
