# Atlas

Atlas is one repo for the agent tooling I write myself: skills, hooks, and larger kits that
used to live in separate repos. Folders under `atlas/` nest freely, and the installer finds
each tool by the file that defines it.


## Why one repo

As I began to build tooling, I wanted to centralize some of the learnings and patterns into a single place instead of having many different locations. This repo follows the idea that current agents can use plain files and folders and do not need a complicated setup.

## Layout

All tooling lives under `atlas/`, in folders that nest freely. Every tool is a Claude Code
plugin: a folder with `.claude-plugin/plugin.json`, holding any of skills, hooks and MCP
servers. The repo root is the plugin catalog, `.claude-plugin/marketplace.json`, which lists
each plugin by its path.

```
.claude-plugin/
  marketplace.json          the catalog: one entry per plugin under atlas/
atlas/
  dreamkit/                 a plugin
    .claude-plugin/
      plugin.json           makes this folder a plugin
    skills/
      dream/
        SKILL.md            a skill
    hooks/hooks.json        hooks, if any
    .mcp.json               MCP servers, if any
install.sh                  installs for harnesses other than Claude Code
```

A plugin with one skill can keep its `SKILL.md` at the plugin root instead of under `skills/`.
Hook and server commands name the plugin's own files with `${CLAUDE_PLUGIN_ROOT}`.

## Install

**Claude Code** reads the catalog directly and installs plugins through its `/plugin` menu,
hooks and MCP servers included:

```bash
claude plugin marketplace add ~/Atlas      # or joshuahaddad/Atlas
```

Then pick plugins in `/plugin`, or run `claude plugin install dreamkit@atlas`. Plugin skills
are named after their plugin, as in `/dreamkit:dream`. A catalog added from a local folder
reads the files in place, so edits load at the next session.

**OpenCode, Codex, Cursor and other harnesses** run `install.sh`. It shows the folders under
`atlas/` as a tree, with each skill and MCP config it found among the files git tracks. Pick a
tool, or a folder to take every tool under it. It links each skill into `~/.agents/skills`,
which all of them read, and adds MCP servers to OpenCode's `opencode.json`. Hooks are Claude
Code only: OpenCode takes hooks as JavaScript plugins. Rerunning it is safe.

## Add a tool

1. Create a branch.
2. Add the folder with its `.claude-plugin/plugin.json`, and an entry in
   `.claude-plugin/marketplace.json`. `install.sh` refuses to run while the two disagree.
3. Run `claude plugin validate .`
4. Open a pull request.
