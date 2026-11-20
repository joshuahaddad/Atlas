import json
import os
import sqlite3
import subprocess
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
    jsonl(proj / "s-dream.jsonl", "s-dream", "<!-- morpheus:dream-session -->")
    jsonl(proj / "s-dream-old.jsonl", "s-dream-old", "<!-- dreamkit:dream-session -->")
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
    assert sum(m["dropped_by_pattern"].values()) == 5  # s-bad, s-dream, s-dream-old, pay.md, ses_bad
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


def test_messages_only(tmp_path):
    # The deny pattern sits in an instruction file the tool recorded, not in what the model saw.
    jsonl(tmp_path / "s-att.jsonl", "s-att", "prefer small PRs")
    with open(tmp_path / "s-att.jsonl", "a") as fh:
        fh.write("\n" + json.dumps({"type": "attachment", "content": "never read /srv/payroll"}))
    # The match is in a tool result past the clip, so only the full message has it.
    recs = [{"type": "user", "message": {"role": "user", "content": "hi"}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "x" * 5000 + " /srv/payroll"}]}}]
    (tmp_path / "s-cut.jsonl").write_text("\n".join(json.dumps(r) for r in recs))
    tier = {"deny": ["/srv/payroll"], "sources": [{"kind": "claude-jsonl", "glob": str(tmp_path / "*.jsonl")}]}
    m = f.run(tier, tmp_path / "out")
    assert [s["id"] for s in m["kept"]] == ["claude-s-att"]
    assert m["dropped_by_pattern"] == {"/srv/payroll": 1}


def test_prepare(tmp_path):
    src = tmp_path / "src"
    tier = {"prepare": "exit 3", "sources": [{"kind": "files", "glob": str(src / "*.md")}]}
    try:
        f.run(tier, tmp_path / "out")
    except SystemExit as e:
        assert "prepare exited 3" in str(e)
    else:
        raise AssertionError("a failing prepare should stop the filter")
    assert not (tmp_path / "out").exists()

    tier["prepare"] = f"mkdir {src} && echo tabs > {src}/style.md"
    f.run(tier, tmp_path / "out")
    assert [p.read_text() for p in (tmp_path / "out/memory").iterdir()] == ["tabs\n"]


def opencode_v2_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        create table session_v2 (id text, directory text, time_created int, time_updated int);
        create table session_message (id text, session_id text, type text, seq int, time_created int, data text);""")
    now = int(time.time() * 1000)
    msgs = {
        "ses_ok": [("system", {"text": "rules: never open /srv/payroll"}),
                   ("user", {"text": "use uv for python"}),
                   ("assistant", {"content": [
                       {"type": "reasoning", "text": "hidden"},
                       {"type": "text", "text": "will do"},
                       {"type": "tool", "name": "bash", "state": {"input": {"command": "ls"},
                                                                  "content": [{"type": "text", "text": "a b"}]}}]})],
        "ses_bad": [("user", {"text": "hi"}),
                    ("assistant", {"content": [{"type": "tool", "name": "read", "state": {
                        "input": {}, "content": [{"type": "text", "text": "x" * 5000 + " /srv/payroll/q1.csv"}]}}]})],
    }
    for sid, rows in msgs.items():
        db.execute("insert into session_v2 values (?,?,?,?)", (sid, "/work/tidepool", now, now))
        for i, (kind, data) in enumerate(rows):
            db.execute("insert into session_message values (?,?,?,?,?,?)",
                       (f"{sid}{i}", sid, kind, i, now, json.dumps({"time": {"created": now}, **data})))
    db.commit()


def test_opencode_v2(tmp_path):
    opencode_v2_db(tmp_path / "opencode.db")
    tier = {"deny": ["/srv/payroll"], "sources": [{"kind": "opencode-sqlite", "path": str(tmp_path / "opencode.db")}]}
    m = f.run(tier, tmp_path / "out")
    # The instruction file in `system` doesn't drop ses_ok; a match past the clip drops ses_bad.
    assert [s["id"] for s in m["kept"]] == ["opencode-ses_ok"]
    text = (tmp_path / "out/sessions/opencode-ses_ok.md").read_text()
    assert "use uv for python" in text and "will do" in text and "[tool bash]" in text and "a b" in text
    assert "hidden" not in text and "payroll" not in text


def test_builtin_deny(tmp_path):
    jsonl(tmp_path / "s-key.jsonl", "s-key", "token is ghp_" + "x" * 36)
    jsonl(tmp_path / "s-ok.jsonl", "s-ok", "prefer small PRs")
    m = f.run({"sources": [{"kind": "claude-jsonl", "glob": str(tmp_path / "*.jsonl")}]}, tmp_path / "out")
    assert [s["id"] for s in m["kept"]] == ["claude-s-ok"]


def sh(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def tier_clone(tmp_path, policy):
    """A tier repo on a local origin whose default branch is `trunk`, and a clone of it."""
    origin, clone = tmp_path / "origin", tmp_path / "clone"
    sh("git", "init", "-q", "-b", "trunk", str(origin))
    (origin / "INDEX.md").write_text("# Index\n")
    if policy:
        (origin / "morpheus.toml").write_text(policy)
    sh("git", "add", "-A", cwd=origin)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init", cwd=origin)
    sh("git", "clone", "-q", str(origin), str(clone))
    return clone


def config(tmp_path, table):
    p = tmp_path / "morpheus.toml"
    p.write_text(table)
    return str(p)


def test_load_tier_merges_policy(tmp_path):
    clone = tier_clone(tmp_path, 'model = "local only"\nindex_max_lines = 40\ndeny = ["tier-secret"]\n')
    # A change on the checkout, such as on a dream branch, does not reach the filter.
    (clone / "morpheus.toml").write_text("deny = []\n")
    t = f.load_tier(config(tmp_path, f'[tiers.org]\nrepo = "{clone}"\nmodel = "mine"\ndeny = ["user-secret"]\n'), "org")
    assert t["base"] == "trunk" and t["repo"] == str(clone)
    assert t["model"] == "mine" and t["index_max_lines"] == 40
    assert t["deny"] == ["tier-secret", "user-secret"]


def test_load_tier_without_policy(tmp_path):
    clone = tier_clone(tmp_path, None)
    t = f.load_tier(config(tmp_path, f'[tiers.org]\nrepo = "{clone}"\nbase = "trunk"\n'), "org")
    assert t["deny"] == [] and "model" not in t


def test_load_tier_errors(tmp_path):
    for cfg, tier, want in [(str(tmp_path / "none.toml"), "org", "no morpheus config"),
                            (config(tmp_path, '[tiers.org]\nrepo = "/x"\n'), "private", "Set up a tier"),
                            (config(tmp_path, f'[tiers.org]\nrepo = "{tmp_path}"\n'), "org", "has no origin/main")]:
        try:
            f.load_tier(cfg, tier)
        except SystemExit as e:
            assert want in str(e), e
        else:
            raise AssertionError(f"{want}: should exit")
