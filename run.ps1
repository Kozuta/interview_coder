# Запуск кодирования (PowerShell)
$Root = $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Создаю venv..."
    python -m venv .venv
    & $Python -m pip install -e .
}

$Project = if ($args.Count -gt 0) { $args[0] } else { "projects\example" }
& $Python -m coder run --project $Project
