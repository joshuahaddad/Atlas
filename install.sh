#!/usr/bin/env bash
# Pick tools under atlas/ and install them into Claude Code and OpenCode. See README.md.
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)
command -v jq >/dev/null || { echo "install.sh needs jq" >&2; exit 1; }

mapfile -t defs < <(git -C "$root" ls-files -- atlas | grep -E '(^|/)(SKILL\.md|hooks\.json|\.mcp\.json)$')
[ ${#defs[@]} -gt 0 ] || { echo "no tools found under atlas/" >&2; exit 1; }

# Every folder from atlas/ down to a tool, sorted so each folder sits above its children.
mapfile -t nodes < <(for d in "${defs[@]}"; do
  p=$(dirname "$d"); while [ "$p" != . ]; do echo "$p"; p=$(dirname "$p"); done
done | sort -u)

describe() {  # what the menu says after a folder that defines tools
  local dir=$1 out=""
  if [ -f "$root/$dir/SKILL.md" ]; then
    out="skill: $(sed -n '2,/^---$/{s/^description: *//p}' "$root/$dir/SKILL.md" | head -1)"
  fi
  [ -f "$root/$dir/hooks.json" ] && out="$out [hooks]"
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

echo "  1  claude    (~/.claude)"
echo "  2  opencode  (~/.config/opencode)"
read -rp "Into which harnesses? (numbers) " -a harness_picks
harnesses=()
for h in "${harness_picks[@]}"; do
  case $h in 1) harnesses+=(claude) ;; 2) harnesses+=(opencode) ;; *) echo "no such harness: $h" >&2; exit 1 ;; esac
done

json_merge() {  # json_merge <file> <jq filter> <tool json>: rewrite file through filter, $add bound to the tool json
  local file=$1 filter=$2 add=$3 tmp
  mkdir -p "$(dirname "$file")"; [ -s "$file" ] || echo '{}' >"$file"
  tmp=$(mktemp "$file.XXXXXX")
  jq --argjson add "$add" "$filter" "$file" >"$tmp" && mv "$tmp" "$file" || { rm -f "$tmp"; return 1; }
}

link_skill() {  # link_skill <tool dir> <skills dir>
  local src=$1 dest="$2/$(basename "$1")"
  mkdir -p "$2"
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    echo "  skip $dest: a real folder is there, not a link"; return
  fi
  [ -L "$dest" ] && [ "$(readlink "$dest")" != "$src" ] && echo "  replacing $dest -> $(readlink "$dest")"
  ln -sfn "$src" "$dest"; echo "  linked $dest"
}

# Appends hook groups that aren't already there, so a second run changes nothing.
hooks_filter='.hooks //= {} | reduce ($add.hooks | to_entries[]) as $e (.;
  .hooks[$e.key] = ((.hooks[$e.key] // []) as $o | $o + [$e.value[] | select(IN($o[]) | not)]))'
claude_mcp_filter='.mcpServers = ((.mcpServers // {}) + $add.mcpServers)'
opencode_mcp_filter='.mcp = ((.mcp // {}) + ($add.mcpServers | map_values(
  if .url then {type: "remote", url, headers: (.headers // {})}
  else {type: "local", command: ([.command] + (.args // [])), environment: (.env // {})} end)))'

for def in "${chosen[@]}"; do
  dir="$root/$(dirname "$def")"
  echo "$(basename "$dir") ($(basename "$def"))"
  # Hook and server commands name their files with ${CLAUDE_PLUGIN_ROOT}, as in a Claude Code plugin.
  [[ $def == *.json ]] && add=$(sed "s|\${CLAUDE_PLUGIN_ROOT}|$dir|g" "$root/$def")
  for h in "${harnesses[@]}"; do
    case "$h $(basename "$def")" in
      "claude SKILL.md")     link_skill "$dir" "$HOME/.claude/skills" ;;
      "opencode SKILL.md")   link_skill "$dir" "$HOME/.config/opencode/skills" ;;
      "claude hooks.json")   json_merge "$HOME/.claude/settings.json" "$hooks_filter" "$add" && echo "  hooks -> ~/.claude/settings.json" ;;
      "opencode hooks.json") echo "  skip: OpenCode takes hooks as JS plugins, not hooks.json" ;;
      "claude .mcp.json")    json_merge "$HOME/.claude.json" "$claude_mcp_filter" "$add" && echo "  servers -> ~/.claude.json" ;;
      "opencode .mcp.json")  json_merge "$HOME/.config/opencode/opencode.json" "$opencode_mcp_filter" "$add" && echo "  servers -> ~/.config/opencode/opencode.json" ;;
    esac
  done
done
