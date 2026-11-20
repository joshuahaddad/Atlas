# /// script
# requires-python = ">=3.11"
# ///
"""Check a tier repo against CONVENTIONS.md. Prints each problem; exits 1 if any.

    uv run check.py path/to/tier-repo [--max-lines N]

The limit defaults to the repo's morpheus.toml `index_max_lines`, else 60.
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path

TYPES = {"user", "feedback", "project", "reference"}
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
SKIP = {"INDEX.md", "README.md"}  # files that carry no frontmatter


def frontmatter(text):
    """Return the frontmatter's key: value pairs, or None if there is none."""
    lines = [l.strip() for l in text.split("\n")]
    if lines[0] != "---" or "---" not in lines[1:]:
        return None
    body = lines[1 : lines.index("---", 1)]
    return {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in body if ":" in l)}


def check(repo, max_lines=60):
    repo = Path(repo).resolve()
    index = repo / "INDEX.md"
    if not index.is_file():
        return ["INDEX.md is missing"]
    problems = []
    n = len(index.read_text().splitlines())
    if n > max_lines:
        problems.append(f"INDEX.md has {n} lines; the limit is {max_lines}")

    # Every file must be reachable from INDEX.md through links: INDEX -> projects -> topics.
    seen, todo = set(), [index]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        for target in LINK.findall(f.read_text()):
            if "://" in target:
                continue
            t = (f.parent / target).resolve()
            if not t.is_relative_to(repo):
                continue  # a link out of the repo, such as a project's own docs
            if not t.is_file():
                problems.append(f"{f.relative_to(repo)}: broken link {target}")
            else:
                todo.append(t)

    for f in sorted(repo.rglob("*.md")):
        rel = f.relative_to(repo)
        if rel.parts[0].startswith(".") or f.name in SKIP and f.parent == repo:
            continue
        if f.resolve() not in seen:
            problems.append(f"{rel}: not linked from INDEX.md or a page it links")
        fm = frontmatter(f.read_text())
        if fm is None:
            problems.append(f"{rel}: no frontmatter")
            continue
        for key in ("name", "description", "type"):
            if not fm.get(key):
                problems.append(f"{rel}: frontmatter has no {key}")
        if fm.get("type") and fm["type"] not in TYPES:
            problems.append(f"{rel}: type {fm['type']!r} is not one of {', '.join(sorted(TYPES))}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo")
    ap.add_argument("--max-lines", type=int)
    a = ap.parse_args()
    policy = Path(a.repo) / "morpheus.toml"
    limit = a.max_lines or (tomllib.loads(policy.read_text()) if policy.is_file() else {}).get("index_max_lines", 60)
    problems = check(a.repo, limit)
    print("\n".join(problems) or "ok")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
