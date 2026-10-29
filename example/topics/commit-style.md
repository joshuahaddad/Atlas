---
name: Commit style
description: How commits and pull requests are shaped across Acme repos
type: feedback
---
One pull request does one thing. A refactor and a behaviour change go in separate PRs.

**Why:** reviewers merge or reject a PR whole, so mixed PRs stall.

**How to apply:** if a task needs a refactor first, open it as its own PR and stack the change on it.
