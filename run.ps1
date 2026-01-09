Write-Host "=== Aktywacja virtualenv ==="
. .\.venv\Scripts\Activate.ps1

Write-Host "=== Instalacja requirements.txt ==="
pip install -r requirements.txt

Write-Host "=== Uruchamianie aplikacji ==="
python -m backend.app

Pause
