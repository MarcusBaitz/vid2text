#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PYTHONUTF8=1

INPUT=""
URL=""
SUMMARIZE=0
MODEL="${WHISPER_MODEL:-base}"
DEVICE="${VID2TEXT_DEVICE:-auto}"
OUT=""
OUT_DIR="${VID2TEXT_OUT_DIR:-}"
SUMMARY_OUT=""
COOKIES_FROM_BROWSER="${VID2TEXT_COOKIES_FROM_BROWSER:-}"
COOKIES="${VID2TEXT_COOKIES_FILE:-}"
SUBTITLES="${VID2TEXT_SUBTITLES:-}"
DIAGNOSE=0
SKIP_INSTALL=0
EXTRA_ARGS=()

step() {
  printf '\n==> %s\n' "$1" >&2
}

die() {
  printf '\nFehler: %s\n' "$1" >&2
  exit 1
}

need_value() {
  local name="$1"
  local value="${2:-}"
  [[ -n "$value" ]] || die "$name braucht einen Wert."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      need_value "$1" "${2:-}"
      URL="$2"
      shift 2
      ;;
    --summarize|-Summarize)
      SUMMARIZE=1
      shift
      ;;
    --model|-Model|-m)
      need_value "$1" "${2:-}"
      MODEL="$2"
      shift 2
      ;;
    --device|-Device)
      need_value "$1" "${2:-}"
      DEVICE="$2"
      shift 2
      ;;
    --out|-Out|-o)
      need_value "$1" "${2:-}"
      OUT="$2"
      shift 2
      ;;
    --out-dir|-OutDir)
      need_value "$1" "${2:-}"
      OUT_DIR="$2"
      shift 2
      ;;
    --summary-out|-SummaryOut)
      need_value "$1" "${2:-}"
      SUMMARY_OUT="$2"
      shift 2
      ;;
    --subtitles|-Subtitles)
      need_value "$1" "${2:-}"
      SUBTITLES="$2"
      shift 2
      ;;
    --cookies-from-browser|-CookiesFromBrowser)
      need_value "$1" "${2:-}"
      COOKIES_FROM_BROWSER="$2"
      shift 2
      ;;
    --cookies|-Cookies)
      need_value "$1" "${2:-}"
      COOKIES="$2"
      shift 2
      ;;
    --diagnose|-Diagnose)
      DIAGNOSE=1
      shift
      ;;
    --skip-install|-SkipInstall)
      SKIP_INSTALL=1
      shift
      ;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break
      ;;
    -*)
      EXTRA_ARGS+=("$1")
      shift
      ;;
    *)
      if [[ -z "$INPUT" ]]; then
        INPUT="$1"
      else
        EXTRA_ARGS+=("$1")
      fi
      shift
      ;;
  esac
done

find_python() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    printf '%s\n' "$ROOT/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  die "Python wurde nicht gefunden. Installiere Python 3 und starte den Befehl erneut."
}

ensure_venv() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    printf '%s\n' "$ROOT/.venv/bin/python"
    return
  fi

  step "Virtuelle Umgebung wird erstellt"
  local base_python
  base_python="$(find_python)"
  "$base_python" -m venv "$ROOT/.venv" || die "Konnte .venv nicht erstellen. Auf Debian/Ubuntu fehlt eventuell python3-venv."

  [[ -x "$ROOT/.venv/bin/python" ]] || die "Die virtuelle Umgebung konnte nicht erstellt werden."
  printf '%s\n' "$ROOT/.venv/bin/python"
}

ensure_python_dependencies() {
  local python_exe="$1"
  if [[ "$SKIP_INSTALL" -eq 1 ]]; then
    step "Python-Installation wird uebersprungen (--skip-install)"
    return
  fi

  step "Python-Abhaengigkeiten werden installiert/aktualisiert"
  "$python_exe" -m pip install --upgrade pip
  "$python_exe" -m pip install -r "$ROOT/requirements.txt"
}

