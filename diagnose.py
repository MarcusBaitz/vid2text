#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
import shutil

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

print("=" * 60)
print("DIAGNOSE: Abhängigkeiten prüfen")
print("=" * 60)

# Python Version
print(f"\n✓ Python: {sys.version}")

# Torch
try:
    import torch
    print(f"✓ Torch: {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    print(f"  CUDA verfügbar: {cuda_available}")
    if cuda_available:
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
        print("  Empfehlung: CUDA/GPU wird automatisch genutzt.")
    else:
        print("  Hinweis: CPU-Fallback ist moeglich, aber deutlich langsamer und nicht empfohlen fuer lange Dateien.")
except ImportError as e:
    print(f"✗ Torch: {e}")

# Whisper
try:
    import whisper
    print(f"✓ Whisper: installiert")
except ImportError as e:
    print(f"✗ Whisper: {e}")

# ffmpeg
print("\n--- FFmpeg ---")
ffmpeg_path = shutil.which("ffmpeg")
ffprobe_path = shutil.which("ffprobe")
if ffmpeg_path:
    print(f"✓ ffmpeg: {ffmpeg_path}")
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    version_line = result.stdout.split('\n')[0]
    print(f"  {version_line}")
else:
    print("✗ ffmpeg: NICHT GEFUNDEN im PATH")
    print("  Überprüfe: $env:PATH")
    
if ffprobe_path:
    print(f"✓ ffprobe: {ffprobe_path}")
else:
    print("✗ ffprobe: NICHT GEFUNDEN im PATH")

# yt-dlp
print("\n--- yt-dlp ---")
local_ytdlp = next(
    (candidate for candidate in (Path("yt-dlp.exe"), Path("yt-dlp")) if candidate.exists()),
    None,
)
path_ytdlp = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
if local_ytdlp:
    print(f"✓ yt-dlp: {local_ytdlp.absolute()}")
    result = subprocess.run([str(local_ytdlp), "--version"], capture_output=True, text=True)
    print(f"  Version: {result.stdout.strip()}")
elif path_ytdlp:
    print(f"✓ yt-dlp: {path_ytdlp}")
    result = subprocess.run([path_ytdlp, "--version"], capture_output=True, text=True)
    print(f"  Version: {result.stdout.strip()}")
else:
    print(f"✗ yt-dlp: NICHT GEFUNDEN in {Path.cwd()} oder PATH")

# PATH prüfen
print("\n--- System PATH ---")
paths = sys.executable.split(';')
print(f"Python executable: {sys.executable}")
print(f"Venv Pfad: {Path(sys.executable).parent}")

print("\n" + "=" * 60)
print("EMPFEHLUNGEN:")
print("=" * 60)
if not ffmpeg_path:
    print("\n1. FFmpeg installieren:")
    print("   PowerShell als Admin:")
    print("   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser")
    print("   iwr -useb get.scoop.sh | iex")
    print("   scoop install ffmpeg")
    print("\n   ODER:")
    print("   choco install ffmpeg -y  (mit Admin-Rechten)")

if not local_ytdlp and not path_ytdlp:
    print("\n2. yt-dlp herunterladen:")
    print("   https://github.com/yt-dlp/yt-dlp/releases")
    print("   Oder: pip install yt-dlp (und PATH aktualisieren)")

print("\n")
