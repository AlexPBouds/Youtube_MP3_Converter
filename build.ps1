# Builds a single-file Windows executable of the GUI app.
# Output: dist\YoutubeMP3Converter.exe

$ErrorActionPreference = "Stop"

Write-Host "Installing build requirements..." -ForegroundColor Cyan
python -m pip install --quiet --upgrade pyinstaller

Write-Host "Building executable..." -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "NotAVirus" `
    --collect-all imageio_ffmpeg `
    converter_gui.py

Write-Host ""
Write-Host "Done. Your app is at: dist\NotAVirus.exe" -ForegroundColor Green
