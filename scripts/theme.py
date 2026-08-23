"""Shared palette and small SVG helpers."""

import xml.sax.saxutils as sax

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "panel": "#0d1117",
        "border": "#232a33",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "accent": "#2dd4a7",
        "accent2": "#8b7cff",
        "grid": "#161b22",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#ffffff",
        "border": "#d5dbe1",
        "text": "#1f2328",
        "muted": "#59636e",
        "accent": "#0f9d78",
        "accent2": "#6248d8",
        "grid": "#eef1f4",
    },
}

FONT = ("ui-monospace,'SFMono-Regular','JetBrains Mono',"
        "Menlo,Consolas,'Liberation Mono',monospace")

LANG_COLOURS = {
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Jupyter Notebook": "#DA5B0B",
    "TeX": "#3D6117",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "C++": "#f34b7d",
    "C": "#555555",
    "Shell": "#89e051",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "PLpgSQL": "#336790",
}


def esc(text):
    return sax.escape(str(text))


def wrap(text, width):
    """Greedy wrap that also copes with the long words in repo blurbs."""
    words, lines, line = str(text).split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def compact(n):
    n = float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return f"{int(n)}"
