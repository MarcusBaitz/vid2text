#!/usr/bin/env python3
import os
import html
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import markdown
from flask import Flask, Response, jsonify, request, send_file
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "uploads"
TRANSCRIPT_DIR = ROOT / "transcripts"

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
MODELS = {"tiny", "base", "small", "medium", "large"}
DEVICES = {"auto", "cuda", "cpu"}

app = Flask(__name__)
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def now_label() -> str:
    return time.strftime("%H:%M:%S")


def append_log(job_id: str, line: str) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["logs"].append(f"[{now_label()}] {line.rstrip()}")
        job["logs"] = job["logs"][-600:]


def set_job(job_id: str, **updates) -> None:
    with jobs_lock:
        jobs[job_id].update(updates)


def get_job_snapshot(job_id: str) -> dict | None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return None
        return dict(job)


def is_supported_url(raw_url: str) -> bool:
    parsed = urlparse(raw_url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def output_paths(job_id: str) -> tuple[Path, Path]:
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    transcript_path = TRANSCRIPT_DIR / f"ui_{job_id}.txt"
    summary_path = TRANSCRIPT_DIR / f"ui_{job_id}.summary.md"
    return transcript_path, summary_path


def read_text_if_exists(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def render_markdown(text: str) -> str:
    if not text:
        return ""
    safe_source = html.escape(text, quote=False)
    return markdown.markdown(
        safe_source,
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )


def run_transcription_job(job_id: str) -> None:
    snapshot = get_job_snapshot(job_id)
    if not snapshot:
        return

    transcript_path = Path(snapshot["transcript_path"])
    summary_path = Path(snapshot["summary_path"])
    input_type = snapshot["input_type"]
    source = snapshot["source"]
    model = snapshot["model"]
    device = snapshot["device"]
    summarize = snapshot["summarize"]

    command = [
        sys.executable,
        str(ROOT / "transcribe_whisper.py"),
        "--model",
        model,
        "--device",
        device,
        "--out",
        str(transcript_path),
    ]
    if input_type == "url":
        command.extend(["--url", source])
    else:
        command.append(source)
    if summarize:
        command.extend(["--summarize", "--summary-out", str(summary_path)])

    set_job(job_id, status="running", started_at=time.time())
    append_log(job_id, "Job gestartet.")

    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            append_log(job_id, line)
        return_code = process.wait()
    except Exception as exc:
        set_job(job_id, status="failed", error=str(exc), finished_at=time.time())
        append_log(job_id, f"Fehler: {exc}")
        return

    finished_at = time.time()
    if return_code == 0 and transcript_path.exists():
        set_job(job_id, status="done", return_code=return_code, finished_at=finished_at)
        append_log(job_id, "Fertig.")
    else:
        set_job(
            job_id,
            status="failed",
            return_code=return_code,
            error=f"Transkription fehlgeschlagen (Exit-Code {return_code}).",
            finished_at=finished_at,
        )
        append_log(job_id, f"Fehlgeschlagen mit Exit-Code {return_code}.")


@app.get("/")
def index() -> Response:
    return Response(
        INDEX_HTML,
        mimetype="text/html; charset=utf-8",
    )


@app.post("/api/jobs")
def create_job():
    source_url = request.form.get("url", "").strip()
    upload = request.files.get("media")
    model = request.form.get("model", "base").strip()
    device = request.form.get("device", "auto").strip()
    summarize = request.form.get("summarize") == "1"

    if model not in MODELS:
        return jsonify({"error": "Ungueltiges Whisper-Modell."}), 400
    if device not in DEVICES:
        return jsonify({"error": "Ungueltiges Zielgeraet."}), 400

    has_url = bool(source_url)
    has_file = bool(upload and upload.filename)
    if has_url == has_file:
        return jsonify({"error": "Bitte genau eine Datei oder einen Video-Link angeben."}), 400

    job_id = uuid.uuid4().hex[:12]
    transcript_path, summary_path = output_paths(job_id)

    if has_url:
        if not is_supported_url(source_url):
            return jsonify({"error": "Bitte eine gueltige http(s)-URL angeben."}), 400
        input_type = "url"
        source = source_url
        display_name = source_url
    else:
        original_name = upload.filename or "upload"
        filename = secure_filename(original_name) or f"upload_{job_id}"
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            return jsonify({"error": f"Dateiformat nicht unterstuetzt. Erlaubt: {allowed}"}), 400
        UPLOAD_DIR.mkdir(exist_ok=True)
        upload_path = UPLOAD_DIR / f"{job_id}_{filename}"
        upload.save(upload_path)
        input_type = "file"
        source = str(upload_path)
        display_name = original_name

    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "logs": [],
            "input_type": input_type,
            "source": source,
            "display_name": display_name,
            "model": model,
            "device": device,
            "summarize": summarize,
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "return_code": None,
            "error": None,
            "transcript_path": str(transcript_path),
            "summary_path": str(summary_path),
        }

    thread = threading.Thread(target=run_transcription_job, args=(job_id,), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = get_job_snapshot(job_id)
    if not job:
        return jsonify({"error": "Job nicht gefunden."}), 404

    transcript_path = Path(job["transcript_path"])
    summary_path = Path(job["summary_path"])
    elapsed = None
    if job.get("started_at"):
        end = job.get("finished_at") or time.time()
        elapsed = round(end - job["started_at"], 1)

    return jsonify(
        {
            "id": job_id,
            "status": job["status"],
            "display_name": job["display_name"],
            "summarize": job["summarize"],
            "logs": job["logs"],
            "error": job.get("error"),
            "elapsed": elapsed,
            "transcript": read_text_if_exists(transcript_path),
            "summary": read_text_if_exists(summary_path),
            "summary_html": render_markdown(read_text_if_exists(summary_path)),
            "has_transcript": transcript_path.exists(),
            "has_summary": summary_path.exists(),
        }
    )


@app.get("/api/jobs/<job_id>/file/<kind>")
def download_result(job_id: str, kind: str):
    job = get_job_snapshot(job_id)
    if not job:
        return jsonify({"error": "Job nicht gefunden."}), 404
    if kind == "transcript":
        path = Path(job["transcript_path"])
    elif kind == "summary":
        path = Path(job["summary_path"])
    else:
        return jsonify({"error": "Unbekannte Datei."}), 404
    if not path.exists():
        return jsonify({"error": "Datei noch nicht vorhanden."}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


INDEX_HTML = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>vid2text</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --surface: #ffffff;
      --surface-soft: #f8fafb;
      --surface-strong: #eef3f6;
      --text: #111827;
      --muted: #667085;
      --border: #d8e0e6;
      --border-strong: #c4ced8;
      --accent: #116466;
      --accent-hover: #0b4d4f;
      --accent-soft: #e2f1ef;
      --danger: #b42318;
      --danger-soft: #fee4e2;
      --ok: #067647;
      --ok-soft: #dcfae6;
      --warn: #b54708;
      --warn-soft: #fef0c7;
      --shadow: 0 18px 50px rgba(17, 24, 39, .08);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top left, rgba(17, 100, 102, .10), transparent 34rem),
        linear-gradient(180deg, #fbfcfd 0%, var(--bg) 100%);
      color: var(--text);
    }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 28px auto 42px;
      display: grid;
      gap: 20px;
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
      padding: 8px 2px;
    }
    h1 {
      margin: 0;
      font-size: clamp(30px, 4vw, 48px);
      line-height: 1;
      letter-spacing: 0;
    }
    h2, h3 {
      margin: 0;
      letter-spacing: 0;
    }
    h2 { font-size: 18px; }
    h3 { font-size: 15px; }
    p { margin: 0; }
    .subtitle {
      margin-top: 9px;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.5;
    }
    .format-note {
      max-width: 480px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
      text-align: right;
    }
    .grid {
      display: grid;
      gap: 20px;
    }
    .app-form {
      display: grid;
      gap: 20px;
    }
    .card {
      background: rgba(255, 255, 255, .92);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: var(--shadow);
    }
    .input-card {
      padding: 22px;
      display: grid;
      gap: 18px;
    }
    .source-card {
      gap: 20px;
    }
    .under-tabs {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
      gap: 20px;
      align-items: start;
    }
    .settings-card {
      padding: 20px;
      display: grid;
      gap: 16px;
      position: sticky;
      top: 18px;
    }
    .card-title {
      display: grid;
      gap: 6px;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    label {
      display: grid;
      gap: 8px;
      color: #273444;
      font-size: 13px;
      font-weight: 700;
    }
    input[type="url"], select {
      width: 100%;
      min-height: 48px;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 11px 13px;
      background: #fff;
      color: var(--text);
      font: inherit;
      outline: none;
      transition: border-color .16s ease, box-shadow .16s ease;
    }
    input[type="url"]:focus, select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 4px var(--accent-soft);
    }
    .source-tabs {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
      width: min(360px, 100%);
      padding: 5px;
      border: 1px solid var(--border);
      border-radius: 15px;
      background: var(--surface-soft);
    }
    .tab-button {
      min-height: 42px;
      border: 0;
      border-radius: 11px;
      background: transparent;
      color: var(--muted);
      font: inherit;
      font-size: 14px;
      font-weight: 850;
      cursor: pointer;
      transition: background .16s ease, color .16s ease, box-shadow .16s ease;
    }
    .tab-button.active {
      background: #fff;
      color: var(--accent);
      box-shadow: 0 6px 18px rgba(17, 24, 39, .08);
    }
    .tab-panels {
      display: grid;
      gap: 14px;
    }
    .tab-panel {
      display: grid;
      gap: 12px;
    }
    .tab-panel[hidden] {
      display: none;
    }
    .source-divider {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .source-divider:before, .source-divider:after {
      content: "";
      height: 1px;
      background: var(--border);
    }
    .drop-zone {
      min-height: 156px;
      border: 1.5px dashed var(--border-strong);
      border-radius: 14px;
      background: var(--surface-soft);
      display: grid;
      place-items: center;
      text-align: center;
      padding: 18px;
      cursor: pointer;
      transition: background .16s ease, border-color .16s ease, transform .16s ease;
    }
    .drop-zone:hover,
    .drop-zone.dragover {
      background: var(--accent-soft);
      border-color: var(--accent);
      transform: translateY(-1px);
    }
    .drop-zone input {
      position: absolute;
      inline-size: 1px;
      block-size: 1px;
      opacity: 0;
      pointer-events: none;
    }
    .drop-inner {
      display: grid;
      gap: 8px;
      justify-items: center;
    }
    .upload-icon {
      width: 44px;
      height: 44px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      background: #fff;
      color: var(--accent);
      border: 1px solid var(--border);
      font-size: 22px;
      font-weight: 900;
    }
    .file-name {
      color: var(--text);
      font-size: 13px;
      font-weight: 800;
      max-width: 100%;
      overflow-wrap: anywhere;
    }
    details.settings {
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface-soft);
      overflow: hidden;
    }
    details.settings summary {
      list-style: none;
      cursor: pointer;
      padding: 14px 15px;
      font-size: 13px;
      font-weight: 800;
      color: #273444;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    details.settings summary::-webkit-details-marker { display: none; }
    details.settings summary:after {
      content: "+";
      color: var(--muted);
      font-size: 18px;
      line-height: 1;
    }
    details.settings[open] summary:after { content: "-"; }
    .settings-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      padding: 0 15px 15px;
    }
    .toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 14px 15px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: #fff;
    }
    .toggle-text {
      display: grid;
      gap: 3px;
    }
    .toggle-text strong {
      font-size: 13px;
    }
    .switch {
      position: relative;
      width: 48px;
      height: 28px;
      flex: 0 0 auto;
    }
    .switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }
    .slider {
      position: absolute;
      inset: 0;
      cursor: pointer;
      background: #d0d5dd;
      border-radius: 999px;
      transition: .18s ease;
    }
    .slider:before {
      content: "";
      position: absolute;
      width: 22px;
      height: 22px;
      left: 3px;
      top: 3px;
      border-radius: 50%;
      background: white;
      box-shadow: 0 2px 7px rgba(17, 24, 39, .2);
      transition: .18s ease;
    }
    .switch input:checked + .slider {
      background: var(--accent);
    }
    .switch input:checked + .slider:before {
      transform: translateX(20px);
    }
    .primary-button {
      min-height: 54px;
      width: 100%;
      border: 0;
      border-radius: 14px;
      background: var(--accent);
      color: white;
      font: inherit;
      font-size: 15px;
      font-weight: 850;
      cursor: pointer;
      box-shadow: 0 10px 26px rgba(17, 100, 102, .22);
      transition: background .16s ease, transform .16s ease, opacity .16s ease;
    }
    .primary-button:hover { background: var(--accent-hover); transform: translateY(-1px); }
    .primary-button:disabled {
      cursor: wait;
      opacity: .65;
      transform: none;
    }
    .error {
      color: var(--danger);
      background: transparent;
      font-size: 13px;
      font-weight: 700;
      min-height: 18px;
    }
    .workspace {
      display: grid;
      gap: 18px;
    }
    .status-card,
    .result-card {
      padding: 20px;
    }
    .status-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 12px;
    }
    .job-meta {
      display: grid;
      gap: 4px;
      min-width: 0;
    }
    .job-meta .hint {
      overflow-wrap: anywhere;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      border-radius: 999px;
      padding: 4px 12px;
      background: var(--surface-strong);
      color: #344054;
      font-size: 12px;
      font-weight: 850;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .badge.queued, .badge.running { color: var(--warn); background: var(--warn-soft); }
    .badge.done { color: var(--ok); background: var(--ok-soft); }
    .badge.failed { color: var(--danger); background: var(--danger-soft); }
    .logs-details {
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }
    .logs-details summary {
      cursor: pointer;
      color: #273444;
      font-size: 13px;
      font-weight: 800;
      list-style: none;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .logs-details summary::-webkit-details-marker { display: none; }
    .logs-details summary:after {
      content: "anzeigen";
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
    }
    .logs-details[open] summary:after { content: "ausblenden"; }
    pre {
      width: 100%;
      height: 210px;
      margin: 12px 0 0;
      padding: 13px;
      overflow: auto;
      white-space: pre-wrap;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: #0f172a;
      color: #dce6ef;
      font: 12px/1.55 ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
    }
    .empty-state {
      min-height: 220px;
      display: grid;
      place-items: center;
      text-align: center;
      color: var(--muted);
      border: 1px dashed var(--border);
      border-radius: 14px;
      background: var(--surface-soft);
      padding: 24px;
    }
    .result-stack {
      display: grid;
      gap: 14px;
    }
    .reader-block {
      border: 1px solid var(--border);
      border-radius: 14px;
      background: #fff;
      overflow: hidden;
    }
    .reader-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-soft);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    .secondary-button,
    .download-link {
      min-height: 34px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #fff;
      color: #273444;
      padding: 7px 11px;
      font: inherit;
      font-size: 12px;
      font-weight: 800;
      text-decoration: none;
      cursor: pointer;
    }
    .secondary-button:hover,
    .download-link:hover {
      border-color: var(--accent);
      color: var(--accent);
    }
    .reader {
      padding: 20px;
      color: #1d2939;
      font-size: 15px;
      line-height: 1.7;
    }
    .reader.summary h1,
    .reader.summary h2,
    .reader.summary h3 {
      margin: 0 0 12px;
      line-height: 1.25;
    }
    .reader.summary h1 { font-size: 24px; }
    .reader.summary h2 { font-size: 20px; margin-top: 22px; }
    .reader.summary h3 { font-size: 17px; margin-top: 18px; }
    .reader.summary p,
    .reader.summary ul,
    .reader.summary ol {
      margin: 0 0 14px;
    }
    .reader.summary li { margin: 6px 0; }
    .transcript-text {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: #26313d;
    }
    .transcript-details {
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
      background: #fff;
    }
    .transcript-details summary {
      cursor: pointer;
      list-style: none;
      padding: 14px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: var(--surface-soft);
      border-bottom: 1px solid transparent;
    }
    .transcript-details summary::-webkit-details-marker { display: none; }
    .transcript-details[open] summary {
      border-bottom-color: var(--border);
    }
    .transcript-details summary:after {
      content: "oeffnen";
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .transcript-details[open] summary:after { content: "schliessen"; }
    .hidden { display: none !important; }
    @media (max-width: 860px) {
      main { width: min(100vw - 20px, 1180px); margin: 18px auto 30px; }
      .under-tabs { grid-template-columns: 1fr; }
      .settings-card { position: static; }
      .format-note { text-align: left; }
      .settings-grid { grid-template-columns: 1fr; }
      .reader-head { align-items: flex-start; flex-direction: column; }
      .actions { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>vid2text</h1>
        <p class="subtitle">Transkription fuer Video-Links und lokale Audio-/Videodateien.</p>
      </div>
      <p class="format-note">Uploads: mp3, m4a, wav, flac, aac, ogg, opus, wma, mp4, mov, mkv, webm, avi</p>
    </header>
    <div class="grid">
      <form id="jobForm" class="app-form">
        <section class="card input-card source-card">
          <div class="card-title">
            <h2>Neue Transkription</h2>
            <p class="hint">Waehle zuerst die Quelle: Video-Link oder lokale Datei.</p>
          </div>

          <div class="source-tabs" role="tablist" aria-label="Quelle auswaehlen">
            <button class="tab-button active" type="button" role="tab" aria-selected="true" data-tab="vidz">Vidz</button>
            <button class="tab-button" type="button" role="tab" aria-selected="false" data-tab="filz">Filz</button>
          </div>

          <div class="tab-panels">
            <div class="tab-panel" role="tabpanel" data-panel="vidz">
              <label>
                Video-Link
                <input id="url" name="url" type="url" placeholder="https://www.youtube.com/watch?v=...">
                <span class="hint">Funktioniert mit erreichbaren yt-dlp-Quellen wie YouTube, Loom, Vimeo oder direkten Medienlinks.</span>
              </label>
            </div>

            <div class="tab-panel" role="tabpanel" data-panel="filz" hidden>
              <label class="drop-zone" id="dropZone">
                <input id="media" name="media" type="file" accept=".mp3,.m4a,.wav,.flac,.aac,.ogg,.opus,.wma,.mp4,.mov,.mkv,.webm,.avi">
                <span class="drop-inner">
                  <span class="upload-icon">+</span>
                  <span class="file-name" id="fileName">Datei hier ablegen oder auswaehlen</span>
                  <span class="hint">Audio oder Video, lokal auf deinem Rechner.</span>
                </span>
              </label>
            </div>
          </div>
        </section>

        <div class="under-tabs">
          <div class="workspace">
            <section class="card status-card">
              <div class="status-bar">
                <div class="job-meta">
                  <h2>Status</h2>
                  <div class="hint" id="jobName">Noch kein Job gestartet.</div>
                </div>
                <span class="badge" id="status">idle</span>
              </div>
              <details class="logs-details" id="logsDetails">
                <summary>Logs</summary>
                <pre id="logs"></pre>
              </details>
            </section>

            <section class="card result-card">
              <div class="result-stack" id="resultStack">
                <div class="empty-state" id="emptyState">
                  <div>
                    <h2>Output</h2>
                    <p class="hint">Summary und Transkript erscheinen hier nach Abschluss.</p>
                  </div>
                </div>

                <article class="reader-block hidden" id="summaryBlock">
                  <div class="reader-head">
                    <h2>Summary</h2>
                    <div class="actions">
                      <button class="secondary-button" type="button" data-copy="summary">Kopieren</button>
                      <a class="download-link" id="summaryDownload" href="#">Herunterladen</a>
                    </div>
                  </div>
                  <div class="reader summary" id="summaryReader"></div>
                </article>

                <details class="transcript-details hidden" id="transcriptDetails">
                  <summary>
                    <h2>Transkript</h2>
                    <span class="actions">
                      <button class="secondary-button" type="button" data-copy="transcript">Kopieren</button>
                      <a class="download-link" id="transcriptDownload" href="#">Herunterladen</a>
                    </span>
                  </summary>
                  <div class="reader transcript-text" id="transcriptReader"></div>
                </details>
              </div>
            </section>
          </div>

          <aside class="card settings-card">
            <div class="card-title">
              <h2>Einstellungen</h2>
              <p class="hint">Whisper, Zielgeraet und Summary-Verhalten.</p>
            </div>

            <details class="settings" open>
              <summary>Erweiterte Einstellungen</summary>
              <div class="settings-grid">
                <label>
                  Whisper-Modell
                  <select name="model">
                    <option value="base" selected>base</option>
                    <option value="tiny">tiny</option>
                    <option value="small">small</option>
                    <option value="medium">medium</option>
                    <option value="large">large</option>
                  </select>
                </label>
                <label>
                  Geraet
                  <select name="device">
                    <option value="auto" selected>auto</option>
                    <option value="cuda">cuda</option>
                    <option value="cpu">cpu</option>
                  </select>
                </label>
              </div>
            </details>

            <label class="toggle-row">
              <span class="toggle-text">
                <strong>Zusammenfassung erzeugen</strong>
                <span class="hint">Zeigt danach zuerst die gerenderte Markdown-Summary.</span>
              </span>
              <span class="switch">
                <input id="summarize" type="checkbox" name="summarize" value="1" checked>
                <span class="slider"></span>
              </span>
            </label>

            <div class="error" id="error"></div>
            <button id="submit" class="primary-button" type="submit">Transkription starten</button>
          </aside>
        </div>
      </form>
    </div>
  </main>
  <script>
    const form = document.querySelector("#jobForm");
    const errorBox = document.querySelector("#error");
    const submit = document.querySelector("#submit");
    const statusBadge = document.querySelector("#status");
    const logs = document.querySelector("#logs");
    const logsDetails = document.querySelector("#logsDetails");
    const jobName = document.querySelector("#jobName");
    const tabButtons = document.querySelectorAll("[data-tab]");
    const tabPanels = document.querySelectorAll("[data-panel]");
    const dropZone = document.querySelector("#dropZone");
    const fileInput = document.querySelector("#media");
    const fileName = document.querySelector("#fileName");
    const urlInput = document.querySelector("#url");
    const emptyState = document.querySelector("#emptyState");
    const summaryBlock = document.querySelector("#summaryBlock");
    const summaryReader = document.querySelector("#summaryReader");
    const summaryDownload = document.querySelector("#summaryDownload");
    const transcriptDetails = document.querySelector("#transcriptDetails");
    const transcriptReader = document.querySelector("#transcriptReader");
    const transcriptDownload = document.querySelector("#transcriptDownload");
    const copyButtons = document.querySelectorAll("[data-copy]");
    let timer = null;
    let currentSummary = "";
    let currentTranscript = "";

    function setStatus(value) {
      statusBadge.textContent = value;
      statusBadge.className = "badge " + value;
    }

    function activateTab(tabName, clearInactive = false) {
      tabButtons.forEach((button) => {
        const active = button.dataset.tab === tabName;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      tabPanels.forEach((panel) => {
        panel.hidden = panel.dataset.panel !== tabName;
      });
      if (!clearInactive) return;
      if (tabName === "vidz") {
        fileInput.value = "";
        updateFileName(false);
      } else {
        urlInput.value = "";
      }
    }

    function resetResult() {
      currentSummary = "";
      currentTranscript = "";
      emptyState.classList.remove("hidden");
      summaryBlock.classList.add("hidden");
      transcriptDetails.classList.add("hidden");
      transcriptDetails.open = false;
      summaryReader.innerHTML = "";
      transcriptReader.textContent = "";
      summaryDownload.removeAttribute("href");
      transcriptDownload.removeAttribute("href");
    }

    function updateFileName(clearUrl = true) {
      const file = fileInput.files && fileInput.files[0];
      fileName.textContent = file ? file.name : "Datei hier ablegen oder auswaehlen";
      if (file) {
        activateTab("filz", false);
        if (clearUrl) urlInput.value = "";
      }
    }

    function renderJob(data) {
      const logText = (data.logs || []).join("\n");
      setStatus(data.status);
      jobName.textContent = data.display_name || (data.elapsed ? `Laufzeit: ${data.elapsed}s` : "Noch kein Job gestartet.");
      logs.textContent = logText;
      logs.scrollTop = logs.scrollHeight;

      currentSummary = data.summary || "";
      currentTranscript = data.transcript || "";
      errorBox.textContent = data.error || "";

      const hasAnyResult = data.has_summary || data.has_transcript;
      emptyState.classList.toggle("hidden", hasAnyResult);

      if (data.summarize && data.has_summary) {
        summaryBlock.classList.remove("hidden");
        summaryReader.innerHTML = data.summary_html || "";
        summaryDownload.href = `/api/jobs/${data.id}/file/summary`;
      } else {
        summaryBlock.classList.add("hidden");
        summaryReader.innerHTML = "";
        summaryDownload.removeAttribute("href");
      }

      if (data.has_transcript) {
        transcriptDetails.classList.remove("hidden");
        transcriptReader.textContent = currentTranscript;
        transcriptDownload.href = `/api/jobs/${data.id}/file/transcript`;
        transcriptDetails.open = !data.summarize;
      } else {
        transcriptDetails.classList.add("hidden");
        transcriptDetails.open = false;
        transcriptReader.textContent = "";
        transcriptDownload.removeAttribute("href");
      }

      if (data.status === "running" && logText) {
        logsDetails.open = true;
      }
      if (data.status === "done" || data.status === "failed") {
        submit.disabled = false;
        if (timer) clearInterval(timer);
      }
    }

    async function poll(jobId) {
      const response = await fetch(`/api/jobs/${jobId}`);
      const data = await response.json();
      renderJob(data);
    }

    async function copyText(kind, button) {
      const text = kind === "summary" ? currentSummary : currentTranscript;
      if (!text) return;
      await navigator.clipboard.writeText(text);
      const oldLabel = button.textContent;
      button.textContent = "Kopiert";
      window.setTimeout(() => {
        button.textContent = oldLabel;
      }, 1200);
    }

    tabButtons.forEach((button) => {
      button.addEventListener("click", () => {
        activateTab(button.dataset.tab, true);
      });
    });

    fileInput.addEventListener("change", () => updateFileName());
    urlInput.addEventListener("input", () => {
      if (urlInput.value) {
        activateTab("vidz", false);
      }
      if (urlInput.value && fileInput.value) {
        fileInput.value = "";
        updateFileName(false);
      }
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("dragover");
      });
    });
    dropZone.addEventListener("drop", (event) => {
      const files = event.dataTransfer.files;
      if (!files || !files.length) return;
      fileInput.files = files;
      updateFileName();
    });

    copyButtons.forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        copyText(button.dataset.copy, button).catch((error) => {
          errorBox.textContent = error.message || "Kopieren fehlgeschlagen.";
        });
      });
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorBox.textContent = "";
      logs.textContent = "";
      submit.disabled = true;
      setStatus("queued");
      resetResult();

      try {
        const response = await fetch("/api/jobs", {
          method: "POST",
          body: new FormData(form),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "Job konnte nicht gestartet werden.");
        }
        await poll(data.job_id);
        if (timer) clearInterval(timer);
        timer = setInterval(() => poll(data.job_id).catch(console.error), 1500);
      } catch (error) {
        errorBox.textContent = error.message;
        setStatus("failed");
        submit.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def parse_args() -> tuple[str, int, bool]:
    host = os.environ.get("VID2TEXT_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("VID2TEXT_UI_PORT", "7860"))
    open_browser = os.environ.get("VID2TEXT_UI_OPEN_BROWSER", "1") != "0"

    args = sys.argv[1:]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--host" and index + 1 < len(args):
            host = args[index + 1]
            index += 2
        elif arg == "--port" and index + 1 < len(args):
            port = int(args[index + 1])
            index += 2
        elif arg == "--no-browser":
            open_browser = False
            index += 1
        else:
            raise SystemExit(f"Unknown argument: {arg}")
    return host, port, open_browser


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(exist_ok=True)
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    host, port, open_browser = parse_args()
    url = f"http://{host}:{port}"
    print(f"vid2text UI: {url}")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, threaded=True)
