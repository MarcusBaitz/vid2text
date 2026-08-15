---
name: video-zu-text
description: Wandelt Videos und Audiodateien in Text um - Transkript, Untertitel (SRT/VTT) und optional eine deutsche Zusammenfassung, lokal per Whisper. Nutze diesen Skill immer, wenn es darum geht, gesprochene Inhalte verschriftlichen zu lassen: "transkribiere dieses Video", "was wird in dem YouTube-Link gesagt", "mach Untertitel fuer mein MP4", "SRT-Datei erzeugen", "Text aus Loom/Vimeo/Zoom-Aufzeichnung ziehen", "fasse dieses Video zusammen", "Meeting-Aufnahme verschriftlichen", "Podcast in Text", "Sprachnachricht abtippen" - auch dann, wenn Whisper, Transkript oder Untertitel gar nicht ausdruecklich erwaehnt werden. Greift auf lokale Video-/Audiodateien und auf Video-URLs (YouTube, Loom, Vimeo, X, Direktlinks) zu.
---

# Video zu Text

Erzeugt aus einem Video oder einer Audiodatei drei Dinge, je nach Bedarf:

1. **Transkript** als `.txt` (immer)
2. **Untertitel** als `.srt` und/oder `.vtt` mit Zeitstempeln (auf Wunsch)
3. **Zusammenfassung** als `.md` per LLM (auf Wunsch, braucht `OPENAI_API_KEY`)

Die Transkription laeuft lokal mit OpenAI Whisper. Nichts wird hochgeladen —
ausser der Nutzer verlangt ausdruecklich eine Zusammenfassung, denn dafuer geht
das fertige Transkript an die OpenAI-API.

## Der eine Befehl

Alles laeuft ueber den Wrapper im Skill-Verzeichnis. Er findet das
vid2text-Repository selbst, richtet beim ersten Lauf `.venv`, `yt-dlp` und
`ffmpeg` ein und legt die Ergebnisse im **aktuellen Arbeitsverzeichnis** unter
`transcripts/` ab:

```bash
bash "$CLAUDE_SKILL_DIR/scripts/vid2text.sh" "<URL-oder-Dateipfad>" [Optionen]
```

Unter Windows/PowerShell stattdessen:

```powershell
powershell -ExecutionPolicy Bypass -File "<Skill-Verzeichnis>\scripts\vid2text.ps1" "<URL-oder-Dateipfad>" [Optionen]
```

Falls `$CLAUDE_SKILL_DIR` nicht gesetzt ist, liegt das Skript relativ zu dieser
Datei unter `scripts/vid2text.sh`. Die URL bzw. der Dateipfad gehoert an die
erste Stelle, danach die Optionen — so bleibt die Argumentweitergabe an das
Repository eindeutig.

### Optionen

| Option | Wirkung |
| --- | --- |
| `--subtitles srt` / `--subtitles srt,vtt` | Untertiteldateien mit Zeitstempeln zusaetzlich zum Transkript |
| `--summarize` | Deutsche Zusammenfassung als `.summary.md` (braucht `OPENAI_API_KEY`) |
| `--model tiny\|base\|small\|medium\|large` | Genauigkeit vs. Tempo, Standard `base` |
| `--device auto\|cuda\|cpu` | Standard `auto`: GPU wenn vorhanden, sonst CPU |
| `--out-dir <Ordner>` | Zielordner, Standard `./transcripts` im aktuellen Verzeichnis |
| `--out <Datei.txt>` | Exakter Pfad fuer das Transkript; Untertitel landen daneben |
| `--cookies-from-browser chrome\|edge\|firefox` | Fuer eingeloggte oder bot-geschuetzte Videos |
| `--subtitle-max-chars 42` | Maximale Zeichen pro Untertitelzeile |

### Typische Aufrufe

```bash
# Nur Text aus einem YouTube-Video
bash scripts/vid2text.sh "https://www.youtube.com/watch?v=..."

# Untertitel fuer eine lokale Datei, in beiden gaengigen Formaten
bash scripts/vid2text.sh ./aufnahme.mp4 --subtitles srt,vtt

# Vollprogramm: gutes Modell, Untertitel, Zusammenfassung
bash scripts/vid2text.sh "https://www.loom.com/share/..." --model small --subtitles srt --summarize

# Privates Video, das Login braucht
bash scripts/vid2text.sh "https://..." --cookies-from-browser chrome
```

