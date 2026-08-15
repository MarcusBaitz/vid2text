param(
    [Parameter(Position = 0)]
    [string]$InputPathOrUrl,

    [string]$Url,

    [switch]$Summarize,

    [string]$Model = $(if ($env:WHISPER_MODEL) { $env:WHISPER_MODEL } else { "base" }),

    [ValidateSet("auto", "cuda", "cpu")]
    [string]$Device = $(if ($env:VID2TEXT_DEVICE) { $env:VID2TEXT_DEVICE } else { "auto" }),

    [string]$Out,

    [string]$OutDir = $env:VID2TEXT_OUT_DIR,

    [string]$SummaryOut,

    [string]$Subtitles = $env:VID2TEXT_SUBTITLES,

    [string]$CookiesFromBrowser = $env:VID2TEXT_COOKIES_FROM_BROWSER,

    [string]$Cookies = $env:VID2TEXT_COOKIES_FILE,

    [switch]$Diagnose,

    [switch]$SkipInstall,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"
trap {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONUTF8 = "1"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
}
catch {
    # Older hosts can ignore this; PYTHONUTF8 still fixes child Python output.
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-ProjectPython {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @{
            File = $venvPython
            Args = @()
        }
    }

    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{
            File = $pyLauncher.Source
            Args = @("-3")
        }
    }

    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            File = $python.Source
            Args = @()
        }
    }

    throw "Python wurde nicht gefunden. Installiere Python 3 und starte den Befehl erneut."
}

function Ensure-Venv {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    Write-Step "Virtuelle Umgebung wird erstellt"
    $python = Get-ProjectPython
    & $python.File @($python.Args + @("-m", "venv", ".venv"))

    if (-not (Test-Path $venvPython)) {
        throw "Die virtuelle Umgebung konnte nicht erstellt werden: $venvPython"
    }
    return $venvPython
}

function Ensure-PythonDependencies {
    param([string]$PythonExe)

    if ($SkipInstall) {
        Write-Step "Python-Installation wird uebersprungen (-SkipInstall)"
        return
    }

    Write-Step "Python-Abhaengigkeiten werden installiert/aktualisiert"
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r (Join-Path $Root "requirements.txt")
}

function Ensure-YtDlp {
    $ytDlp = Join-Path $Root "yt-dlp.exe"
    if (Test-Path $ytDlp) {
        return
    }

    Write-Step "yt-dlp.exe wird heruntergeladen"
    $url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    Invoke-WebRequest -Uri $url -OutFile $ytDlp
}

function Find-LocalFfmpegBin {
    $tools = Join-Path $Root "tools"
    if (-not (Test-Path $tools)) {
        return $null
    }

    $ffmpeg = Get-ChildItem -Path $tools -Recurse -Filter "ffmpeg.exe" -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($ffmpeg) {
        return $ffmpeg.DirectoryName
    }
    return $null
}

function Ensure-Ffmpeg {
    $systemFfmpeg = Get-Command "ffmpeg" -ErrorAction SilentlyContinue
    if ($systemFfmpeg) {
        return
    }

    $localBin = Find-LocalFfmpegBin
    if ($localBin) {
        $env:PATH = "$localBin;$env:PATH"
        return
    }

    if ($SkipInstall) {
        throw "ffmpeg wurde nicht gefunden. Entferne -SkipInstall oder installiere ffmpeg manuell."
    }

    Write-Step "FFmpeg wird lokal nach tools\ heruntergeladen"
    $tools = Join-Path $Root "tools"
    New-Item -ItemType Directory -Force -Path $tools | Out-Null

    $zipPath = Join-Path $tools "ffmpeg-release-essentials.zip"
    $extractPath = Join-Path $tools "ffmpeg"
    $downloadUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

    if (-not (Test-Path $zipPath)) {
        Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath
    }

    if (-not (Test-Path $extractPath)) {
        New-Item -ItemType Directory -Force -Path $extractPath | Out-Null
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
    }

    $localBin = Find-LocalFfmpegBin
    if (-not $localBin) {
        throw "FFmpeg wurde heruntergeladen, aber ffmpeg.exe konnte nicht gefunden werden."
    }
    $env:PATH = "$localBin;$env:PATH"
}

function Build-TranscribeArgs {
    $args = @()

    if ($Url) {
        $args += @("--url", $Url)
    }
    elseif ($InputPathOrUrl -match "^https?://") {
        $args += @("--url", $InputPathOrUrl)
    }
    elseif ($InputPathOrUrl) {
        $args += $InputPathOrUrl
    }
    elseif (-not $Diagnose) {
        throw "Bitte gib eine URL oder Audiodatei an. Beispiel: .\run.ps1 `"https://www.youtube.com/watch?v=...`" -Summarize"
    }

    $args += @("--model", $Model, "--device", $Device)

    if ($Summarize) {
        $args += "--summarize"
    }
    if ($Out) {
        $args += @("--out", $Out)
    }
    if ($OutDir) {
        $args += @("--out-dir", $OutDir)
    }
    if ($SummaryOut) {
        $args += @("--summary-out", $SummaryOut)
    }
    if ($Subtitles) {
        $args += @("--subtitles", $Subtitles)
    }
    if ($CookiesFromBrowser) {
        $args += @("--cookies-from-browser", $CookiesFromBrowser)
    }
    if ($Cookies) {
        $args += @("--cookies", $Cookies)
    }
    if ($ExtraArgs) {
        $args += $ExtraArgs
    }

    return $args
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "downloads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "transcripts") | Out-Null

$pythonExe = Ensure-Venv
Ensure-PythonDependencies -PythonExe $pythonExe
Ensure-YtDlp
Ensure-Ffmpeg

if ($Diagnose) {
    Write-Step "Diagnose wird ausgefuehrt"
    & $pythonExe (Join-Path $Root "diagnose.py")
    exit $LASTEXITCODE
}

$transcribeArgs = Build-TranscribeArgs
Write-Step "Transkription wird gestartet"
& $pythonExe (Join-Path $Root "transcribe_whisper.py") @transcribeArgs
exit $LASTEXITCODE
