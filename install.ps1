Write-Host "=== Sprawdzanie CMake ==="

if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    Write-Error "CMake NIE jest zainstalowany lub nie ma go w PATH"
    exit 1
}

cmake --version

Write-Host "=== Tworzenie virtualenv (Python 3.10) ==="
py -3.10 -m venv .venv

Write-Host "=== Aktywacja virtualenv ==="
. .\.venv\Scripts\Activate.ps1

Write-Host "=== Aktualizacja pip ==="
python -m pip install --upgrade pip

Write-Host "=== Instalacja dlib ==="
pip install dlib

Write-Host "=== Instalacja zakonczona ==="
Write-Host "Uruchom run.ps1 aby wystartowac aplikacje"

Pause
