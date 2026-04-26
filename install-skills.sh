#!/bin/bash
# Install 1C skills for Codex and compatible local skill runners.
# Creates symlinks from ~/.codex/skills/ to the project's skills/
# directory. The skill folders follow the shared SKILL.md convention.
#
# Usage: ./install-skills.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/skills"

if [ ! -d "$SKILLS_SRC" ]; then
    echo "ERROR: Skills directory not found: $SKILLS_SRC"
    exit 1
fi

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

TARGETS=()
# Codex: install unconditionally — ~/.codex is created on demand.
TARGETS+=("$CODEX_HOME/skills|Codex")

expected_skills=0
for skill_dir in "$SKILLS_SRC"/*/; do
    [ -f "$skill_dir/SKILL.md" ] || continue
    expected_skills=$((expected_skills + 1))
done

if [ "$expected_skills" -eq 0 ]; then
    echo "ERROR: No skills with SKILL.md found in $SKILLS_SRC"
    exit 1
fi

total_installed=0
for pair in "${TARGETS[@]}"; do
    dst="${pair%%|*}"
    label="${pair##*|}"
    mkdir -p "$dst"
    installed=0
    skipped=0
    for skill_dir in "$SKILLS_SRC"/*/; do
        [ -f "$skill_dir/SKILL.md" ] || continue
        skill_name=$(basename "$skill_dir")
        target="$dst/$skill_name"

        if [ -L "$target" ]; then
            rm "$target"
            ln -s "$skill_dir" "$target"
            installed=$((installed + 1))
        elif [ -d "$target" ]; then
            echo "  [$label] SKIP $skill_name (directory exists, not a symlink)"
            skipped=$((skipped + 1))
        else
            ln -s "$skill_dir" "$target"
            installed=$((installed + 1))
        fi
    done
    verified=0
    for skill_dir in "$SKILLS_SRC"/*/; do
        [ -f "$skill_dir/SKILL.md" ] || continue
        skill_name=$(basename "$skill_dir")
        target="$dst/$skill_name"
        [ -e "$target" ] || continue
        verified=$((verified + 1))
    done
    echo "[$label] Installed: $installed | Skipped: $skipped | Verified: $verified/$expected_skills | Location: $dst"
    if [ "$verified" -ne "$expected_skills" ]; then
        echo "ERROR: Skill installation verification failed for $label"
        exit 1
    fi
    total_installed=$((total_installed + installed))
done

echo ""
echo "Skills installed for Codex."
echo "Restart Codex to pick up newly installed or updated skills."
