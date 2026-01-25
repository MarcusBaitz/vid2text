#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
import shutil

print("=" * 60)
print("DIAGNOSE: Abhängigkeiten prüfen")
print("=" * 60)

# Python Version
print(f"\n✓ Python: {sys.version}")

# Torch
try:
    import torch
    print(f"✓ Torch: {torch.__version__}")
    print(f"  CUDA verfügbar: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
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
ytdlp_exe = Path("yt-dlp.exe")
if ytdlp_exe.exists():
    print(f"✓ yt-dlp.exe: {ytdlp_exe.absolute()}")
    result = subprocess.run([str(ytdlp_exe), "--version"], capture_output=True, text=True)
    print(f"  Version: {result.stdout.strip()}")
else:
    print(f"✗ yt-dlp.exe: NICHT GEFUNDEN in {Path.cwd()}")
    print("  Versuche mit pip-Installation:")
    try:
        result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
        print(f"  ✓ yt-dlp (pip): {result.stdout.strip()}")
    except:
        print("  ✗ yt-dlp (pip): NICHT GEFUNDEN")

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

if not ytdlp_exe.exists():
    print("\n2. yt-dlp herunterladen:")
    print("   https://github.com/yt-dlp/yt-dlp/releases")
    print("   Oder: pip install yt-dlp (und PATH aktualisieren)")

print("\n")
