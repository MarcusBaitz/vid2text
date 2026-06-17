# vid2text

Transkribiert lokale Audiodateien oder Video-URLs mit Whisper. Optional wird danach automatisch eine kurze deutsche Lernzusammenfassung per LLM erzeugt.

## Schnellstart: ein Befehl

UI unter Windows im Projektordner:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_ui.ps1
```

Danach ist die Oberflaeche unter `http://127.0.0.1:7860` erreichbar. Sie bietet Datei-Upload, Video-Link-Eingabe, Status-Logs und Ergebnisanzeige.

UI unter Linux im Projektordner:

```bash
bash ./start_ui.sh
```

Windows im Projektordner:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 "https://www.youtube.com/watch?v=..." -Summarize
```

Linux im Projektordner:

```bash
bash ./run.sh "https://www.youtube.com/watch?v=..." --summarize
```

Das erledigt automatisch:

- erstellt `.venv`, falls sie fehlt
- installiert Python-Abhaengigkeiten aus `requirements.txt`
- laedt `yt-dlp` bzw. `yt-dlp.exe`, falls es fehlt
- richtet FFmpeg ein oder gibt eine klare Installationsmeldung aus
- legt `downloads/` und `transcripts/` an
- startet Download, Transkription und optional Zusammenfassung

GPU/CUDA ist nicht zwingend erforderlich. Empfohlen ist eine NVIDIA-GPU mit CUDA, weil Whisper damit deutlich schneller ist. Ohne CUDA faellt `--device auto` automatisch auf CPU zurueck; das funktioniert, ist fuer lange Dateien aber langsam und nicht empfohlen.

Nach dem ersten Lauf reicht meistens:

```powershell
.\run.ps1 "https://www.youtube.com/watch?v=..." -Summarize
```

```bash
bash ./run.sh "https://www.youtube.com/watch?v=..." --summarize
```

## Lokale Datei

Windows:

```powershell
.\run.ps1 "C:\pfad\audio.mp3"
```

Linux:

```bash
bash ./run.sh "/home/user/audio.mp3"
```

Mit Zusammenfassung unter Windows:

```powershell
.\run.ps1 "C:\pfad\audio.mp3" -Summarize
```

Mit Zusammenfassung unter Linux:

```bash
bash ./run.sh "/home/user/audio.mp3" --summarize
```

## Plattformen und Formate

URL-Downloads laufen ueber `yt-dlp`. Dadurch funktionieren viele Plattformen, solange das Video fuer deinen Rechner erreichbar ist.

Typische Plattformen:

- YouTube: Videos, Shorts, teilweise Playlists
- Loom: oeffentliche oder freigegebene Loom-Links
- Vimeo: oeffentliche Videos
- Twitter/X: einzelne Video-Posts, wenn erreichbar
- TikTok, Instagram, Facebook: oft nur mit Login/Cookies stabil
- Direktlinks zu Audio/Video-Dateien, z. B. `.mp3`, `.mp4`, `.m4a`, `.wav`

Beispiele Windows:

```powershell
.\run.ps1 "https://www.youtube.com/watch?v=..." -Summarize
.\run.ps1 "https://www.loom.com/share/..." -Summarize
.\run.ps1 "https://vimeo.com/..." -Summarize
.\run.ps1 "https://example.com/audio.mp3" -Summarize
```

Beispiele Linux:

```bash
bash ./run.sh "https://www.youtube.com/watch?v=..." --summarize
bash ./run.sh "https://www.loom.com/share/..." --summarize
bash ./run.sh "https://vimeo.com/..." --summarize
bash ./run.sh "https://example.com/audio.mp3" --summarize
```

Lokale Dateien werden von Whisper/FFmpeg gelesen. Praktisch nutzbar sind u. a.:

- Audio: `.mp3`, `.m4a`, `.wav`, `.flac`, `.aac`, `.ogg`, `.opus`, `.wma`
- Video: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`

Private oder login-geschuetzte Inhalte brauchen meist Cookies:

```powershell
.\run.ps1 "https://..." -CookiesFromBrowser chrome -Summarize
```

```bash
bash ./run.sh "https://..." --cookies-from-browser chrome --summarize
```

Wenn eine Plattform nicht klappt, liegt es meistens an Login-Schutz, Bot-Check, regionalen Sperren oder daran, dass `yt-dlp` fuer diese Seite gerade angepasst werden muss.

## OpenAI-Key fuer Zusammenfassungen

`-Summarize` braucht `OPENAI_API_KEY`. Lege dafuer eine lokale `.env` an:

Windows:

```powershell
Copy-Item .env.example .env
notepad .env
```

Linux:

```bash
cp .env.example .env
nano .env
```

Dann `OPENAI_API_KEY=` ausfuellen. `.env` ist absichtlich in `.gitignore`.

## Nuetzliche Optionen

Windows:

```powershell
.\run.ps1 "https://..." -Model small -Device auto
.\run.ps1 "https://..." -Out .\transcripts\mein_text.txt
.\run.ps1 "https://..." -Summarize -SummaryOut .\transcripts\mein_summary.md
.\run.ps1 "https://..." -CookiesFromBrowser chrome
.\run.ps1 "https://..." -- --yt-clients "android,tv,web"
```

Linux:

```bash
bash ./run.sh "https://..." --model small --device auto
bash ./run.sh "https://..." --out ./transcripts/mein_text.txt
bash ./run.sh "https://..." --summarize --summary-out ./transcripts/mein_summary.md
bash ./run.sh "https://..." --cookies-from-browser chrome
bash ./run.sh "https://..." -- --yt-clients "android,tv,web"
```

Hinweise:

- `-Model`: `tiny`, `base`, `small`, `medium`, `large`
- `-Device`: `auto`, `cuda`, `cpu`
- `auto` ist der Standard: nutzt CUDA, wenn verfuegbar, sonst CPU-Fallback.
- `cuda` erzwingt GPU-Nutzung und bricht ab, wenn keine CUDA-GPU erkannt wird.
- `cpu` funktioniert ohne GPU, ist aber deutlich langsamer und fuer lange Dateien nicht empfohlen.
- Linux nutzt dieselben Optionen in Kleinschreibung, z. B. `--model` und `--device`.
- Alles nach `--` wird direkt an `transcribe_whisper.py` weitergereicht.
- Bei YouTube Bot-Checks hilft oft `-CookiesFromBrowser chrome` oder `edge`.
- Unter Linux heisst dieselbe Option `--cookies-from-browser chrome`.

## Diagnose

Windows:

```powershell
.\run.ps1 -Diagnose
```

Linux:

```bash
bash ./run.sh --diagnose
```

## Ausgabe

- Transkripte landen standardmaessig in `transcripts/`.
- Downloads landen temporaer in `downloads/`.
- URL-Transkripte werden in `transcripts\video_index.csv` mit Video-ID, Titel, Hash und Datei protokolliert.
- Bei `-Summarize` entsteht zusaetzlich `<transkript>.summary.md`.

## Direkter Python-Aufruf

Der alte Weg funktioniert weiterhin:

```powershell
.\.venv\Scripts\python.exe .\transcribe_whisper.py --url "https://..." --summarize
```

```bash
./.venv/bin/python ./transcribe_whisper.py --url "https://..." --summarize
```
