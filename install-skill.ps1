# Installiert den Skill "video-zu-text" global fuer Claude Code.
#
# Global heisst: der Skill liegt unter ~\.claude\skills und steht damit in jedem
# Projekt zur Verfuegung, nicht nur in diesem Repository.
param(
    [switch]$Copy,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $Root ".claude\skills\video-zu-text"
$TargetDir = if ($env:CLAUDE_SKILLS_DIR) { $env:CLAUDE_SKILLS_DIR } else { Join-Path $HOME ".claude\skills" }
$Target = Join-Path $TargetDir "video-zu-text"

if ($Uninstall) {
    if (Test-Path $Target) {
        Remove-Item -Recurse -Force $Target
        Write-Host "Entfernt: $Target"
    } else {
        Write-Host "Nichts zu entfernen unter $Target"
    }
    exit 0
}

if (-not (Test-Path (Join-Path $Source "SKILL.md"))) {
    throw "$Source\SKILL.md fehlt."
}

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }

# Symlinks brauchen unter Windows Entwicklermodus oder Adminrechte; bei einem
# Fehlschlag wird kopiert, damit die Installation trotzdem durchlaeuft.
$linked = $false
if (-not $Copy) {
    try {
        New-Item -ItemType SymbolicLink -Path $Target -Target $Source -ErrorAction Stop | Out-Null
        $linked = $true
        Write-Host "Symlink erstellt: $Target -> $Source"
    } catch {
        Write-Host "Symlink nicht moeglich (Entwicklermodus aus?), es wird kopiert."
    }
}

if (-not $linked) {
    Copy-Item -Recurse -Force $Source $Target
    Write-Host "Kopiert: $Source -> $Target"
}

Set-Content -Path (Join-Path $Target ".vid2text-home") -Value $Root -Encoding UTF8

Write-Host ""
Write-Host "Fertig. Der Skill ist jetzt global verfuegbar."
Write-Host "vid2text-Repository: $Root"
Write-Host ""
Write-Host 'Naechster Schritt: neue Claude-Code-Sitzung starten und z. B. sagen:'
Write-Host '  "Erstelle Untertitel fuer https://www.youtube.com/watch?v=..."'
