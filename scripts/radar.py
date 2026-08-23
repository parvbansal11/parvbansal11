"""Two radar charts: a self-rated one and one measured from the repos.

    python scripts/radar.py            # both, both themes
"""

import argparse
import json
import math
import os
from pathlib import Path

from theme import FONT, THEMES, esc

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

WIDTH, HEIGHT = 540, 470
CX, CY = WIDTH / 2, HEIGHT / 2 - 6
R = 132
RINGS = 4


def fade_in(delay, dur=0.5):
    """SMIL fade. Plays under <img>, where CSS keyframes are inert."""
    return (
        f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;0.01;1" '
        f'dur="{dur + delay:.2f}s" begin="0s" fill="freeze"/>'
    )


def polygon(values, radius):
    n = len(values)
    points = []
    for i, v in enumerate(values):
        angle = -math.pi / 2 + 2 * math.pi * i / n
        rr = radius * max(0.02, v)
        points.append((CX + rr * math.cos(angle), CY + rr * math.sin(angle)))
    return points


def path_of(points):
    return " ".join(
        ("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y) in enumerate(points)
    ) + " Z"


def render(axes, theme_name, title, animate=True):
    t = THEMES[theme_name]
    n = len(axes)
    labels = [a["label"] for a in axes]
    values = [max(0.0, min(1.0, a["value"])) for a in axes]

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{esc(title)}">',
        f"<title>{esc(title)}</title>",
        "<defs>",
        f'<linearGradient id="rg{theme_name}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{t["accent"]}"/>'
        f'<stop offset="1" stop-color="{t["accent2"]}"/></linearGradient>',
        "</defs>",
    ]

    web = ['<g>' if not animate else '<g opacity="1">' + fade_in(0.0, 0.6)]
    for ring in range(1, RINGS + 1):
        pts = polygon([ring / RINGS] * n, R)
        web.append(
            f'<path d="{path_of(pts)}" fill="none" stroke="{t["border"]}" stroke-width="1"/>'
        )
    for i in range(n):
        angle = -math.pi / 2 + 2 * math.pi * i / n
        web.append(
            f'<line x1="{CX}" y1="{CY}" x2="{CX + R * math.cos(angle):.1f}" '
            f'y2="{CY + R * math.sin(angle):.1f}" stroke="{t["border"]}" stroke-width="1"/>'
        )
    web.append("</g>")
    out.extend(web)

    pts = polygon(values, R)
    out.append(
        (f'<g opacity="1">{fade_in(0.35, 0.7)}' if animate else '<g>')
        + f'<path d="{path_of(pts)}" fill="url(#rg{theme_name})" '
        f'fill-opacity="0.22" stroke="url(#rg{theme_name})" stroke-width="2" '
        'stroke-linejoin="round"'
        + '/>' 
    )
    for x, y in pts:
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{t["accent"]}"/>')
    out.append("</g>")

    for i, label in enumerate(labels):
        angle = -math.pi / 2 + 2 * math.pi * i / n
        lx = CX + (R + 30) * math.cos(angle)
        ly = CY + (R + 30) * math.sin(angle)
        anchor = "middle"
        lx = CX + (R + 28) * math.cos(angle)
        if math.cos(angle) > 0.3:
            anchor = "start"
        elif math.cos(angle) < -0.3:
            anchor = "end"
        out.append(
            f'<text x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="{anchor}" '
            f'font-family="{FONT}" font-size="12" fill="{t["muted"]}"'
            + (f'>{fade_in(0.6 + i * 0.06, 0.4)}{esc(label)}</text>'
               if animate else f'>{esc(label)}</text>')
        )

    out.append(
        f'<text x="{CX}" y="{HEIGHT - 10}" text-anchor="middle" font-family="{FONT}" '
        f'font-size="10.5" fill="{t["muted"]}">{esc(title)}</text>'
    )
    out.append("</svg>")
    return "".join(out)


GROUPS = {
    "Python": "Python",
    "Jupyter Notebook": "Notebooks",
    "TypeScript": "TypeScript",
    "JavaScript": "JavaScript",
    "TeX": "LaTeX",
    "HTML": "Web",
    "CSS": "Web",
    "Shell": "Shell",
    "PLpgSQL": "SQL",
    "Makefile": "Shell",
}


def language_axes(langs, count=8):
    merged = {}
    for lang, size in langs.items():
        key = GROUPS.get(lang, lang)
        merged[key] = merged.get(key, 0) + size
    ordered = sorted(merged.items(), key=lambda kv: -kv[1])[:count]
    # Log scale, otherwise one dominant language flattens everything else.
    scaled = [(name, math.log10(size + 10)) for name, size in ordered]
    hi = max(v for _, v in scaled)
    lo = min(v for _, v in scaled)
    span = max(1e-6, hi - lo)
    return [
        {"label": name, "value": 0.28 + 0.72 * (v - lo) / span}
        for name, v in scaled
    ]


def main():
    ap = argparse.ArgumentParser()
    # Off by default: a reveal animation renders as an empty box in any viewer
    # that shows only the first frame of an SVG (GitHub's own social previews
    # among them), and a blank chart is worse than a still one.
    ap.add_argument("--animate", action="store_true")
    args = ap.parse_args()
    animate = args.animate

    skills = json.loads((ASSETS / "skills.json").read_text())["axes"]
    for name in THEMES:
        (ASSETS / f"radar-{name}.svg").write_text(
            render(skills, name, "self-rated  ·  where I spend my attention", animate)
        )

    lang_file = ASSETS / "languages.json"
    if lang_file.exists():
        axes = language_axes(json.loads(lang_file.read_text()))
        for name in THEMES:
            (ASSETS / f"radar-langs-{name}.svg").write_text(
                render(axes, name, "measured  ·  bytes shipped per language (log)", animate)
            )
        print("language radar:", [a["label"] for a in axes])
    else:
        print("languages.json missing - run scripts/cards.py --stats first")


if __name__ == "__main__":
    main()
