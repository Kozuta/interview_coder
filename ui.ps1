# Streamlit UI (PowerShell)
$Root = $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Создаю venv..."
    python -m venv .venv
    & $Python -m pip install -e .
}

& $Python -m streamlit run ui\app.py
