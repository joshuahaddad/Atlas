# /// script
# requires-python = ">=3.11"
# ///
"""Copy one tier's allowed sessions and memory files into a work dir.

Runs before the model. A session or file that matches any of the tier's deny
patterns anywhere in its raw text is dropped whole, so the model never sees it.
A tier's optional `prepare` command runs first, such as to copy another user's sessions.

    uv run filter.py --tier org --out ~/.cache/morpheus/org-2026-01-31
    uv run filter.py --tier org --show
"""

import argparse
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import tomllib
from pathlib import Path

DEFAULT_CONFIG = os.environ.get("MORPHEUS_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or "~/.config", "morpheus", "morpheus.toml")
SETUP_HINT = "ask the agent to set up morpheus (the dream skill's \"Set up a tier\")"
# Secret shapes, dropped on every tier on top of its own deny patterns.
BUILTIN_DENY = [
    r"BEGIN [A-Z ]*PRIVATE KEY",
    r"\b(sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_\w{50,}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})",
]
# Sessions that ran dream itself hold other sessions' text; skip them so dream never feeds on its own output.
DREAM_MARKERS = ["morpheus:" + "dream-session",
                 # shortcut: dreams from before the rename to morpheus; drop once they pass max_age_days (after 2026-12)
                 "dreamkit:" + "dream-session"]
CLIP = 2000  # characters kept from each tool input or result


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def load_tier(config, tier):
    """The tier's table from the user's config, over the tier repo's own morpheus.toml on origin/<base>.
    The user's keys win, except deny, which adds to the tier's patterns."""
    path = os.path.expanduser(config)
    if not os.path.exists(path):
        sys.exit(f"no morpheus config at {config}; {SETUP_HINT}")
    with open(path, "rb") as f:
        tiers = tomllib.load(f).get("tiers", {})
    if tier not in tiers:
        sys.exit(f"no tier {tier!r} in {config}; tiers: {', '.join(tiers) or 'none'}; {SETUP_HINT}")
    user = tiers[tier]
    repo = os.path.expanduser(user["repo"])
    head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").stdout.strip()
    base = user.get("base") or head.removeprefix("origin/") or "main"
    ref = f"origin/{base}"
    # Read from origin, not the checkout, so a dream branch can't loosen its own filter.
    if git(repo, "rev-parse", "--verify", "--quiet", ref).returncode:
        sys.exit(f"{repo} has no {ref}: clone the tier repo there and fetch")
    policy = {}
    if git(repo, "ls-tree", "--name-only", ref, "morpheus.toml").stdout.strip():
        policy = tomllib.loads(git(repo, "show", f"{ref}:morpheus.toml").stdout)
    return policy | user | {"repo": repo, "base": base, "deny": policy.get("deny", []) + user.get("deny", [])}


def clip(s):
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return s if len(s) <= CLIP else s[:CLIP] + f" [... {len(s) - CLIP} chars cut]"


def claude_text(content):
    """Render a Claude Code message's content (a string or a list of blocks)."""
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        t = b.get("type")
        if t == "text":
            out.append(b["text"])
        elif t == "tool_use":
            out.append(f"[tool {b.get('name')}] {clip(b.get('input'))}")
        elif t == "tool_result":
            c = b.get("content")
            if isinstance(c, list):
                c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
            out.append(f"[result] {clip(c)}")
    return "\n".join(out)


def claude_sessions(src, since):
    """Claude Code: one JSONL file per session under ~/.claude/projects/<project>/."""
    for path in sorted(glob.glob(os.path.expanduser(src["glob"]))):
        if os.path.getmtime(path) < since:
            continue
        # raw is the full messages only: attachment records hold the instruction files, which the model never sees here.
        raws, lines, meta = [], [], {}
        for line in Path(path).read_text(errors="replace").splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue  # a live session's last line can be partial
            meta.setdefault("cwd", d.get("cwd"))
            meta.setdefault("start", d.get("timestamp"))
            meta["end"] = d.get("timestamp") or meta.get("end")
            msg = d.get("message")
            if d.get("type") in ("user", "assistant") and isinstance(msg, dict):
                raws.append(json.dumps(msg, ensure_ascii=False))
                text = claude_text(msg.get("content"))
                if text.strip():
                    lines.append(f"## {d['type']}\n{text}")
        yield "claude-" + Path(path).stem, "\n".join(raws), meta, "\n\n".join(lines)


def opencode_sessions(src, since):
    """OpenCode: sessions in a SQLite DB. 1.x keeps them in session, message and part; 2.0 in
    session_v2 and session_message, and keeps the 1.x tables for sessions made before it."""
    path = os.path.expanduser(src["path"])
    if not os.path.exists(path):
        return
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables = {n for (n,) in db.execute("select name from sqlite_master where type = 'table'")}
    for table, render in (("session", opencode_v1), ("session_v2", opencode_v2)):
        if table not in tables:
            continue
        sessions = db.execute(
            f"select id, directory, time_created, time_updated from {table} where time_updated >= ? order by time_created",
            (since * 1000,),
        ).fetchall()
        for sid, directory, created, updated in sessions:
            raw, lines = render(db, sid)
            meta = {"cwd": directory, "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created / 1000)),
                    "end": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(updated / 1000))}
            yield "opencode-" + sid, raw, meta, "\n\n".join(lines)


