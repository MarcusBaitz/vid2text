# vid2text – Kurzanleitung

Diese App transkribiert Audio in Text mit Whisper (GPU/CUDA erforderlich).

## Voraussetzungen
- Windows
- Python + virtuelle Umgebung (`venv`)
- NVIDIA GPU mit CUDA (ohne CUDA beendet sich das Skript)
- `ffmpeg` im `PATH`
- `yt-dlp.exe` liegt bereits im Projektordner (ist vorhanden)

## Installation
```powershell
# im Projektordner
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Nutzung
### 1) Lokale Audiodatei transkribieren
```powershell
python .\transcribe_whisper.py "C:\pfad\zur\datei.mp3"
```

### 2) Audio direkt von URL laden und transkribieren
```powershell
python .\transcribe_whisper.py --url "https://www.youtube.com/watch?v=..."
```

Bei YouTube-403 kannst du Browser-Cookies nutzen:
```powershell
python .\transcribe_whisper.py --url "https://www.youtube.com/watch?v=..." --cookies-from-browser chrome
```

Wenn `Could not copy Chrome cookie database` erscheint:
- Chrome vollständig schließen und erneut starten
- oder Browser wechseln: `--cookies-from-browser edge`
- oder Cookie-Datei nutzen: `--cookies C:\pfad\cookies.txt`

Hinweis:
- Das Skript nutzt automatisch Fallback-Clients (`android,tv`) für yt-dlp.
- Optional anpassbar mit `--yt-clients "android,tv,web"`.
- Bei Bot-Check: `--cookies-from-browser chrome` (oder `edge`/`firefox`) setzen.

### 3) Nach der Transkription automatisch mit LLM zusammenfassen
In `.env` hinterlegen:
```env
OPENAI_API_KEY=dein_api_key
```

Dann starten mit `--summarize`:
```powershell
python .\transcribe_whisper.py --url "https://www.youtube.com/watch?v=..." --summarize
```

Optional:
- `--llm-model gpt-4o-mini` (oder anderes kompatibles Modell)
- `--summary-out .\transcripts\mein_summary.txt`
- `--summary-prompt "..."` für eigene Zusammenfassungsanweisung
- `--cookies-from-browser chrome` bei YouTube-403
- `--cookies C:\pfad\cookies.txt` für manuelle Cookies
- `--device auto|cuda|cpu` (Standard: `auto`; ohne GPU automatisch CPU)

### Optionale Parameter
- `-m` / `--model`: `tiny`, `base`, `small`, `medium`, `large` (Default: `base`)
- `-o` / `--out`: Ausgabepfad für Transkript

Beispiel:
```powershell
python .\transcribe_whisper.py --url "https://..." -m small -o .\transcripts\mein_text.txt
```

## Ausgabe
- Bei lokaler Datei: Standardmäßig `transcripts/<dateiname>.txt`.
- Bei `--url`: Standardmäßig `transcripts/<video_id>_<title-hash>.txt`.
- Bei `--summarize`: zusätzliche Datei `transcripts/<transkriptname>.summary.txt`.
- In der Konsole siehst du u. a. GPU, Laufzeit, Audiolänge und Wortanzahl.

## Video-Zuordnung (Hash + Titel)
- Bei URL-Transkription erzeugt die App einen stabilen Hash aus dem Video-Titel.
- Die Zuordnung wird in `transcripts/video_index.csv` gespeichert mit:
	- Zeitstempel
	- Hash
	- Video-ID
	- Titel
	- URL
	- Transkript-Datei
- So kannst du auch bei kryptischen IDs Videos später eindeutig zuordnen.

## Diagnose bei Problemen
```powershell
python .\diagnose.py
```

Typische Fehler:
- `ffmpeg not found` → FFmpeg installieren und `PATH` prüfen.
- `CUDA-capable GPU required` → CUDA/GPU fehlt oder ist nicht korrekt eingerichtet.
