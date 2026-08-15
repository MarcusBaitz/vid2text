#!/usr/bin/env python3
import argparse
import csv
import hashlib
import io
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import torch
import whisper

if isinstance(sys.stdout, io.TextIOBase) and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if isinstance(sys.stderr, io.TextIOBase) and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file to text using OpenAI Whisper."
    )
    parser.add_argument(
        "audio",
        nargs="?",
        help="Path to an audio file (e.g. .mp3).",
    )
    parser.add_argument(
        "--url",
        help="Video URL (e.g. YouTube or Loom) to download with yt-dlp before transcribing.",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="base",
        help="Whisper model size (tiny, base, small, medium, large). Default: base.",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu"],
        default=os.environ.get("VID2TEXT_DEVICE", "auto"),
        help=(
            "Execution device for Whisper (auto, cuda, cpu). Default: auto. "
            "Auto uses CUDA when available and falls back to CPU."
        ),
    )
    parser.add_argument(
        "-o",
        "--out",
        default=None,
        help="Output text file path. Default: <audio>.txt next to input.",
    )
    parser.add_argument(
        "--out-dir",
        default=os.environ.get("VID2TEXT_OUT_DIR"),
        help=(
            "Directory for generated files, keeping the automatic file name. "
            "Default: ./transcripts. Ignored when --out is given."
        ),
    )
    parser.add_argument(
        "--subtitles",
        default=os.environ.get("VID2TEXT_SUBTITLES"),
        help=(
            "Comma-separated subtitle formats to write next to the transcript "
            "(srt, vtt). Example: --subtitles srt,vtt"
        ),
    )
    parser.add_argument(
        "--subtitle-max-chars",
        type=int,
        default=int(os.environ.get("VID2TEXT_SUBTITLE_MAX_CHARS", "42")),
        help="Maximum characters per subtitle line (default: 42, max two lines per cue).",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Generate a concrete summary with an LLM after transcription.",
    )
    parser.add_argument(
        "--summary-out",
        default=None,
        help="Output file path for summary. Default: <transcript>.summary.md",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model name for summary (default from env VID2TEXT_LLM_MODEL or gpt-4o-mini).",
    )
    parser.add_argument(
        "--summary-prompt",
        default=(
            "Erstelle eine inhaltstreue deutsche Zusammenfassung, die den wichtigen Content "
            "und die eigentliche Botschaft des Transkripts erhaelt. Ziel: Ich soll verstehen, "
            "was der Sprecher vermitteln wollte, welche Argumente, Beispiele, Warnungen, "
            "Strategien und Schlussfolgerungen wichtig sind, und was ich praktisch daraus "
            "mitnehmen kann. Verdichte Wiederholungen, Smalltalk, Werbung und irrelevante "
            "Nebenbemerkungen, aber streiche keine fachlich relevanten Details, Bedingungen, "
            "Einschraenkungen, Zahlen, Namen, Begriffe, Prozessschritte oder Ursache-Wirkung-"
            "Zusammenhaenge. Wenn etwas nur angedeutet wird, kennzeichne es als Ableitung "
            "statt als Fakt. Erfinde nichts und nutze nur Inhalte, die aus dem Transkript "
            "ableitbar sind. Struktur: 1. Kurzueberblick, 2. Zentrale Botschaft, "
            "3. Wichtigste Inhalte und Argumente, 4. Konkrete Learnings/Handlungspunkte, "
            "5. Wichtige Details, Beispiele oder Einschraenkungen, 6. Merksatz."
        ),
        help="Custom instruction prompt for the summary.",
    )
    parser.add_argument(
        "--cookies-from-browser",
        default=os.environ.get("VID2TEXT_COOKIES_FROM_BROWSER"),
        help="Pass browser cookies to yt-dlp (e.g. chrome, edge, firefox).",
    )
    parser.add_argument(
        "--cookies",
        default=os.environ.get("VID2TEXT_COOKIES_FILE"),
        help="Path to a Netscape cookies.txt file for yt-dlp.",
    )
    parser.add_argument(
        "--cookies-browser-fallbacks",
        default=os.environ.get("VID2TEXT_COOKIES_BROWSER_FALLBACKS", "edge,firefox"),
        help="Fallback browsers when --cookies-from-browser fails (default: edge,firefox).",
    )
    parser.add_argument(
        "--yt-clients",
        default=os.environ.get("VID2TEXT_YT_CLIENTS", "android,tv"),
        help="Comma-separated YouTube player clients for fallback (default: android,tv).",
    )
    parser.add_argument(
        "--yt-js-runtimes",
        default=os.environ.get("VID2TEXT_YT_JS_RUNTIMES"),
        help="yt-dlp JavaScript runtimes (e.g. node or deno).",
    )
    return parser.parse_args()