def opencode_v1(db, sid):
    rows = db.execute(
        "select m.data, p.data from part p join message m on p.message_id = m.id"
        " where p.session_id = ? order by p.time_created",
        (sid,),
    ).fetchall()
    raw = "\n".join(m + "\n" + p for m, p in rows)
    lines = []
    for m, p in rows:
        role, part = json.loads(m).get("role"), json.loads(p)
        if part.get("type") == "text":
            lines.append(f"## {role}\n{part['text']}")
        elif part.get("type") == "tool":
            st = part.get("state", {})
            lines.append(f"## {role}\n[tool {part.get('tool')}] {clip(st.get('input'))}\n[result] {clip(st.get('output', ''))}")
    return raw, lines


# The 2.0 message types the model reads; `system` holds the loaded instruction files, as Claude
# Code's attachment records do, so it is neither rendered nor matched
OPENCODE_V2_TYPES = ("user", "assistant", "synthetic", "compaction")


def opencode_v2(db, sid):
    rows = db.execute(
        f"select type, data from session_message where session_id = ? and type in ({','.join('?' * len(OPENCODE_V2_TYPES))})"
        " order by seq",
        (sid, *OPENCODE_V2_TYPES),
    ).fetchall()
    raw = "\n".join(data for _, data in rows)
    lines = []
    for kind, data in rows:
        d = json.loads(data)
        if kind == "user" and d.get("text"):
            lines.append(f"## user\n{d['text']}")
        elif kind == "synthetic" and d.get("text"):
            lines.append(f"## user\n[{d.get('description') or 'synthetic'}] {clip(d['text'])}")
        elif kind == "compaction" and d.get("summary"):
            lines.append(f"## summary\n{d['summary']}")
        elif kind == "assistant":
            for b in d.get("content") or []:
                if b.get("type") == "text":
                    lines.append(f"## assistant\n{b['text']}")
                elif b.get("type") == "tool":
                    st = b.get("state") or {}
                    out = st.get("content") or st.get("error") or ""
                    if isinstance(out, list):
                        out = "\n".join(x.get("text", "") for x in out if isinstance(x, dict))
                    lines.append(f"## assistant\n[tool {b.get('name')}] {clip(st.get('input'))}\n[result] {clip(out)}")
    return raw, lines


def memory_files(src):
    """Scratch memory: plain files, copied as they are."""
    for path in sorted(glob.glob(os.path.expanduser(src["glob"]))):
        name = "__".join(Path(path).parts[-3:])  # keeps the project folder in the name
        yield name, Path(path).read_text(errors="replace")


def run(tier, out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty: another dream may be running, or remove it")
    if tier.get("prepare"):
        r = subprocess.run(tier["prepare"], shell=True)
        if r.returncode:
            sys.exit(f"prepare exited {r.returncode}; nothing written")
    (out / "sessions").mkdir(parents=True, exist_ok=True)
    (out / "memory").mkdir(exist_ok=True)
    deny = [re.compile(p) for p in BUILTIN_DENY + tier.get("deny", [])] + [re.compile(re.escape(m)) for m in DREAM_MARKERS]
    since = time.time() - tier.get("max_age_days", 7) * 86400
    kept, dropped = [], {}

    def denied(raw):
        hit = next((p.pattern for p in deny if p.search(raw)), None)
        if hit:
            dropped[hit] = dropped.get(hit, 0) + 1
        return hit

    for src in tier.get("sources", []):
        kind = src["kind"]
        if kind == "files":
            for name, text in memory_files(src):
                if not denied(text):
                    (out / "memory" / name).write_text(text)
            continue
        gen = {"claude-jsonl": claude_sessions, "opencode-sqlite": opencode_sessions}.get(kind)
        if gen is None:
            sys.exit(f"unknown source kind {kind!r}")
        for sid, raw, meta, text in gen(src, since):
            # Raw text catches what clipping cut; the rendered text is exactly what the model reads.
            if not text or denied(raw + "\n" + text):
                continue
            (out / "sessions" / f"{sid}.md").write_text(
                f"# {sid}\ncwd: {meta.get('cwd')}\nfrom: {meta.get('start')}\nto: {meta.get('end')}\n\n{text}\n")
            kept.append({"id": sid, **meta})
    manifest = {"kept": kept, "dropped_by_pattern": dropped}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--tier", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out")
    g.add_argument("--show", action="store_true", help="print the tier's merged config as JSON and exit")
    a = ap.parse_args()
    t = load_tier(a.config, a.tier)
    if a.show:
        print(json.dumps(t, indent=2))
        return
    m = run(t, os.path.expanduser(a.out))
    n_mem = len(os.listdir(Path(os.path.expanduser(a.out)) / "memory"))
    print(f"kept {len(m['kept'])} sessions and {n_mem} memory files; dropped {sum(m['dropped_by_pattern'].values())}")


if __name__ == "__main__":
    main()