ensure_ytdlp() {
  if [[ -x "$ROOT/yt-dlp" || -f "$ROOT/yt-dlp.exe" || -n "$(command -v yt-dlp || true)" ]]; then
    return
  fi
  [[ "$SKIP_INSTALL" -eq 0 ]] || die "yt-dlp wurde nicht gefunden. Entferne --skip-install oder installiere yt-dlp manuell."

  step "yt-dlp wird heruntergeladen"
  local target="$ROOT/yt-dlp"
  local url="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
  if command -v curl >/dev/null 2>&1; then
    curl -L "$url" -o "$target"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$target" "$url"
  else
    die "curl oder wget wird benoetigt, um yt-dlp herunterzuladen."
  fi
  chmod +x "$target"
}

ensure_ffmpeg() {
  if command -v ffmpeg >/dev/null 2>&1; then
    return
  fi
  [[ "$SKIP_INSTALL" -eq 0 ]] || die "ffmpeg wurde nicht gefunden. Entferne --skip-install oder installiere ffmpeg manuell."

  if command -v apt-get >/dev/null 2>&1; then
    step "FFmpeg wird ueber apt installiert"
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
      apt-get update
      apt-get install -y ffmpeg
    elif command -v sudo >/dev/null 2>&1; then
      sudo apt-get update
      sudo apt-get install -y ffmpeg
    else
      die "ffmpeg fehlt und sudo ist nicht verfuegbar. Installiere ffmpeg manuell."
    fi
    return
  fi

  die "ffmpeg fehlt. Installiere es mit dem Paketmanager deiner Distribution, z. B. sudo apt install ffmpeg."
}

build_transcribe_args() {
  TRANSCRIBE_ARGS=()
  if [[ -n "$URL" ]]; then
    TRANSCRIBE_ARGS+=(--url "$URL")
  elif [[ "$INPUT" =~ ^https?:// ]]; then
    TRANSCRIBE_ARGS+=(--url "$INPUT")
  elif [[ -n "$INPUT" ]]; then
    TRANSCRIBE_ARGS+=("$INPUT")
  elif [[ "$DIAGNOSE" -eq 0 ]]; then
    die 'Bitte gib eine URL oder Audiodatei an. Beispiel: ./run.sh "https://www.youtube.com/watch?v=..." --summarize'
  fi

  TRANSCRIBE_ARGS+=(--model "$MODEL" --device "$DEVICE")
  [[ "$SUMMARIZE" -eq 1 ]] && TRANSCRIBE_ARGS+=(--summarize)
  [[ -n "$OUT" ]] && TRANSCRIBE_ARGS+=(--out "$OUT")
  [[ -n "$OUT_DIR" ]] && TRANSCRIBE_ARGS+=(--out-dir "$OUT_DIR")
  [[ -n "$SUMMARY_OUT" ]] && TRANSCRIBE_ARGS+=(--summary-out "$SUMMARY_OUT")
  [[ -n "$SUBTITLES" ]] && TRANSCRIBE_ARGS+=(--subtitles "$SUBTITLES")
  [[ -n "$COOKIES_FROM_BROWSER" ]] && TRANSCRIBE_ARGS+=(--cookies-from-browser "$COOKIES_FROM_BROWSER")
  [[ -n "$COOKIES" ]] && TRANSCRIBE_ARGS+=(--cookies "$COOKIES")
  [[ "${#EXTRA_ARGS[@]}" -gt 0 ]] && TRANSCRIBE_ARGS+=("${EXTRA_ARGS[@]}")
}

mkdir -p "$ROOT/downloads" "$ROOT/transcripts"

PYTHON_EXE="$(ensure_venv)"
ensure_python_dependencies "$PYTHON_EXE"
ensure_ytdlp
ensure_ffmpeg

if [[ "$DIAGNOSE" -eq 1 ]]; then
  step "Diagnose wird ausgefuehrt"
  exec "$PYTHON_EXE" "$ROOT/diagnose.py"
fi

build_transcribe_args
step "Transkription wird gestartet"
exec "$PYTHON_EXE" "$ROOT/transcribe_whisper.py" "${TRANSCRIBE_ARGS[@]}"