DOWNLOAD_DIR = Path("downloads")
OUTPUT_TEMPLATE = str(DOWNLOAD_DIR / "%(id)s.%(ext)s")
PREFERRED_ENCODING = locale.getpreferredencoding(False)


def resolve_ytdlp_path() -> Path:
    script_dir = Path(__file__).resolve().parent
    local_names = ("yt-dlp.exe", "yt-dlp")
    for name in local_names:
        candidate = script_dir / name
        if candidate.exists():
            return candidate

    path_match = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if path_match:
        return Path(path_match)

    raise SystemExit(
        "yt-dlp not found. Run .\\run.ps1 on Windows or ./run.sh on Linux to set it up."
    )


def normalize_ytdlp_path(raw_path: str) -> Path:
    trimmed = raw_path.strip()
    if trimmed.startswith("\\\\wsl.localhost\\") or trimmed.startswith("\\wsl.localhost\\"):
        parts = trimmed.lstrip("\\").split("\\")
        if len(parts) >= 2:
            path_parts = parts[2:]
            return Path("/" + "/".join(path_parts))
    if "\\" in trimmed:
        trimmed = trimmed.replace("\\", "/")
    return Path(trimmed)


def ytdlp_cookie_option_sets(cli_args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    if cli_args.cookies:
        return [("cookies-file", ["--cookies", cli_args.cookies])]

    if not cli_args.cookies_from_browser:
        return [("no-cookies", [])]

    requested = cli_args.cookies_from_browser.strip()
    fallbacks = [
        browser.strip()
        for browser in cli_args.cookies_browser_fallbacks.split(",")
        if browser.strip()
    ]
    sources: list[str] = [requested]
    for browser in fallbacks:
        if browser.casefold() != requested.casefold() and browser not in sources:
            sources.append(browser)
    return [(f"cookies:{source}", ["--cookies-from-browser", source]) for source in sources]


def ytdlp_common_options(cli_args: argparse.Namespace) -> list[str]:
    options = ["--no-update"]
    if cli_args.yt_js_runtimes:
        options.extend(["--js-runtimes", cli_args.yt_js_runtimes])
    return options


def ytdlp_profiles(cli_args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    profiles: list[tuple[str, list[str]]] = [("default", [])]
    clients = [part.strip() for part in cli_args.yt_clients.split(",") if part.strip()]
    for client in clients:
        profiles.append(
            (
                f"player_client={client}",
                ["--extractor-args", f"youtube:player_client={client}"],
            )
        )
    return profiles


def run_ytdlp_with_fallback(
    *,
    yt_dlp_path: Path,
    cli_args: argparse.Namespace,
    action_args: list[str],
) -> tuple[subprocess.CompletedProcess[str], str]:
    common = ytdlp_common_options(cli_args)
    last_error = ""
    for cookie_name, cookie_args in ytdlp_cookie_option_sets(cli_args):
        for profile_name, profile_args in ytdlp_profiles(cli_args):
            cmd = [str(yt_dlp_path), *common, *cookie_args, *profile_args, *action_args]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding=PREFERRED_ENCODING,
                errors="surrogateescape",
            )
            if result.returncode == 0:
                return result, f"{cookie_name}|{profile_name}"
            stderr_text = (result.stderr or "").strip()
            if stderr_text:
                last_error = stderr_text

    if "Could not copy Chrome cookie database" in last_error:
        raise SystemExit(
            last_error
            + "\nHint: close Chrome completely and retry, or use --cookies-from-browser edge,"
            + " or pass --cookies <cookies.txt>."
        )
    if "Sign in to confirm you’re not a bot" in last_error or "Sign in to confirm you're not a bot" in last_error:
        raise SystemExit(
            last_error
            + "\nHint: retry with --cookies-from-browser chrome (or edge/firefox)."
        )
    raise SystemExit(
        last_error
        or "yt-dlp failed for all fallback profiles."
        + " Try --cookies-from-browser chrome (or edge/firefox)."
    )


def get_existing_audio_path(url: str, cli_args: argparse.Namespace) -> Path | None:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    yt_dlp_path = resolve_ytdlp_path()

    print("Checking for existing download...")
    action_args = [
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        OUTPUT_TEMPLATE,
        "--print",
        "filename",
        "--skip-download",
        url,
    ]
    result, profile_name = run_ytdlp_with_fallback(
        yt_dlp_path=yt_dlp_path,
        cli_args=cli_args,
        action_args=action_args,
    )
    if profile_name != "default":
        print(f"yt-dlp fallback profile used: {profile_name}")

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        return None

    audio_path = normalize_ytdlp_path(output_lines[-1])
    if audio_path.exists():
        return audio_path
    return None


def get_video_metadata(url: str, cli_args: argparse.Namespace) -> tuple[str, str]:
    yt_dlp_path = resolve_ytdlp_path()

    action_args = [
        "--print",
        "%(id)s\t%(title)s",
        "--skip-download",
        url,
    ]
    result, profile_name = run_ytdlp_with_fallback(
        yt_dlp_path=yt_dlp_path,
        cli_args=cli_args,
        action_args=action_args,
    )
    if profile_name != "default":
        print(f"yt-dlp fallback profile used: {profile_name}")

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise SystemExit("Could not read video metadata from yt-dlp.")

    video_id, _, title = output_lines[-1].partition("\t")
    if not video_id or not title:
        raise SystemExit("Could not parse video metadata (id/title).")
    return video_id.strip(), title.strip()


def title_hash(title: str) -> str:
    normalized = title.strip().casefold()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def append_video_index(
    *,
    url: str,
    video_id: str,
    title: str,
    title_digest: str,
    transcript_path: Path,
) -> None:
    out_dir = Path("transcripts")
    out_dir.mkdir(exist_ok=True)
    index_path = out_dir / "video_index.csv"
    file_exists = index_path.exists()

    with index_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                [
                    "timestamp_utc",
                    "hash",
                    "video_id",
                    "title",
                    "url",
                    "transcript",
                ]
            )
        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                title_digest,
                video_id,
                title,
                url,
                str(transcript_path),
            ]
        )