## Vorgehen

**Modellwahl.** `base` ist der Standard und fuer die meisten deutschsprachigen
Aufnahmen brauchbar. Empfiehl `small` oder `medium`, wenn es um Fachbegriffe,
Namen, schlechte Tonqualitaet oder um Untertitel geht, die veroeffentlicht
werden — die Zeitstempel werden dann ebenfalls sauberer. Auf CPU kostet jede
Stufe spuerbar Zeit: grob ist `medium` etwa fuenfmal langsamer als `base`. Sag
das dem Nutzer vorher, statt ihn nach zwanzig Minuten zu ueberraschen.

**Laufzeit.** Whisper laeuft ohne GPU ungefaehr in Echtzeit bis halber
Echtzeit. Ein einstuendiges Video ist auf CPU also kein Zwei-Minuten-Job.
Starte lange Laeufe im Hintergrund und nenne dem Nutzer eine grobe Schaetzung,
bevor du anfaengst.

**Nach dem Lauf.** Nenne die erzeugten Dateien mit Pfad. Wenn der Nutzer nach
dem Inhalt gefragt hat und nicht nur nach der Datei, lies das Transkript und
antworte inhaltlich — die Datei allein beantwortet die Frage nicht.

**Untertitel gegen Transkript.** Frag nicht lange nach: geht es um Text zum
Lesen oder Weiterverarbeiten, reicht `.txt`. Sobald von Untertiteln, SRT, VTT,
Video-Einblendungen, Zeitstempeln oder davon die Rede ist, etwas "unter das
Video zu legen", nimm `--subtitles srt` dazu. Im Zweifel beides erzeugen, das
kostet nichts extra — die Zeitstempel fallen bei der Transkription ohnehin an.

**Zusammenfassungen.** `--summarize` schickt das Transkript an die OpenAI-API
und braucht `OPENAI_API_KEY` in der Umgebung oder in der `.env` des
vid2text-Repositorys. Fehlt der Schluessel, bricht nur dieser Schritt ab;
Transkript und Untertitel sind dann bereits geschrieben. Bei vertraulichen
Aufnahmen weise darauf hin, dass dieser Schritt — anders als die
Transkription — die Daten aus dem Haus gibt.

## Erstinstallation und globale Nutzung

Damit der Skill in **jedem** Projekt zur Verfuegung steht, muss er unter
`~/.claude/skills/` liegen. Im vid2text-Repository erledigt das:

```bash
bash ./install-skill.sh          # Symlink, bleibt bei git pull automatisch aktuell
bash ./install-skill.sh --copy   # Kopie, wenn Symlinks nicht moeglich sind
```

```powershell
powershell -ExecutionPolicy Bypass -File .\install-skill.ps1
```

Der Wrapper findet das vid2text-Repository in dieser Reihenfolge: `VID2TEXT_HOME`,
die gemerkte Position aus `.vid2text-home` im Skill-Ordner, das Repository um
den Skill herum, gaengige Ablageorte im Home-Verzeichnis. Findet er nichts,
klont er `https://github.com/MarcusBaitz/vid2text.git` nach `~/.vid2text` —
sag dem Nutzer, dass das passiert. `VID2TEXT_NO_CLONE=1` unterbindet es,
`VID2TEXT_HOME` zeigt gezielt auf einen vorhandenen Checkout.

Der erste Lauf auf einem neuen Rechner dauert laenger: venv, PyTorch und das
Whisper-Modell werden heruntergeladen. Das ist normal, kein Fehler.

## Wenn etwas schiefgeht

Fehlermeldungen zu Download, Login-Schutz, Bot-Checks, CUDA, ffmpeg oder
fehlenden Abhaengigkeiten sind in `references/troubleshooting.md` mit der
jeweils passenden Gegenmassnahme aufgelistet. Lies die Datei, sobald ein Lauf
abbricht, statt zu raten.
