import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skills/dream/scripts"))
import filter as f  # noqa: E402


def jsonl(path, sid, text):
    recs = [
        {"type": "user", "sessionId": sid, "cwd": "/work/lantern", "timestamp": "2026-01-01T10:00:00Z",
         "message": {"role": "user", "content": text}},
        {"type": "assistant", "sessionId": sid, "timestamp": "2026-01-01T10:01:00Z",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "thinking": "hidden"},
             {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x" * 5000}]}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in recs) + '\n{"partial')


def opencode_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        create table session (id text, directory text, time_created int, time_updated int);
        create table message (id text, session_id text, time_created int, data text);
        create table part (id text, message_id text, session_id text, time_created int, data text);""")
    now = int(time.time() * 1000)
    for sid, text in [("ses_ok", "use uv for python"), ("ses_bad", "see /srv/payroll/q1.csv")]:
        db.execute("insert into session values (?,?,?,?)", (sid, "/work/tidepool", now, now))
        db.execute("insert into message values (?,?,?,?)", (sid + "m", sid, now, json.dumps({"role": "user"})))
        db.execute("insert into part values (?,?,?,?,?)",
                   (sid + "p", sid + "m", sid, now, json.dumps({"type": "text", "text": text})))
        db.execute("insert into part values (?,?,?,?,?)", (sid + "q", sid + "m", sid, now + 1, json.dumps(
            {"type": "tool", "tool": "bash", "state": {"input": {"command": "ls"}, "output": "a b"}})))
    db.commit()


def test_filter(tmp_path):
    proj = tmp_path / "projects/-work-lantern"
    (proj / "memory").mkdir(parents=True)
    jsonl(proj / "s-ok.jsonl", "s-ok", "prefer small PRs")
    jsonl(proj / "s-bad.jsonl", "s-bad", "open /srv/payroll/q1.csv")
    jsonl(proj / "s-dream.jsonl", "s-dream", "<!-- dreamkit:dream-session -->")
    jsonl(proj / "s-old.jsonl", "s-old", "old news")
    os.utime(proj / "s-old.jsonl", (0, 0))
    (proj / "memory/style.md").write_text("tabs, never spaces")
    (proj / "memory/pay.md").write_text("Payroll runs on Fridays")
    opencode_db(tmp_path / "opencode.db")
    tier = {"deny": ["/srv/payroll", "(?i)payroll"], "max_age_days": 7, "sources": [
        {"kind": "claude-jsonl", "glob": str(tmp_path / "projects/*/*.jsonl")},
        {"kind": "files", "glob": str(tmp_path / "projects/*/memory/*.md")},
        {"kind": "opencode-sqlite", "path": str(tmp_path / "opencode.db")},
    ]}
    out = tmp_path / "out"
    m = f.run(tier, out)

    assert sorted(s["id"] for s in m["kept"]) == ["claude-s-ok", "opencode-ses_ok"]
    assert sorted(p.name for p in (out / "sessions").iterdir()) == ["claude-s-ok.md", "opencode-ses_ok.md"]
    assert os.listdir(out / "memory") == ["-work-lantern__memory__style.md"]
    assert sum(m["dropped_by_pattern"].values()) == 4  # s-bad, s-dream, pay.md, ses_bad
    claude = (out / "sessions/claude-s-ok.md").read_text()
    assert "prefer small PRs" in claude and "[tool Bash]" in claude and "cwd: /work/lantern" in claude
    assert "hidden" not in claude and "chars cut" in claude
    assert "[tool bash]" in (out / "sessions/opencode-ses_ok.md").read_text()
    # Nothing that matches a deny pattern reaches the work dir.
    assert not any("payroll" in p.read_text().lower() for p in out.rglob("*.md"))

    # A second run into the same dir refuses, which also keeps two dreams apart.
    try:
        f.run(tier, out)
    except SystemExit as e:
        assert "not empty" in str(e)
    else:
        raise AssertionError("second run should refuse")
