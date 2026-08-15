# Wrapper around the vid2text repository so the skill works from any directory.
#
# Resolves where vid2text lives, bootstraps it if needed, then hands over to the
# repo's run.ps1 (which sets up .venv, yt-dlp and ffmpeg). Output lands in the
# caller's working directory unless -OutDir says otherwise, so transcripts do
# not disappear into a checkout the user never opens.
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

$SkillDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$HomeFile = Join-Path $SkillDir ".vid2text-home"
$RepoUrl = if ($env:VID2TEXT_REPO_URL) { $env:VID2TEXT_REPO_URL } else { "https://github.com/MarcusBaitz/vid2text.git" }
$CallerPwd = (Get-Location).Path

function Write-Step { param([string]$Message) Write-Host "==> $Message" }

function Test-Vid2TextRepo {
    param([string]$Path)
    if (-not $Path) { return $false }
    return (Test-Path (Join-Path $Path "transcribe_whisper.py")) -and (Test-Path (Join-Path $Path "run.ps1"))
}

function Resolve-Vid2TextHome {
    if (Test-Vid2TextRepo $env:VID2TEXT_HOME) { return $env:VID2TEXT_HOME }

    if (Test-Path $HomeFile) {
        $remembered = (Get-Content $HomeFile -First 1).Trim()
        if (Test-Vid2TextRepo $remembered) { return $remembered }
    }

    # The skill may live inside the repo itself (.claude\skills\video-zu-text).
    $inRepo = Split-Path -Parent (Split-Path -Parent $SkillDir)
    if (Test-Vid2TextRepo $inRepo) { return $inRepo }

    $candidates = @(
        $CallerPwd,
        (Join-Path $HOME "vid2text"),
        (Join-Path $HOME "projects\vid2text"),
        (Join-Path $HOME "Projekte\vid2text"),
        (Join-Path $HOME "git\vid2text"),
        (Join-Path $HOME "code\vid2text"),
        (Join-Path $HOME "source\repos\vid2text"),
        (Join-Path $HOME "Documents\vid2text"),
        (Join-Path $HOME ".vid2text")
    )
    foreach ($candidate in $candidates) {
        if (Test-Vid2TextRepo $candidate) { return $candidate }
    }

    if ($env:VID2TEXT_NO_CLONE -eq "1") {
        throw "vid2text wurde nicht gefunden und VID2TEXT_NO_CLONE=1 verbietet das Klonen. Setze VID2TEXT_HOME auf dein Repository."
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "vid2text wurde nicht gefunden und git ist nicht installiert. Setze VID2TEXT_HOME auf dein Repository."
    }

    $target = Join-Path $HOME ".vid2text"
    Write-Step "vid2text wurde nicht gefunden. Klone $RepoUrl nach $target"
    git clone --depth 1 $RepoUrl $target
    if (-not (Test-Vid2TextRepo $target)) {
        throw "Klonen fehlgeschlagen. Setze VID2TEXT_HOME manuell auf dein vid2text-Verzeichnis."
    }
    return $target
}

function ConvertTo-AbsolutePath {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    return (Join-Path $CallerPwd $Path)
}

# Translate the long options from SKILL.md into run.ps1's parameter names, and
# make user-supplied paths absolute before run.ps1 changes directory - relative
# paths would otherwise resolve against the checkout instead of the caller.
$pathOptions = @{
    "--out-dir" = "-OutDir"; "-outdir" = "-OutDir"
    "--out" = "-Out"; "-out" = "-Out"
    "--summary-out" = "-SummaryOut"; "-summaryout" = "-SummaryOut"
    "--cookies" = "-Cookies"; "-cookies" = "-Cookies"
}
$valueOptions = @{
    "--subtitles" = "-Subtitles"; "-subtitles" = "-Subtitles"
    "--model" = "-Model"; "-model" = "-Model"; "-m" = "-Model"
    "--device" = "-Device"; "-device" = "-Device"
    "--cookies-from-browser" = "-CookiesFromBrowser"
    "-cookiesfrombrowser" = "-CookiesFromBrowser"
}
$switchOptions = @{
    "--summarize" = "-Summarize"; "-summarize" = "-Summarize"
    "--skip-install" = "-SkipInstall"; "-skipinstall" = "-SkipInstall"
    "--diagnose" = "-Diagnose"; "-diagnose" = "-Diagnose"
}

$forwarded = @()
$passthrough = @()
$hasOutDir = $false
$hasOut = $false
$index = 0
while ($index -lt $Arguments.Count) {
    $current = $Arguments[$index]
    $key = $current.ToLowerInvariant()

    if ($pathOptions.ContainsKey($key)) {
        if ($index + 1 -ge $Arguments.Count) { throw "$current braucht einen Wert." }
        $mapped = $pathOptions[$key]
        if ($mapped -eq "-OutDir") { $hasOutDir = $true }
        if ($mapped -eq "-Out") { $hasOut = $true }
        $forwarded += @($mapped, (ConvertTo-AbsolutePath $Arguments[$index + 1]))
        $index += 2
    } elseif ($valueOptions.ContainsKey($key)) {
        if ($index + 1 -ge $Arguments.Count) { throw "$current braucht einen Wert." }
        $forwarded += @($valueOptions[$key], $Arguments[$index + 1])
        $index += 2
    } elseif ($switchOptions.ContainsKey($key)) {
        $forwarded += $switchOptions[$key]
        $index += 1
    } elseif ($current.StartsWith("-")) {
        # Unknown flags belong to transcribe_whisper.py. PowerShell would try to
        # bind them to run.ps1 parameters, so they go behind the -- separator.
        # Their value travels with them, otherwise it would look like the input
        # path and bind to run.ps1's positional parameter.
        $passthrough += $current
        $index += 1
        if ($index -lt $Arguments.Count -and -not $Arguments[$index].StartsWith("-")) {
            $passthrough += $Arguments[$index]
            $index += 1
        }
    } else {
        if (Test-Path -LiteralPath $current) {
            $forwarded += (ConvertTo-AbsolutePath $current)
        } else {
            $forwarded += $current
        }
        $index += 1
    }
}

if ($forwarded.Count -eq 0) {
    throw 'Bitte gib eine URL oder eine Mediendatei an. Beispiel: vid2text.ps1 "https://..." --subtitles srt'
}

$root = Resolve-Vid2TextHome
Set-Content -Path $HomeFile -Value $root -Encoding UTF8
Write-Step "vid2text: $root"

# An older checkout may predate these flags; run.ps1 would then bind the value
# to the wrong parameter, so fail loudly instead of transcribing the wrong thing.
$runScript = Get-Content (Join-Path $root "run.ps1") -Raw
foreach ($flag in @("Subtitles", "OutDir")) {
    if (($forwarded -contains "-$flag") -and ($runScript -notmatch "\`$$flag")) {
        throw "Das gefundene vid2text unter $root kennt -$flag noch nicht. Aktualisiere es mit: git -C `"$root`" pull"
    }
}

if (-not $hasOutDir -and -not $hasOut -and ($runScript -match '\$OutDir')) {
    $forwarded += @("-OutDir", (Join-Path $CallerPwd "transcripts"))
}

if ($passthrough.Count -gt 0) {
    $forwarded += "--"
    $forwarded += $passthrough
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $root "run.ps1") @forwarded
exit $LASTEXITCODE
