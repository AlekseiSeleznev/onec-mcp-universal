#!/bin/bash
# Install 1C skills for Claude Code
# Creates symlinks from ~/.claude/skills/ to the project's skills/ directory
# Usage: ./install-skills.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/skills"
SKILLS_DST="$HOME/.claude/skills"

if [ ! -d "$SKILLS_SRC" ]; then
    echo "ERROR: Skills directory not found: $SKILLS_SRC"
    exit 1
fi

mkdir -p "$SKILLS_DST"

installed=0
skipped=0
for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name=$(basename "$skill_dir")
    target="$SKILLS_DST/$skill_name"

    if [ -L "$target" ]; then
        # Symlink exists — update it
        rm "$target"
        ln -s "$skill_dir" "$target"
        installed=$((installed + 1))
    elif [ -d "$target" ]; then
        # Directory exists (not symlink) — skip
        echo "  SKIP $skill_name (directory exists, not a symlink)"
        skipped=$((skipped + 1))
    else
        ln -s "$skill_dir" "$target"
        installed=$((installed + 1))
    fi
done

echo ""
echo "Installed: $installed skills"
echo "Skipped:   $skipped skills"
echo "Location:  $SKILLS_DST"
echo ""
echo "Skills are now available in Claude Code via /command (e.g. /meta-compile, /epf-init)"
