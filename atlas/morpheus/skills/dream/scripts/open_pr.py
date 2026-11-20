# /// script
# requires-python = ">=3.11"
# ///
"""Run a tier's pr_command from its repo clone, on the branch that is checked out.

    uv run open_pr.py --tier org --title "Dream 2026-01-31" --body ~/.cache/morpheus/org-2026-01-31/pr.md

pr_command gets DREAM_TIER, DREAM_BRANCH, DREAM_BASE, DREAM_TITLE and DREAM_BODY_FILE.
"""

import argparse
import os
import subprocess
import sys

from filter import DEFAULT_CONFIG, load_tier


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--tier", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", required=True, help="a markdown file with the PR description")
    a = ap.parse_args()
    t = load_tier(a.config, a.tier)
    git = lambda *args: subprocess.run(["git", "-C", t["repo"], *args], capture_output=True, text=True, check=True).stdout.strip()
    branch = git("branch", "--show-current")
    if branch in ("", t["base"]):
        sys.exit(f"on {branch or 'a detached HEAD'}: commit the change on its own branch first")
    if git("status", "--porcelain"):
        sys.exit("the tier repo has uncommitted changes")
    env = os.environ | {"DREAM_TIER": a.tier, "DREAM_BRANCH": branch, "DREAM_BASE": t["base"],
                        "DREAM_TITLE": a.title, "DREAM_BODY_FILE": os.path.abspath(os.path.expanduser(a.body))}
    sys.exit(subprocess.run(t["pr_command"], shell=True, cwd=t["repo"], env=env).returncode)


if __name__ == "__main__":
    main()
