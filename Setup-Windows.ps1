$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
py -3 -m venv .venv
if($LASTEXITCODE -ne 0){throw 'Install Python3.11+ with Tkinter first.'}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if($LASTEXITCODE -ne 0){throw 'Python dependency installation failed.'}
Write-Host 'Ready: double-click launch_studio.cmd. Preview works without hardware.'
