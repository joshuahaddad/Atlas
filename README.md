# Atlas

Atlas is one repo for the agent tooling I write myself: skills, hooks, and larger kits that
used to live in separate repos. Folders under `atlas/` nest freely, and the installer finds
each tool by the file that defines it.


## Why one repo

As I began to build tooling, I wanted to centralize some of the learnings and patterns into a single place instead of having many different locations. This repo follows the idea that current agents can use plain files and folders and do not need a complicated setup.

## Layout

All tooling lives under `atlas/`. Everything outside it, such as this README and
`install.sh`, is about the repo itself, and the installer never looks there.

```
atlas/
  writing/                  a folder that only groups
    figure-kit/             a kit: scripts, a Docker image, and its skill
      figure-loop/
        SKILL.md            makes this folder a skill
      ...
install.sh                  picks tools and installs them
```

## Discovery

The installer lists the files that git tracks under `atlas/` and looks for three names:

| File | Tool | The installer |
|---|---|---|
| `SKILL.md` | a skill | links the folder into each harness's skills folder |
| `hooks.json` | hooks | adds the hooks to each harness's settings |
| `.mcp.json` | MCP servers | adds the servers to each harness's config |

A tool's name is its folder name. The menu shows a skill's `description` from its frontmatter.
Untracked files, such as caches and build output, are never installed.

## Install

`install.sh` shows the folders under `atlas/` as a tree, with every tool it found. Pick a tool
to install it, or pick a folder to install every tool under it. Then pick the harnesses.

## Change a tool

1. Create a branch.
2. Change the folder.
3. Open a pull request.
