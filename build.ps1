# Builds a single-file dist\LocalAI.exe. Needs: Python 3.10+, pip install pywebview pyinstaller pillow
# (keep this file ASCII-only: Windows PowerShell 5.1 misreads BOM-less UTF-8)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python tools\make_icon.py
python -m PyInstaller --noconfirm --onefile --windowed --name LocalAI --icon app\icon.ico `
    --add-data "ui;ui" --paths app --hidden-import catalog --hidden-import engine --hidden-import hw --hidden-import server `
    app\main.py
Write-Host "Done: $PSScriptRoot\dist\LocalAI.exe"
