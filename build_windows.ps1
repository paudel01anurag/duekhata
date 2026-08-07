$ErrorActionPreference = "Stop"

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $projectDirectory

try {
    python -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --windowed `
        --name "Subscription Tracker" `
        --collect-all tkcalendar `
        --hidden-import babel.numbers `
        main.py

    Write-Host "Portable application created at: dist\Subscription Tracker.exe"
}
finally {
    Pop-Location
}
