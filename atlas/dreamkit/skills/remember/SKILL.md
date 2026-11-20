---
name: remember
description: Propose one fact, rule or preference to org memory as a small pull request on a tier repo. Use when the user says "remember this for every project", "add this to org memory", or "propose this to org memory".
---

# Remember

You propose one change to an org-memory tier repo. You never write its `base` branch; a human
merges or rejects the PR.

`$DREAM` below is the `dream` skill's folder, which holds the scripts and config reader.
Run them with `uv run`, or `python3` (3.11+) where uv isn't installed.

1. **Pick the tier.** Ask the user which tier, unless they said. Read it with
   `uv run "$DREAM/scripts/filter.py" --tier "$TIER" --show` and take `$REPO` and `$BASE`
   from it; if there is no config or no such tier, follow the dream skill's **Set up a tier**.
   If the content could be read by someone the tier is not meant for, say so and stop.
2. **Branch** from a clean, current clone:
   ```bash
   git -C "$REPO" status --porcelain    # must print nothing
   git -C "$REPO" fetch origin
   git -C "$REPO" switch -c "remember/<short-slug>" "origin/$BASE"
   ```
3. **Write one topic.** Never edit the repo's `dreamkit.toml`. Read `INDEX.md` first. If a page already covers the topic, edit it.
   Otherwise add one page in the folder the kit's `CONVENTIONS.md` names
   (`$(realpath "$DREAM")/../../CONVENTIONS.md`), with frontmatter `name`,
   `description`, `type`, and add the one line that links it from `INDEX.md` or a project page.
   Write it for a new agent: the rule, then **Why:** and **How to apply:**. No secrets.
4. **Check and commit:**
   ```bash
   uv run "$DREAM/scripts/check.py" "$REPO"    # must print "ok"
   git -C "$REPO" add -A && git -C "$REPO" commit -m "Remember: <title>"
   ```
5. **Open the PR.** Write a body with what changed, why, and where it came from (this session,
   in the user's words), then:
   ```bash
   uv run "$DREAM/scripts/open_pr.py" --tier "$TIER" --title "Remember: <title>" --body <body file>
   ```
   Give the user the link.
