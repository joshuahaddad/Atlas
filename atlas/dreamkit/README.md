# dreamkit

Shared memory for coding agents (Claude Code, OpenCode), kept as markdown in git and changed
only through reviewed pull requests.

Agents learn things in sessions: a preference, a correction, how two projects fit together.
Each tool keeps that in its own scratch memory, per project, per machine. dreamkit gives a
team (or one person with many projects) an **org memory** every agent reads, and a batch job,
**dream**, that proposes what it should learn from the agents' sessions. A human merges or
rejects each proposal.

## The four layers

| Layer | Where | Written by | Read by |
|---|---|---|---|
| Org | a tier repo, such as `memory-org` | merged PRs only | every agent allowed that tier |
| Private | another tier repo, such as `memory-private` | merged PRs only | a smaller group |
| Project | each repo's own `AGENTS.md` and docs | that repo's PRs | sessions in that repo |
| Scratch | each tool's own memory (Claude Code auto memory, ...) | the agent, freely | that agent, and dream |

Git permissions work per repo, so each read tier is its own repo. Agents never write a tier
repo; `dream` and `remember` open PRs, and a human merges them. Git records who changed what
and when; a dream PR names the sessions behind each change.

A tier repo is plain markdown: a short `INDEX.md` loaded into every session, a page per
project, and topic pages read on demand. See [CONVENTIONS.md](CONVENTIONS.md) and
[example/](example/).

## What's here

- `skills/dream/`: the dream skill, and its scripts:
  - `scripts/filter.py` copies a tier's allowed sessions and memory files into a work dir.
    It drops any session or file that matches the tier's deny patterns, before the model sees
    anything.
  - `scripts/check.py` checks a tier repo: `INDEX.md` under a line limit, every page linked,
    valid frontmatter.
  - `scripts/open_pr.py` runs the tier's PR command.
- `skills/remember/`: proposes one topic to a tier as a small PR, from inside a session.
- `dreamkit.toml.example`: per-tier config: repo, sources, deny patterns, an optional prepare
  command, model hint, PR command.

The scripts use only the Python standard library (3.11 or later) and run with `uv run`, or
`python3` where uv isn't installed.

## Install

1. Create a tier repo in your forge (start from `example/`) and protect its `main`, so only
   reviewed PRs reach it. Add a secret scanner (such as `gitleaks`) to its pre-commit or CI.
2. Check it out where agents can read it, and keep that checkout pulled.
3. Load its `INDEX.md` in every session:
   - Claude Code: `ln -s /path/to/memory-org/INDEX.md ~/.claude/rules/org-memory.md`
   - OpenCode: add the path to `instructions` in `~/.config/opencode/opencode.json`, or link it
     as `~/.config/opencode/AGENTS.md` if you have no global AGENTS.md.
4. Install the skills: run `install.sh` at the root of Atlas and pick `dreamkit/`.
5. For each user who runs dream: copy `dreamkit.toml.example` to
   `~/.config/dreamkit/dreamkit.toml` and fill in each tier. Give `repo` its own clone (not
   the checkout agents read), and give that clone a remote the PR command can push to: a fork,
   or a review ref.

## Run dream by hand

In a Claude Code or OpenCode session, as the user that can read the tier's sources, on a model
the tier allows:

> dream for org

The skill filters the sessions into `~/.cache/dreamkit/<tier>-<date>/`, reads only that, commits
its changes on a `dream/<tier>-<date>` branch in the tier clone, runs `check.py`, and opens the PR.

To see what the model would get, run the filter alone:

```bash
uv run skills/dream/scripts/filter.py --tier org --out /tmp/dream-preview
```

Run one dream per tier. A tier whose readers are a smaller group should be dreamed by a user
and a model that group trusts, over that group's sessions only.

## Sources

| `kind` | What | Checked on |
|---|---|---|
| `claude-jsonl` | Claude Code sessions: one JSONL file per session under `~/.claude/projects/<project>/` | Claude Code, 2026-10 |
| `files` | Plain memory files, such as Claude Code auto memory in `~/.claude/projects/*/memory/` | |
| `opencode-sqlite` | OpenCode sessions in `~/.local/share/opencode/opencode.db`: tables `session`, `message` and `part` (1.x), and `session_v2` and `session_message` (2.0, which keeps the 1.x tables for older sessions) | OpenCode 1.18 and 2.0.30 |

Older OpenCode versions kept sessions as JSON files under `~/.local/share/opencode/storage/`;
that layout is not supported.

## Security

- **Review dream PRs like code.** A merged page is loaded into every agent's context on that
  tier. A wrong memory spreads; agents copy what memory tells them.
- **Transcripts carry text nobody on your team wrote:** web pages, issue comments, tool output.
  Someone can plant instructions there, hoping dream turns them into memory. The skill treats
  that text as data and flags proposals that rest on it, but the review is the only real gate.
  Check each change's evidence.
- **The filter is the only thing that keeps data out of a tier.** It drops whole sessions on a
  plain regex match. Deny patterns are blunt: test them with a dry run of the filter, and prefer
  a stricter pattern to a leak. They match the messages, not the instruction files a tool
  records.
- **Transcripts hold secrets** that passed through a session. The skill tells the model not to
  copy any; a secret scanner on the tier repo catches what slips through. PR bodies are not
  scanned.
- The model that runs a tier's dream reads everything the filter keeps. Pick it per tier.
