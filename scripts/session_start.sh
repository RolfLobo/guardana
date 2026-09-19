#!/usr/bin/env bash
# SessionStart hook: three lines of live state, so a session does not rediscover
# them with tool calls. Wired in .claude/settings.json.
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}" 2>/dev/null || exit 0

work=$(ls docs/work/*.md 2>/dev/null | grep -v -E '/(README|BACKLOG|TEMPLATE)\.md$' | xargs -n1 basename 2>/dev/null | tr '\n' ' ')
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
engines=""
command -v codex >/dev/null 2>&1 && engines="gpt(codex)"
command -v agy >/dev/null 2>&1 && engines="${engines:+$engines, }gemini(agy)"

echo "Work in flight (docs/work/): ${work:-none}"
echo "Uncommitted paths in the tree: ${dirty} — not all of them are yours; stage explicit paths only."
echo "Text engines for content-model: ${engines:-NONE INSTALLED — reader-facing wording cannot be produced in this session}"
exit 0
