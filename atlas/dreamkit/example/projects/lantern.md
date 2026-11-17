---
name: lantern
description: The command-line tool, how it relates to tidepool, and where its repo is
type: project
---
lantern is a command-line tool written in Go. It talks to tidepool's API and nothing else.

- Repo: `git.example.com/acme/lantern`. Its `AGENTS.md` has the build and test commands.
- Releases are tagged `vX.Y.Z`; tidepool pins a lantern tag, so a breaking API change needs both repos.
- See [Release process](../topics/release-process.md).
