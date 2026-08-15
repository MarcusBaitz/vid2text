#!/usr/bin/env bash
# Installiert den Skill "video-zu-text" global fuer Claude Code.
#
# Global heisst: der Skill liegt unter ~/.claude/skills und steht damit in
# jedem Projekt zur Verfuegung, nicht nur in diesem Repository.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/.claude/skills/video-zu-text"
TARGET_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
TARGET="$TARGET_DIR/video-zu-text"
MODE="link"

usage() {
  cat <<'EOF'
Verwendung: ./install-skill.sh [--copy] [--link] [--uninstall]

  --link       Symlink auf dieses Repository (Standard, bleibt automatisch aktuell)
  --copy       Dateien kopieren (fuer Rechner ohne Symlink-Unterstuetzung)
  --uninstall  Global installierten Skill wieder entfernen
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy) MODE="copy"; shift ;;
    --link) MODE="link"; shift ;;
    --uninstall) MODE="uninstall"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unbekannte Option: %s\n\n' "$1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ "$MODE" == "uninstall" ]]; then
  if [[ -e "$TARGET" || -L "$TARGET" ]]; then
    rm -rf "$TARGET"
    printf 'Entfernt: %s\n' "$TARGET"
  else
    printf 'Nichts zu entfernen unter %s\n' "$TARGET"
  fi
  exit 0
fi

[[ -f "$SOURCE/SKILL.md" ]] || { printf 'Fehler: %s/SKILL.md fehlt.\n' "$SOURCE" >&2; exit 1; }

mkdir -p "$TARGET_DIR"
[[ ! -e "$TARGET" && ! -L "$TARGET" ]] || rm -rf "$TARGET"

if [[ "$MODE" == "link" ]]; then
  ln -s "$SOURCE" "$TARGET"
  printf 'Symlink erstellt: %s -> %s\n' "$TARGET" "$SOURCE"
else
  cp -r "$SOURCE" "$TARGET"
  printf 'Kopiert: %s -> %s\n' "$SOURCE" "$TARGET"
fi

chmod +x "$SOURCE/scripts/vid2text.sh" 2>/dev/null || true

# Merken, wo vid2text liegt, damit der Skill das Repo spaeter nicht suchen muss.
printf '%s\n' "$ROOT" > "$TARGET/.vid2text-home" 2>/dev/null || true

cat <<EOF

Fertig. Der Skill ist jetzt global verfuegbar.
vid2text-Repository: $ROOT

Naechster Schritt: neue Claude-Code-Sitzung starten und z. B. sagen:
  "Erstelle Untertitel fuer https://www.youtube.com/watch?v=..."
EOF
