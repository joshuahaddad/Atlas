#!/usr/bin/env bash
# Install Atlas tools for harnesses that don't read Claude Code plugins: link skills into
# ~/.agents/skills (OpenCode, Codex, Cursor) and add MCP servers to OpenCode. See README.md.
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)
command -v jq >/dev/null || { echo "install.sh needs jq" >&2; exit 1; }

# The catalog must list exactly the plugins in the repo, or Claude Code misses one.
listed=$(jq -r '.plugins[].source | ltrimstr("./")' "$root/.claude-plugin/marketplace.json" | sort)
found=$(git -C "$root" ls-files -- 'atlas/**/.claude-plugin/plugin.json' | sed 's|/.claude-plugin/plugin.json$||' | sort)
if [ "$listed" != "$found" ]; then
  echo "catalog out of date: .claude-plugin/marketplace.json must list each plugin under atlas/" >&2
  diff <(echo "$listed") <(echo "$found") | sed 's/^</  listed, no plugin.json:/; s/^>/  not listed:/' | grep '^ ' >&2
  exit 1
fi

mapfile -t defs < <(git -C "$root" ls-files -- atlas | grep -E '(^|/)(SKILL\.md|\.mcp\.json)$')
[ ${#defs[@]} -gt 0 ] || { echo "no skills or MCP servers found under atlas/" >&2; exit 1; }

# Every folder from atlas/ down to a tool, sorted so each folder sits above its children.
mapfile -t nodes < <(for d in "${defs[@]}"; do
  p=$(dirname "$d"); while [ "$p" != . ]; do echo "$p"; p=$(dirname "$p"); done
done | sort -u)

describe() {  # what the menu says after a folder that defines tools
  local dir=$1 out=""
  if [ -f "$root/$dir/SKILL.md" ]; then
    out="skill: $(sed -n '2,/^---$/{s/^description: *//p}' "$root/$dir/SKILL.md" | head -1)"
  fi
  [ -f "$root/$dir/.mcp.json" ] && out="$out [mcp]"
  echo "$out"
}

for i in "${!nodes[@]}"; do
  n=${nodes[$i]}; depth=$(( $(tr -cd / <<<"$n" | wc -c) ))
  line=$(printf '%3d  %*s%s/  %s' $((i + 1)) $((depth * 2)) '' "$(basename "$n")" "$(describe "$n")")
  echo "${line:0:${COLUMNS:-100}}"
done
read -rp "Install which? (numbers, space separated) " -a picks
[ ${#picks[@]} -gt 0 ] || exit 0

chosen=()
for k in "${picks[@]}"; do
  [[ $k =~ ^[0-9]+$ ]] && [ "$k" -ge 1 ] && [ "$k" -le ${#nodes[@]} ] || { echo "no such number: $k" >&2; exit 1; }
  for d in "${defs[@]}"; do [[ $d == "${nodes[$((k - 1))]}"/* ]] && chosen+=("$d"); done
done
mapfile -t chosen < <(printf '%s\n' "${chosen[@]}" | sort -u)

link_skill() {  # link_skill <tool dir> <skills dir>
  local src=$1 dest="$2/$(basename "$1")"
  mkdir -p "$2"
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    echo "  skip $dest: a real folder is there, not a link"; return
  fi
  [ -L "$dest" ] && [ "$(readlink "$dest")" != "$src" ] && echo "  replacing $dest -> $(readlink "$dest")"
  ln -sfn "$src" "$dest"; echo "  linked $dest"
}

add_opencode_servers() {  # add_opencode_servers <.mcp.json>, translated to OpenCode's format
  local file="$HOME/.config/opencode/opencode.json" tmp add
  # A plugin's server commands name its files with ${CLAUDE_PLUGIN_ROOT}.
  add=$(sed "s|\${CLAUDE_PLUGIN_ROOT}|$(dirname "$1")|g" "$1")
  mkdir -p "$(dirname "$file")"; [ -s "$file" ] || echo '{}' >"$file"
  tmp=$(mktemp "$file.XXXXXX")
  jq --argjson add "$add" '.mcp = ((.mcp // {}) + (($add.mcpServers // $add) | map_values(
    if .url then {type: "remote", url, headers: (.headers // {})}
    else {type: "local", command: ([.command] + (.args // [])), environment: (.env // {})} end)))' \
    "$file" >"$tmp" && mv "$tmp" "$file" || { rm -f "$tmp"; return 1; }
  echo "  servers -> $file"
}

for def in "${chosen[@]}"; do
  echo "$(basename "$(dirname "$def")") ($(basename "$def"))"
  case $def in
    */SKILL.md) link_skill "$root/$(dirname "$def")" "$HOME/.agents/skills" ;;
    */.mcp.json) add_opencode_servers "$root/$def" ;;
  esac
done