def load_dotenv_file(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def download_audio(url: str, cli_args: argparse.Namespace) -> tuple[Path, bool]:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    existing_path = get_existing_audio_path(url, cli_args)
    if existing_path:
        print(f"Using existing audio: {existing_path}")
        return existing_path, False

    yt_dlp_path = resolve_ytdlp_path()

    print("Downloading audio...")
    action_args = [
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        OUTPUT_TEMPLATE,
        "--print",
        "after_move:filepath",
        url,
    ]
    result, profile_name = run_ytdlp_with_fallback(
        yt_dlp_path=yt_dlp_path,
        cli_args=cli_args,
        action_args=action_args,
    )
    if profile_name != "default":
        print(f"yt-dlp fallback profile used: {profile_name}")

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise SystemExit("yt-dlp did not return a downloaded file path.")

    audio_path = normalize_ytdlp_path(output_lines[-1])
    if not audio_path.exists():
        raise SystemExit(f"Downloaded audio file not found: {audio_path}")
    return audio_path, True


def resolve_output_dir(out_dir_arg: str | None) -> Path:
    out_dir = Path(out_dir_arg).expanduser() if out_dir_arg else Path("transcripts")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def resolve_out_path(audio_path: Path, out_arg: str | None, out_dir_arg: str | None) -> Path:
    if out_arg:
        return Path(out_arg)
    return resolve_output_dir(out_dir_arg) / f"{audio_path.stem}.txt"


def resolve_url_out_path(
    out_arg: str | None,
    out_dir_arg: str | None,
    video_id: str,
    title_digest: str,
    title: str,
) -> Path:
    if out_arg:
        return Path(out_arg)
    out_dir = resolve_output_dir(out_dir_arg)
    title_stem = safe_stem(title)[:80].rstrip("._-") or "video"
    return out_dir / f"{title_stem}_{video_id}_{title_digest}.txt"


def resolve_summary_out_path(transcript_path: Path, summary_out_arg: str | None) -> Path:
    if summary_out_arg:
        return Path(summary_out_arg)
    return transcript_path.with_name(f"{transcript_path.stem}.summary.md")


def call_openai_chat_completion(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    data = json.dumps(payload).encode("utf-8")
    endpoint = base_url.rstrip("/") + "/v1/chat/completions"
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"LLM request failed ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"LLM request failed: {exc}") from exc

    parsed = json.loads(raw)
    try:
        content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit("LLM response format unexpected.") from exc
    if not content or not str(content).strip():
        raise SystemExit("LLM returned an empty summary.")
    return str(content).strip()


def summarize_with_llm(
    transcript_text: str,
    model: str,
    summary_prompt: str,
    original_title: str | None = None,
) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is missing. Add it to .env or environment.")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
    max_chars = int(os.environ.get("VID2TEXT_SUMMARY_MAX_CHARS", "30000"))
    text_for_model = transcript_text[:max_chars]
    if len(transcript_text) > max_chars:
        text_for_model += "\n\n[Hinweis: Transkript wurde für die Zusammenfassung gekürzt.]"

    title_instruction = ""
    title_context = ""
    if original_title:
        title_instruction = (
            "Beginne die Antwort mit einer Markdown-Ueberschrift, die den Originaltitel "
            "enthaelt und optional um eine kurze konkrete Einordnung ergaenzt. "
            "Verwende keinen rein generischen Titel wie 'Zusammenfassung'.\n\n"
        )
        title_context = f"Originaltitel: {original_title}\n\n"

    return call_openai_chat_completion(
        api_key=api_key,
        model=model,
        system_prompt=(
            "Du bist ein praeziser Analyse-Assistent fuer Transkript-Zusammenfassungen. "
            "Deine Prioritaet ist Inhaltstreue: Bewahre die beabsichtigte Botschaft, "
            "wichtige Argumente, Nuancen und umsetzbare Erkenntnisse. Verdichte, aber "
            "verflache den Inhalt nicht. Erfinde keine Informationen."
        ),
        user_prompt=(
            f"{title_instruction}{summary_prompt}\n\n"
            f"{title_context}Transkript:\n{text_for_model}"
        ),
        base_url=base_url,
    )


def safe_stem(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return sanitized or "audio"


def ensure_safe_name(path: Path) -> Path:
    safe_name = f"{safe_stem(path.stem)}{path.suffix}"
    if path.name == safe_name:
        return path
    target = path.with_name(safe_name)
    counter = 1
    while target.exists():
        target = path.with_name(f"{safe_stem(path.stem)}_{counter}{path.suffix}")
        counter += 1
    path.rename(target)
    return target


def get_audio_duration_seconds(audio_path: Path, ffprobe_path: str | None) -> float | None:
    if not ffprobe_path:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            encoding=PREFERRED_ENCODING,
            errors="surrogateescape",
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    duration_str = result.stdout.strip()
    if not duration_str:
        return None
    try:
        return float(duration_str)
    except ValueError:
        return None


SUBTITLE_FORMATS = ("srt", "vtt")


def parse_subtitle_formats(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    formats: list[str] = []
    for chunk in raw_value.replace(";", ",").split(","):
        name = chunk.strip().lower().lstrip(".")
        if not name:
            continue
        if name not in SUBTITLE_FORMATS:
            raise SystemExit(
                f"Unknown subtitle format: {name}. Supported: {', '.join(SUBTITLE_FORMATS)}."
            )
        if name not in formats:
            formats.append(name)
    return formats


def format_timestamp(seconds: float, use_comma: bool) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    separator = "," if use_comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def wrap_subtitle_text(text: str, max_chars: int) -> str:
    """Split a cue into at most two readable lines.

    Whisper segments are sentence-ish, so a single long line is common. Players
    render one endless line badly, and two balanced lines are the subtitling
    convention, so we only break when the text actually exceeds max_chars.
    """
    cleaned = " ".join(text.split())
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned

    words = cleaned.split(" ")
    best_index = None
    best_distance = None
    for index in range(1, len(words)):
        first = " ".join(words[:index])
        distance = abs(len(first) - len(cleaned) / 2)
        if len(first) > max_chars:
            break
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_index = index
    if not best_index:
        return cleaned
    return " ".join(words[:best_index]) + "\n" + " ".join(words[best_index:])


def render_subtitles(segments: list[dict], subtitle_format: str, max_chars: int) -> str:
    use_comma = subtitle_format == "srt"
    lines: list[str] = []
    if subtitle_format == "vtt":
        lines.append("WEBVTT")
        lines.append("")

    cue_number = 0
    previous_end = 0.0
    for segment in segments:
        text = wrap_subtitle_text(str(segment.get("text", "")), max_chars)
        if not text:
            continue
        cue_number += 1
        start = max(float(segment.get("start", 0.0)), previous_end)
        end = float(segment.get("end", start))
        if end <= start:
            end = start + 0.5
        previous_end = end
        if subtitle_format == "srt":
            lines.append(str(cue_number))
        lines.append(
            f"{format_timestamp(start, use_comma)} --> {format_timestamp(end, use_comma)}"
        )
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def write_subtitle_files(
    out_path: Path,
    segments: list[dict],
    formats: list[str],
    max_chars: int,
) -> list[Path]:
    if not formats:
        return []
    if not segments:
        print("No subtitle segments returned by Whisper; skipping subtitle files.")
        return []

    written: list[Path] = []
    for subtitle_format in formats:
        subtitle_path = out_path.with_suffix(f".{subtitle_format}")
        subtitle_path.write_text(
            render_subtitles(segments, subtitle_format, max_chars),
            encoding="utf-8",
        )
        print(f"Subtitles written: {subtitle_path}")
        written.append(subtitle_path)
    return written


def main() -> None:
    load_dotenv_file()
    args = parse_args()
    subtitle_formats = parse_subtitle_formats(args.subtitles)
    if args.audio and args.url:
        raise SystemExit("Provide either an audio file path or a URL, not both.")
    if not args.audio and not args.url:
        raise SystemExit("Provide an audio file path or a URL.")

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            winget_base = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
            if winget_base.exists():
                candidates = sorted(
                    winget_base.glob(
                        "Gyan.FFmpeg_*\\ffmpeg-*-full_build\\bin\\ffmpeg.exe"
                    )
                )
                if candidates:
                    ffmpeg_path = str(candidates[-1])
                    os.environ["PATH"] = f"{Path(ffmpeg_path).parent};{os.environ.get('PATH', '')}"
    if not ffmpeg_path:
        raise SystemExit(
            "ffmpeg not found. Install it (e.g. winget install -e --id Gyan.FFmpeg) "
            "and ensure it is on PATH."
        )
    print(f"ffmpeg: {ffmpeg_path}")
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        ffprobe_candidate = Path(ffmpeg_path).with_name("ffprobe.exe")
        if ffprobe_candidate.exists():
            ffprobe_path = str(ffprobe_candidate)

    if args.url:
        print("Input: URL")
        video_id, video_title = get_video_metadata(args.url, args)
        summary_title = video_title
        video_title_hash = title_hash(video_title)
        print(f"Video ID: {video_id}")
        print(f"Title: {video_title}")
        print(f"Title hash: {video_title_hash}")
        audio_path, downloaded = download_audio(args.url, args)
        if downloaded:
            print("Renaming downloaded audio to a safe name...")
            audio_path = ensure_safe_name(audio_path)
        out_path = resolve_url_out_path(
            args.out, args.out_dir, video_id, video_title_hash, video_title
        )
    else:
        print("Input: local file")
        audio_path = Path(args.audio)
        if not audio_path.exists():
            raise SystemExit(f"Audio file not found: {audio_path}")
        summary_title = audio_path.stem
        downloaded = False
        out_path = resolve_out_path(audio_path, args.out, args.out_dir)

    print(f"Output: {out_path}")

    if args.device == "cuda":
        if not torch.cuda.is_available():
            raise SystemExit("CUDA requested but none detected. Use --device cpu or --device auto.")
        device = "cuda"
    elif args.device == "cpu":
        device = "cpu"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"Using device: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("CPU fallback active (works, but is much slower than CUDA and not recommended for long files).")

    print(f"Loading Whisper model: {args.model}")
    model = whisper.load_model(args.model, device=device)
    print("Transcribing...")
    started_at = time.perf_counter()
    result = model.transcribe(str(audio_path))
    elapsed = time.perf_counter() - started_at
    text = result.get("text", "").strip()

    print("Writing transcript...")
    out_path.write_text(text + "\n", encoding="utf-8")

    if subtitle_formats:
        write_subtitle_files(
            out_path,
            result.get("segments") or [],
            subtitle_formats,
            args.subtitle_max_chars,
        )

    if args.summarize:
        if not text:
            raise SystemExit("Transcript is empty; cannot generate summary.")
        llm_model = args.llm_model or os.environ.get("VID2TEXT_LLM_MODEL", "gpt-4o-mini")
        print(f"Generating summary with model: {llm_model}")
        summary_text = summarize_with_llm(
            text,
            llm_model,
            args.summary_prompt,
            original_title=summary_title,
        )
        summary_out_path = resolve_summary_out_path(out_path, args.summary_out)
        summary_out_path.write_text(summary_text + "\n", encoding="utf-8")
        print(f"Summary written: {summary_out_path}")

    if args.url:
        append_video_index(
            url=args.url,
            video_id=video_id,
            title=video_title,
            title_digest=video_title_hash,
            transcript_path=out_path,
        )
        print("Video mapping saved: transcripts/video_index.csv")

    word_count = len(text.split())
    audio_duration = get_audio_duration_seconds(audio_path, ffprobe_path)
    print(f"Elapsed: {elapsed:.2f}s")
    if audio_duration:
        rtf = elapsed / audio_duration if audio_duration > 0 else 0.0
        print(f"Audio duration: {audio_duration:.2f}s")
        print(f"Real-time factor: {rtf:.2f}x")
    else:
        print("Audio duration: unknown")
        print("Real-time factor: n/a")
    print(f"Word count: {word_count}")

    if args.url and downloaded:
        print("Cleaning up downloaded audio...")
        try:
            audio_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
