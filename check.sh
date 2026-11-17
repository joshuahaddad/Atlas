#!/usr/bin/env bash
# The catalog must list exactly the plugins under atlas/: Claude Code and `npx skills` find tools only through it.
set -euo pipefail
cd "$(dirname "$0")"
listed=$(jq -r '.plugins[].source | ltrimstr("./")' .claude-plugin/marketplace.json | sort)
found=$(git ls-files -- 'atlas/**/.claude-plugin/plugin.json' | sed 's|/.claude-plugin/plugin.json$||' | sort)
if [ "$listed" != "$found" ]; then
  echo "catalog out of date (< listed without a plugin.json, > plugin not listed):" >&2
  diff <(echo "$listed") <(echo "$found") | grep '^[<>]' >&2
  exit 1
fi
claude plugin validate . >/dev/null && echo ok
