#!/usr/bin/env bash
# Wrapper around the vid2text repository so the skill works from any directory.
#
# It resolves where vid2text lives, bootstraps it if necessary, and then hands
# over to the repo's own run.sh (which sets up .venv, yt-dlp and ffmpeg).
# Output always lands in the caller's working directory unless --out-dir says
# otherwise, because a transcript is useless if it disappears into a checkout
# the user never looks at.
set -Eeuo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_URL="${VID2TEXT_REPO_URL:-https://github.com/MarcusBaitz/vid2text.git}"
HOME_FILE="$SKILL_DIR/.vid2text-home"

info() { printf '==> %s\n' "$1" >&2; }
die() { printf 'Fehler: %s\n' "$1" >&2; exit 1; }

is_vid2text_repo() {
  [[ -n "${1:-}" && -f "$1/transcribe_whisper.py" && -f "$1/run.sh" ]]
}

remember_home() {
  printf '%s\n' "$1" > "$HOME_FILE" 2>/dev/null || true
}

resolve_home() {
  local candidate

  # 1. Explicit override wins.
  if is_vid2text_repo "${VID2TEXT_HOME:-}"; then
    printf '%s\n' "$VID2TEXT_HOME"
    return
  fi

  # 2. Remembered location from a previous run.
  if [[ -f "$HOME_FILE" ]]; then
    candidate="$(head -n 1 "$HOME_FILE")"
    if is_vid2text_repo "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  fi

  # 3. The skill may live inside the repo itself (.claude/skills/video-zu-text).
  candidate="$(cd "$SKILL_DIR/../../.." 2>/dev/null && pwd || true)"
  if is_vid2text_repo "$candidate"; then
    printf '%s\n' "$candidate"
    return
  fi

  # 4. The current project, or common checkout locations.
  for candidate in "$PWD" "$HOME/vid2text" "$HOME/projects/vid2text" \
    "$HOME/Projekte/vid2text" "$HOME/git/vid2text" "$HOME/code/vid2text" \
    "$HOME/src/vid2text" "$HOME/Documents/vid2text" "$HOME/.vid2text"; do
    if is_vid2text_repo "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  # 5. Nothing found: fetch a private copy under $HOME/.vid2text.
  [[ "${VID2TEXT_NO_CLONE:-0}" != "1" ]] || die \
    "vid2text wurde nicht gefunden und VID2TEXT_NO_CLONE=1 verbietet das Klonen. Setze VID2TEXT_HOME auf dein Repository."
  command -v git >/dev/null 2>&1 || die "vid2text wurde nicht gefunden und git ist nicht installiert. Setze VID2TEXT_HOME auf dein Repository."

  info "vid2text wurde nicht gefunden. Klone $REPO_URL nach $HOME/.vid2text"
  git clone --depth 1 "$REPO_URL" "$HOME/.vid2text" >&2 \
    || die "Klonen fehlgeschlagen. Setze VID2TEXT_HOME manuell auf dein vid2text-Verzeichnis."
  is_vid2text_repo "$HOME/.vid2text" || die "Der Klon enthaelt kein vid2text."
  printf '%s\n' "$HOME/.vid2text"
}

CALLER_PWD="$PWD"
ARGS=()
PASSTHROUGH=()
HAS_OUT_DIR=0
HAS_OUT=0

# Flags run.sh understands itself; everything else has to travel behind "--",
# because run.sh would otherwise mistake an option value for the input path.
KNOWN_VALUE_FLAGS=" --url --model -m --device --out --out-dir --summary-out --subtitles --cookies-from-browser --cookies "
KNOWN_SWITCHES=" --summarize --diagnose --skip-install "

# Make user-supplied paths absolute before run.sh cd's into the repo, otherwise
# relative paths would silently resolve against the checkout.
absolutize() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    ~*) printf '%s\n' "${1/#\~/$HOME}" ;;
    *) printf '%s\n' "$CALLER_PWD/$1" ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir)
      [[ -n "${2:-}" ]] || die "--out-dir braucht einen Wert."
      ARGS+=(--out-dir "$(absolutize "$2")")
      HAS_OUT_DIR=1
      shift 2
      ;;
    --out|--summary-out|--cookies)
      [[ -n "${2:-}" ]] || die "$1 braucht einen Wert."
      [[ "$1" == "--out" ]] && HAS_OUT=1
      ARGS+=("$1" "$(absolutize "$2")")
      shift 2
      ;;
    --)
      shift
      PASSTHROUGH+=("$@")
      break
      ;;
    -*)
      if [[ "$KNOWN_VALUE_FLAGS" == *" $1 "* ]]; then
        [[ -n "${2:-}" ]] || die "$1 braucht einen Wert."
        ARGS+=("$1" "$2")
        shift 2
      elif [[ "$KNOWN_SWITCHES" == *" $1 "* ]]; then
        ARGS+=("$1")
        shift
      else
        # Unknown flag: hand it plus its value straight to transcribe_whisper.py.
        PASSTHROUGH+=("$1")
        shift
        if [[ $# -gt 0 && "$1" != -* ]]; then
          PASSTHROUGH+=("$1")
          shift
        fi
      fi
      ;;
    *)
      # Local media files are positional; make those absolute too.
      if [[ -e "$1" ]]; then
        ARGS+=("$(absolutize "$1")")
      else
        ARGS+=("$1")
      fi
      shift
      ;;
  esac
done

[[ "${#ARGS[@]}" -gt 0 ]] || die 'Bitte gib eine URL oder eine Mediendatei an. Beispiel: vid2text.sh "https://..." --subtitles srt'

VID2TEXT_ROOT="$(resolve_home)"
remember_home "$VID2TEXT_ROOT"
info "vid2text: $VID2TEXT_ROOT"

# An older checkout may predate these flags. run.sh would then treat the flag
# value as the input file, so refuse loudly instead of transcribing the wrong
# thing.
supports_flag() {
  grep -q -- "$1" "$VID2TEXT_ROOT/run.sh"
}

for flag in --subtitles --out-dir; do
  if printf '%s\n' "${ARGS[@]}" | grep -qx -- "$flag" && ! supports_flag "$flag"; then
    die "Das gefundene vid2text unter $VID2TEXT_ROOT kennt $flag noch nicht. Aktualisiere es mit: git -C \"$VID2TEXT_ROOT\" pull"
  fi
done

if [[ "$HAS_OUT_DIR" -eq 0 && "$HAS_OUT" -eq 0 ]] && supports_flag --out-dir; then
  ARGS+=(--out-dir "$CALLER_PWD/transcripts")
fi

if [[ "${#PASSTHROUGH[@]}" -gt 0 ]]; then
  ARGS+=(-- "${PASSTHROUGH[@]}")
fi

exec bash "$VID2TEXT_ROOT/run.sh" "${ARGS[@]}"
