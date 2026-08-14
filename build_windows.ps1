$ErrorActionPreference = "Stop"

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $projectDirectory

try {
    # PyInstaller writes its progress log to stderr. With ErrorActionPreference
    # set to Stop, PowerShell treats those ordinary INFO lines as a terminating
    # error, so the build is run with the preference relaxed and judged on its
    # exit code instead.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    python -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --windowed `
        --name "Subscription Tracker" `
        --collect-all tkcalendar `
        --hidden-import babel.numbers `
        main.py

    $buildExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference

    if ($buildExitCode -ne 0) {
        throw "PyInstaller failed with exit code $buildExitCode."
    }

    $executable = Join-Path $projectDirectory "dist\Subscription Tracker.exe"
    if (-not (Test-Path $executable)) {
        throw "PyInstaller reported success but $executable is missing."
    }

    # Name the archive after APP_VERSION in main.py so a build is always
    # traceable to the source it came from.
    $versionLine = Select-String -Path (Join-Path $projectDirectory "main.py") -Pattern '^APP_VERSION = "(.+)"' | Select-Object -First 1
    if (-not $versionLine) { throw "Could not read APP_VERSION from main.py." }
    $version = $versionLine.Matches[0].Groups[1].Value
    $major = $version.Split(".")[0]

    # Package the executable on its own. The personal database lives in
    # %LOCALAPPDATA% and must never be included in something handed to a tester.
    $stamp = Get-Date -Format "yyyy-MM-dd"
    $archive = Join-Path $projectDirectory "dist\Subscription Tracker V$major ($stamp).zip"
    if (Test-Path $archive) { Remove-Item $archive -Force }

    $readme = Join-Path $projectDirectory "dist\READ ME FIRST.txt"
    Copy-Item (Join-Path $projectDirectory "TESTERS.txt") $readme -Force
    Compress-Archive -Path $executable, $readme -DestinationPath $archive
    Remove-Item $readme -Force

    $sizeInMb = [math]::Round((Get-Item $executable).Length / 1MB, 1)
    $hash = (Get-FileHash $executable -Algorithm SHA256).Hash

    Write-Host ""
    Write-Host "Version    : $version"
    Write-Host "Executable : $executable ($sizeInMb MB)"
    Write-Host "Share this : $archive"
    Write-Host "SHA-256    : $hash"
}
finally {
    Pop-Location
}
