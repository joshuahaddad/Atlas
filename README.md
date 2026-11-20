# Atlas

Atlas is one repo for the agent tooling I write myself: skills, hooks, and larger kits that
used to live in separate repos. Each tool is a Claude Code plugin under `atlas/`,
and standard tools install it: Claude Code's `/plugin` and `npx skills`.


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
  morpheus/                 a plugin
    .claude-plugin/
      plugin.json           makes this folder a plugin
    skills/
      dream/
        SKILL.md            a skill
    hooks/hooks.json        hooks, if any
    .mcp.json               MCP servers, if any
check.sh                    checks the catalog against the plugins
```

A plugin with one skill can keep its `SKILL.md` at the plugin root instead of under `skills/`.
Hook and server commands name the plugin's own files with `${CLAUDE_PLUGIN_ROOT}`.

## Install

```bash
npx skills add joshuahaddad/Atlas -g                  # pick skills and harnesses
npx skills update -g                                  # pull new versions later
```

## Add a tool

1. Create a branch.
2. Add the folder with its `.claude-plugin/plugin.json`, and an entry in
   `.claude-plugin/marketplace.json`.
3. Run `./check.sh`. It fails when the catalog and the plugins disagree, then runs
   `claude plugin validate .`
4. Open a pull request.
