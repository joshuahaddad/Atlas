# Conventions for a tier repo

A tier repo holds what crosses projects: people's preferences and style, how projects relate,
and domains with no repo of their own. A project's detail stays in that project's repo.

## Layout

```
INDEX.md               loaded into every session; short
projects/<name>.md     one page per project: what it is, how it relates to the others, where its repo is
topics/<topic>.md      a preference, rule or fact that crosses projects
domains/<name>/*.md    optional: a subject with several pages and no repo
```

Each level links to the next: `INDEX.md` links project and topic pages; a project page links
topic pages and the project's own `AGENTS.md`. Every page must be reachable from `INDEX.md`.

## INDEX.md

- At most 60 lines (`check.py --max-lines` changes it). Tools load it whole into every session.
- One line per link, saying when to open the page, not what it says.
- No frontmatter.

## Pages

Plain markdown, readable by any tool: no tool-specific syntax such as `@imports`. Every page
but `INDEX.md` and a root `README.md` starts with frontmatter:

```markdown
---
name: Commit style
description: How commits and pull requests are shaped across our repos
type: feedback
---
One pull request does one thing.

**Why:** reviewers merge or reject a PR whole.

**How to apply:** open a refactor as its own PR and stack the change on it.
```

| `type` | For |
|---|---|
| `user` | who the people are and how they like to work |
| `feedback` | a rule learned from a correction: the rule, then **Why:** and **How to apply:** |
| `project` | a project page, or a fact about how projects relate |
| `reference` | a fact to look up: a command, an address, a process |

Write each page for a new agent. Leave out history, session ids and how the fact was learned;
those belong in the PR that added it. Never put a secret in a page.

## Changes

Only through pull requests, reviewed by a human: from `dream`, from `remember`, or by hand.
Run `uv run skills/dream/scripts/check.py <repo>` before opening one.
