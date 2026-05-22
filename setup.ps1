# One-time install
$Root = $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -e .
Write-Host ""
Write-Host "Done. Next:"
Write-Host "  .\ui.ps1   - browser UI"
Write-Host "  .\run.ps1  - run coding (projects\example)"
Write-Host ""
Write-Host "Copy .env.example to .env and set OPENAI_API_KEY"
