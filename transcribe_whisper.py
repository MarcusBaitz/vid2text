#!/usr/bin/env python3
import argparse
import locale
import re
import subprocess
from pathlib import Path

import whisper


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
        "-o",
        "--out",
        default=None,
        help="Output text file path. Default: <audio>.txt next to input.",
    )
    return parser.parse_args()


OUTPUT_TEMPLATE = "%(id)s.%(ext)s"
PREFERRED_ENCODING = locale.getpreferredencoding(False)


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


def get_existing_audio_path(url: str) -> Path | None:
    yt_dlp_path = Path(__file__).with_name("yt-dlp.exe")
    if not yt_dlp_path.exists():
        raise SystemExit(f"yt-dlp.exe not found next to script: {yt_dlp_path}")

    print("Checking for existing download...")
    cmd = [
        str(yt_dlp_path),
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
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding=PREFERRED_ENCODING,
        errors="surrogateescape",
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "yt-dlp failed.")

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        return None

    audio_path = normalize_ytdlp_path(output_lines[-1])
    if audio_path.exists():
        return audio_path
    return None


def download_audio(url: str) -> tuple[Path, bool]:
    existing_path = get_existing_audio_path(url)
    if existing_path:
        print(f"Using existing audio: {existing_path}")
        return existing_path, False

    yt_dlp_path = Path(__file__).with_name("yt-dlp.exe")
    if not yt_dlp_path.exists():
        raise SystemExit(f"yt-dlp.exe not found next to script: {yt_dlp_path}")

    print("Downloading audio...")
    cmd = [
        str(yt_dlp_path),
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        OUTPUT_TEMPLATE,
        "--print",
        "after_move:filepath",
        url,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding=PREFERRED_ENCODING,
        errors="surrogateescape",
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "yt-dlp failed.")

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise SystemExit("yt-dlp did not return a downloaded file path.")

    audio_path = normalize_ytdlp_path(output_lines[-1])
    if not audio_path.exists():
        raise SystemExit(f"Downloaded audio file not found: {audio_path}")
    return audio_path, True


def resolve_out_path(audio_path: Path, out_arg: str | None) -> Path:
    if out_arg:
        return Path(out_arg)
    out_dir = Path("transcripts")
    out_dir.mkdir(exist_ok=True)
    return out_dir / f"{audio_path.stem}.txt"


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


def main() -> None:
    args = parse_args()
    if args.audio and args.url:
        raise SystemExit("Provide either an audio file path or a URL, not both.")
    if not args.audio and not args.url:
        raise SystemExit("Provide an audio file path or a URL.")

    if args.url:
        print("Input: URL")
        audio_path, downloaded = download_audio(args.url)
        if downloaded:
            print("Renaming downloaded audio to a safe name...")
            audio_path = ensure_safe_name(audio_path)
    else:
        print("Input: local file")
        audio_path = Path(args.audio)
        if not audio_path.exists():
            raise SystemExit(f"Audio file not found: {audio_path}")
        downloaded = False

    out_path = resolve_out_path(audio_path, args.out)
    print(f"Output: {out_path}")

    print(f"Loading Whisper model: {args.model}")
    model = whisper.load_model(args.model)
    print("Transcribing...")
    result = model.transcribe(str(audio_path))
    text = result.get("text", "").strip()

    print("Writing transcript...")
    out_path.write_text(text + "\n", encoding="utf-8")
    print(text)

    if args.url and downloaded:
        print("Cleaning up downloaded audio...")
        try:
            audio_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
