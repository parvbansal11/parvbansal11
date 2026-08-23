"""Render the project and statistics cards as self-hosted SVG.

Everything is drawn here and committed into the repo, so the profile never
depends on a shared public card service staying up.

    python scripts/cards.py            # all cards, both themes
    python scripts/cards.py --stats    # just the stats card
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

from theme import FONT, LANG_COLOURS, THEMES, compact, esc, wrap

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
USER = os.environ.get("GH_USER", "parvbansal11")
API = "https://api.github.com"


def token():
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    try:
        import subprocess
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except Exception:
        return None


SESSION = requests.Session()
_tok = token()
SESSION.headers.update({"Accept": "application/vnd.github+json",
                        "User-Agent": f"{USER}-profile-cards"})
if _tok:
    SESSION.headers["Authorization"] = f"Bearer {_tok}"


def get(path, **params):
    for attempt in range(3):
        r = SESSION.get(f"{API}{path}", params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (403, 429):
            time.sleep(2 + 3 * attempt)
            continue
        r.raise_for_status()
    raise RuntimeError(f"GET {path} failed")


def graphql(query, **variables):
    if not _tok:
        return None
    r = SESSION.post("https://api.github.com/graphql",
                     json={"query": query, "variables": variables}, timeout=30)
    if r.status_code != 200:
        return None
    return r.json().get("data")


# ---------------------------------------------------------------- data

def fetch_repos():
    repos, page = [], 1
    while True:
        batch = get(f"/users/{USER}/repos", per_page=100, page=page, type="owner")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_languages(repos):
    totals = {}
    for repo in repos:
        if repo["fork"]:
            continue
        try:
            for lang, count in get(f"/repos/{USER}/{repo['name']}/languages").items():
                totals[lang] = totals.get(lang, 0) + count
        except Exception:
            continue
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


CONTRIB_QUERY = """
query($login:String!){
  user(login:$login){
    followers{totalCount}
    contributionsCollection{
      totalCommitContributions
      totalPullRequestContributions
      restrictedContributionsCount
      contributionCalendar{totalContributions}
    }
    repositories(privacy:PRIVATE, ownerAffiliations:OWNER){totalCount}
  }
}
"""


def commit_count(repo_name):
    """Total commits on the default branch, read off the pagination header."""
    r = SESSION.get(f"{API}/repos/{USER}/{repo_name}/commits",
                    params={"per_page": 1}, timeout=30)
    if r.status_code != 200:
        return None
    link = r.headers.get("Link", "")
    for part in link.split(","):
        if 'rel="last"' in part:
            return int(part.split("page=")[-1].split(">")[0])
    return len(r.json())


def age(iso):
    from datetime import datetime, timezone
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (datetime.now(timezone.utc) - then).days
    if days < 1:
        return "today"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def fetch_profile(repos):
    user = get(f"/users/{USER}")
    stats = {
        "repos": user["public_repos"],
        "followers": user["followers"],
        "stars": sum(r["stargazers_count"] for r in repos),
        "forks": sum(r["forks_count"] for r in repos),
        "since": user["created_at"][:4],
        "contributions": None,
        "commits": None,
        "private": 0,
    }
    data = graphql(CONTRIB_QUERY, login=USER)
    if data and data.get("user"):
        u = data["user"]
        cc = u["contributionsCollection"]
        stats["contributions"] = cc["contributionCalendar"]["totalContributions"]
        stats["commits"] = cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        stats["prs"] = cc["totalPullRequestContributions"]
        stats["private"] = u["repositories"]["totalCount"]
        stats["followers"] = u["followers"]["totalCount"]
    return stats


# ---------------------------------------------------------------- drawing

def frame(w, h, t, radius=14):
    return (
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{radius}" '
        f'fill="{t["panel"]}" stroke="{t["border"]}"/>'
    )


def defs(name, t):
    return (
        "<defs>"
        f'<linearGradient id="g{name}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{t["accent"]}"/>'
        f'<stop offset="1" stop-color="{t["accent2"]}"/>'
        "</linearGradient>"
        f'<radialGradient id="h{name}" cx="0" cy="0" r="1">'
        f'<stop offset="0" stop-color="{t["accent"]}" stop-opacity="0.18"/>'
        f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/>'
        "</radialGradient>"
        "</defs>"
    )


STAR = ("M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97."
        "719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L."
        "818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z")
FORK = ("M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v."
        "878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 "
        "1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0Z")


def project_card(project, repo, theme_name):
    t = THEMES[theme_name]
    w, h = 470, 176
    name = project["name"]
    desc = project.get("blurb") or (repo or {}).get("description") or ""
    lang = project.get("language") or (repo or {}).get("language") or ""
    stars = (repo or {}).get("stargazers_count", 0)
    commits = project.get("_commits")
    updated = age((repo or {}).get("pushed_at")) if repo else None
    tags = project.get("tags", [])[:4]

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(name)}">',
        f"<title>{esc(name)}</title>",
        defs(theme_name, t),
        frame(w, h, t),
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="13" fill="url(#h{theme_name})"/>',
        f'<rect x="18" y="22" width="3" height="17" rx="1.5" fill="url(#g{theme_name})"/>',
        f'<text x="32" y="36" font-family="{FONT}" font-size="16" font-weight="700" '
        f'fill="{t["text"]}">{esc(name)}</text>',
    ]

    y = 62
    for line in wrap(desc, 58)[:4]:
        out.append(
            f'<text x="18" y="{y}" font-family="{FONT}" font-size="11.5" '
            f'fill="{t["muted"]}">{esc(line)}</text>'
        )
        y += 17

    # tag chips
    x = 18
    for tag in tags:
        cw = 9 + len(tag) * 6.4
        out.append(
            f'<rect x="{x:.0f}" y="{h - 52}" width="{cw:.0f}" height="19" rx="9.5" '
            f'fill="none" stroke="{t["border"]}"/>'
            f'<text x="{x + cw / 2:.0f}" y="{h - 38}" text-anchor="middle" '
            f'font-family="{FONT}" font-size="10" fill="{t["muted"]}">{esc(tag)}</text>'
        )
        x += cw + 7

    # footer stats
    out.append(f'<line x1="18" y1="{h - 27}" x2="{w - 18}" y2="{h - 27}" stroke="{t["border"]}"/>')
    fy = h - 11
    fx = 18
    if lang:
        colour = LANG_COLOURS.get(lang, t["accent"])
        out.append(f'<circle cx="{fx + 5}" cy="{fy - 4}" r="5" fill="{colour}"/>')
        out.append(
            f'<text x="{fx + 16}" y="{fy}" font-family="{FONT}" font-size="11" '
            f'fill="{t["muted"]}">{esc(lang)}</text>'
        )
        fx += 26 + len(lang) * 6.6

    if stars:
        out.append(
            f'<g transform="translate({fx:.0f},{fy - 12}) scale(0.8)">'
            f'<path d="{STAR}" fill="{t["muted"]}"/></g>'
            f'<text x="{fx + 17:.0f}" y="{fy}" font-family="{FONT}" font-size="11" '
            f'fill="{t["muted"]}">{compact(stars)}</text>'
        )
        fx += 34 + 6 * len(compact(stars))

    # A squashed import shows up as "2 commits", which reads as an abandoned
    # repo rather than a compact one. Below five, say nothing.
    if commits and commits >= 5:
        label = f"{compact(commits)} commit" + ("s" if commits != 1 else "")
        out.append(
            f'<text x="{fx:.0f}" y="{fy}" font-family="{FONT}" font-size="11" '
            f'fill="{t["muted"]}">{esc(label)}</text>'
        )
        fx += 12 + 6.6 * len(label)

    if updated:
        out.append(
            f'<text x="{fx:.0f}" y="{fy}" font-family="{FONT}" font-size="11" '
            f'fill="{t["muted"]}">{esc(updated)}</text>'
        )

    live = project.get("live")
    if live:
        out.append(
            f'<text x="{w - 18}" y="{fy}" text-anchor="end" font-family="{FONT}" '
            f'font-size="11" fill="{t["accent"]}">{esc(live)}</text>'
        )

    out.append("</svg>")
    return "".join(out)


def stats_card(stats, langs, theme_name):
    t = THEMES[theme_name]
    w, h = 500, 218
    total = sum(langs.values()) or 1

    cells = [
        ("repositories", compact(stats["repos"] + stats.get("private", 0))),
        ("commits", compact(stats["commits"]) if stats.get("commits") else "--"),
        ("pull requests", compact(stats.get("prs", 0))),
        ("contributions", compact(stats["contributions"]) if stats.get("contributions") else "--"),
    ]
    if stats["stars"]:
        cells[2] = ("stars earned", compact(stats["stars"]))

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="GitHub statistics">',
        "<title>GitHub statistics</title>",
        defs(theme_name, t),
        frame(w, h, t),
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="13" fill="url(#h{theme_name})"/>',
        f'<text x="20" y="32" font-family="{FONT}" font-size="12.5" fill="{t["muted"]}">'
        f'{esc(USER)} <tspan fill="{t["accent"]}">// building since {stats["since"]}</tspan></text>',
    ]

    for i, (label, value) in enumerate(cells):
        cx = 20 + i * 120
        out.append(
            f'<text x="{cx}" y="{86}" font-family="{FONT}" font-size="30" font-weight="700" '
            f'fill="url(#g{theme_name})">{esc(value)}</text>'
            f'<text x="{cx}" y="{104}" font-family="{FONT}" font-size="10" '
            f'fill="{t["muted"]}">{esc(label)}</text>'
        )

    out.append(f'<line x1="20" y1="126" x2="{w - 20}" y2="126" stroke="{t["border"]}"/>')
    out.append(
        f'<text x="20" y="148" font-family="{FONT}" font-size="10.5" '
        f'fill="{t["muted"]}">language mix across public repositories</text>'
    )

    # stacked language bar
    bar_x, bar_w, bar_y = 20, w - 40, 158
    x = float(bar_x)
    top = list(langs.items())[:6]
    shown = sum(v for _, v in top)
    rest = total - shown
    segments = top + ([("other", rest)] if rest > 0 else [])
    out.append(f'<clipPath id="bar{theme_name}"><rect x="{bar_x}" y="{bar_y}" '
               f'width="{bar_w}" height="10" rx="5"/></clipPath>')
    out.append(f'<g clip-path="url(#bar{theme_name})">')
    for lang, count in segments:
        seg = bar_w * count / total
        colour = LANG_COLOURS.get(lang, t["border"])
        out.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{seg + 0.6:.2f}" height="10" fill="{colour}"/>')
        x += seg
    out.append("</g>")

    lx, ly = 20, 192
    for lang, count in segments[:4]:
        pct = 100 * count / total
        name = lang if len(lang) <= 12 else lang.split()[0]
        label = f"{name} {pct:.0f}%"
        colour = LANG_COLOURS.get(lang, t["border"])
        out.append(
            f'<circle cx="{lx + 4}" cy="{ly - 4}" r="4" fill="{colour}"/>'
            f'<text x="{lx + 14}" y="{ly}" font-family="{FONT}" font-size="10" '
            f'fill="{t["muted"]}">{esc(label)}</text>'
        )
        lx += 26 + len(label) * 6.1

    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true", help="stats card only")
    ap.add_argument("--projects", action="store_true", help="project cards only")
    args = ap.parse_args()
    do_all = not (args.stats or args.projects)

    ASSETS.mkdir(exist_ok=True)
    repos = fetch_repos()
    index = {r["name"].lower(): r for r in repos}

    if do_all or args.stats:
        langs = fetch_languages(repos)
        stats = fetch_profile(repos)
        for name in THEMES:
            (ASSETS / f"card-stats-{name}.svg").write_text(stats_card(stats, langs, name))
        (ASSETS / "languages.json").write_text(json.dumps(langs, indent=2))
        print("stats card:", stats)

    if do_all or args.projects:
        projects = json.loads((ASSETS / "projects.json").read_text())
        for project in projects:
            repo = index.get(project["repo"].lower())
            project["_commits"] = commit_count(project["repo"]) if repo else None
            if repo is None:
                print(f"  ! {project['repo']} not found on the API", file=sys.stderr)
            for name in THEMES:
                svg = project_card(project, repo, name)
                (ASSETS / f"card-{project['repo']}-{name}.svg").write_text(svg)
            print("card:", project["repo"])


if __name__ == "__main__":
    main()
