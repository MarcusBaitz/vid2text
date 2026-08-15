# Troubleshooting

Nachschlagewerk fuer abgebrochene Laeufe. Suche die Meldung, die im Terminal
stand, und wende die genannte Gegenmassnahme an.

## Inhalt

- [Download und Plattformen](#download-und-plattformen)
- [Whisper, GPU und Tempo](#whisper-gpu-und-tempo)
- [ffmpeg und yt-dlp](#ffmpeg-und-yt-dlp)
- [Python und Abhaengigkeiten](#python-und-abhaengigkeiten)
- [Zusammenfassung und OpenAI-Key](#zusammenfassung-und-openai-key)
- [Untertitel](#untertitel)
- [Skill findet vid2text nicht](#skill-findet-vid2text-nicht)

## Download und Plattformen

**"Sign in to confirm you're not a bot" / HTTP 403 bei YouTube**
Bot-Check. Cookies aus einem eingeloggten Browser mitgeben:
`--cookies-from-browser chrome` (oder `edge`, `firefox`). Wenn der Browser
laeuft, sperrt er unter Windows die Cookie-Datenbank — Browser vorher schliessen.
Hilft das nicht, andere Player-Clients probieren:
`-- --yt-clients "android,tv,web"`.

**"Video unavailable" / "Private video"**
Das Video ist nicht oeffentlich. Ohne Zugang per Cookie ist hier Schluss; das
ist kein Fehler des Skills. Alternative: der Nutzer laedt die Datei selbst
herunter und uebergibt den lokalen Pfad.

**TikTok, Instagram, Facebook schlagen fehl**
Diese Plattformen sind ohne Login selten stabil. `--cookies-from-browser` ist
hier fast immer noetig.

**Der Download bricht mitten drin ab**
Meist ein Netzwerkproblem. Einfach erneut starten — bereits geladene Audios
liegen in `downloads/` des vid2text-Repositorys und werden wiederverwendet.

**Playlist statt Einzelvideo**
`yt-dlp` laedt bei Playlist-URLs unter Umstaenden nicht das erwartete Video.
Verwende die reine Video-URL (`watch?v=...` ohne `&list=...`).

## Whisper, GPU und Tempo

**"CUDA requested but none detected"**
`--device cuda` wurde erzwungen, es ist aber keine NVIDIA-GPU nutzbar. Nimm
`--device auto` (faellt automatisch auf CPU zurueck) oder `--device cpu`.

**"CUDA out of memory"**
Das Modell passt nicht in den GPU-Speicher. Eine Stufe kleiner waehlen
(`--model small` statt `medium`) oder `--device cpu` nutzen.

**Es laeuft, aber extrem langsam**
CPU-Fallback ist aktiv. Das ist normal: rechne grob mit Echtzeit bis halber
Echtzeit der Videolaenge, bei `medium` deutlich mehr. Fuer lange Aufnahmen
`--model base` oder `tiny` waehlen, oder den Lauf im Hintergrund starten.

**Das Transkript ist inhaltlich daneben oder in falscher Sprache**
`base` verwechselt bei schlechter Tonqualitaet gern die Sprache. `--model small`
oder `--model medium` loesen das fast immer.

**Der erste Lauf haengt scheinbar bei "Loading Whisper model"**
Das Modell wird einmalig heruntergeladen (`base` ca. 140 MB, `medium` ca. 1,5 GB)
und landet in `~/.cache/whisper`. Ab dem zweiten Lauf entfaellt das.

## ffmpeg und yt-dlp

**"ffmpeg not found"**
- Linux: `sudo apt install ffmpeg`
- Windows: `winget install -e --id Gyan.FFmpeg`, danach neues Terminal oeffnen
- macOS: `brew install ffmpeg`

**"yt-dlp not found"**
`run.sh` bzw. `run.ps1` laedt `yt-dlp` normalerweise selbst herunter. Schlaegt
das fehl, fehlt meist `curl`/`wget` oder der Netzwerkzugang. Manuell nach
`<vid2text>/yt-dlp` legen und ausfuehrbar machen.

**yt-dlp meldet "Unsupported URL" oder aehnliche Extractor-Fehler**
Die Plattform hat sich geaendert. `yt-dlp` aktualisieren:
`<vid2text>/yt-dlp -U` bzw. die Datei neu herunterladen.

## Python und Abhaengigkeiten

**"Konnte .venv nicht erstellen"**
Unter Debian/Ubuntu fehlt `python3-venv`: `sudo apt install python3-venv`.

**pip-Installation bricht bei torch ab**
PyTorch ist gross und braucht Platz sowie eine stabile Verbindung. Plattenplatz
pruefen und erneut starten; `run.sh` setzt die Installation fort.

**Der Lauf soll die Installationspruefung ueberspringen**
`--skip-install` an den Wrapper haengen. Nur sinnvoll, wenn die Umgebung
nachweislich fertig ist.

## Zusammenfassung und OpenAI-Key

**"OPENAI_API_KEY" fehlt**
Nur `--summarize` braucht ihn. Entweder als Umgebungsvariable setzen oder im
vid2text-Repository `.env` aus `.env.example` anlegen und den Schluessel
eintragen. Transkript und Untertitel entstehen auch ohne Key — der Abbruch
passiert erst nach dem Schreiben des Transkripts.

**Die Zusammenfassung soll ein anderes Modell nutzen**
`--llm-model gpt-4o` oder `VID2TEXT_LLM_MODEL` in der `.env` setzen.

**Der Nutzer will einen anderen Zusammenfassungs-Fokus**
`--summary-prompt "..."` ersetzt die Standardanweisung komplett. Sinnvoll etwa
fuer reine Aufgabenlisten aus Meeting-Mitschnitten.

## Untertitel

**Es wird keine SRT-Datei geschrieben, obwohl `--subtitles srt` gesetzt war**
Whisper hat keine Segmente geliefert — praktisch nur bei Aufnahmen ohne
verstaendliche Sprache. Die Meldung "No subtitle segments returned by Whisper"
steht dann im Log. Tonspur pruefen.

**Die Zeilen sind zu lang fuer den Player**
`--subtitle-max-chars 32` setzen. Pro Cue entstehen hoechstens zwei Zeilen.

**Die Zeitstempel driften bei langen Videos**
Ein groesseres Modell hilft (`--model small` oder `medium`); `base` setzt
Segmentgrenzen ungenauer.

**"Unknown subtitle format"**
Unterstuetzt sind `srt` und `vtt`. Andere Formate (z. B. ASS) muessen mit
ffmpeg aus der SRT-Datei konvertiert werden.

## Skill findet vid2text nicht

**"vid2text wurde nicht gefunden"**
`VID2TEXT_HOME` auf das Repository setzen:
`export VID2TEXT_HOME=/pfad/zu/vid2text` (bzw. `$env:VID2TEXT_HOME` unter
Windows). Alternativ im Repository `bash ./install-skill.sh` ausfuehren — das
merkt die Position dauerhaft im Skill-Ordner.

**"kennt --subtitles noch nicht" / "kennt --out-dir noch nicht"**
Der gefundene Checkout ist aelter als diese Funktionen. Aktualisieren mit
`git -C <vid2text> pull`.

**Der Skill klont ungefragt nach `~/.vid2text`**
Das passiert nur, wenn kein Checkout gefunden wurde. `VID2TEXT_NO_CLONE=1`
verhindert es, `VID2TEXT_HOME` zeigt auf den vorhandenen.
