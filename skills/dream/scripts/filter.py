# /// script
# requires-python = ">=3.11"
# ///
"""Copy one tier's allowed sessions and memory files into a work dir.

Runs before the model. A session or file that matches any of the tier's deny
patterns anywhere in its raw text is dropped whole, so the model never sees it.

    uv run filter.py --tier org --out ~/.cache/dreamkit/org-2026-01-31
"""

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time
import tomllib
from pathlib import Path

DEFAULT_CONFIG = "~/.config/dreamkit/dreamkit.toml"
# Sessions that ran dream itself hold other sessions' text; skip them so dream never feeds on its own output.
DREAM_MARKER = "dreamkit:" + "dream-session"
CLIP = 2000  # characters kept from each tool input or result


def load_tier(config, tier):
    with open(os.path.expanduser(config), "rb") as f:
        tiers = tomllib.load(f).get("tiers", {})
    if tier not in tiers:
        sys.exit(f"no tier {tier!r} in {config}; tiers: {', '.join(tiers) or 'none'}")
    t = tiers[tier]
    t.setdefault("base", "main")
    t["repo"] = os.path.expanduser(t["repo"])
    return t


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
        raw = Path(path).read_text(errors="replace")
        lines, meta = [], {}
        for line in raw.splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue  # a live session's last line can be partial
            meta.setdefault("cwd", d.get("cwd"))
            meta.setdefault("start", d.get("timestamp"))
            meta["end"] = d.get("timestamp") or meta.get("end")
            msg = d.get("message")
            if d.get("type") in ("user", "assistant") and isinstance(msg, dict):
                text = claude_text(msg.get("content"))
                if text.strip():
                    lines.append(f"## {d['type']}\n{text}")
        yield "claude-" + Path(path).stem, raw, meta, "\n\n".join(lines)


def opencode_sessions(src, since):
    """OpenCode (checked on 1.18): sessions in a SQLite DB, tables session, message, part."""
    path = os.path.expanduser(src["path"])
    if not os.path.exists(path):
        return
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    sessions = db.execute(
        "select id, directory, time_created, time_updated from session where time_updated >= ? order by time_created",
        (since * 1000,),
    ).fetchall()
    for sid, directory, created, updated in sessions:
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
        meta = {"cwd": directory, "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created / 1000)),
                "end": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(updated / 1000))}
        yield "opencode-" + sid, raw, meta, "\n\n".join(lines)


def memory_files(src):
    """Scratch memory: plain files, copied as they are."""
    for path in sorted(glob.glob(os.path.expanduser(src["glob"]))):
        name = "__".join(Path(path).parts[-3:])  # keeps the project folder in the name
        yield name, Path(path).read_text(errors="replace")


def run(tier, out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty: another dream may be running, or remove it")
    (out / "sessions").mkdir(parents=True, exist_ok=True)
    (out / "memory").mkdir(exist_ok=True)
    deny = [re.compile(p) for p in tier.get("deny", [])] + [re.compile(re.escape(DREAM_MARKER))]
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
    ap.add_argument("--config", default=os.environ.get("DREAMKIT_CONFIG", DEFAULT_CONFIG))
    ap.add_argument("--tier", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    m = run(load_tier(a.config, a.tier), os.path.expanduser(a.out))
    n_mem = len(os.listdir(Path(os.path.expanduser(a.out)) / "memory"))
    print(f"kept {len(m['kept'])} sessions and {n_mem} memory files; dropped {sum(m['dropped_by_pattern'].values())}")


if __name__ == "__main__":
    main()
