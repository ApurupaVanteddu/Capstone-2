$ErrorActionPreference = 'Stop'

$projectRoot = 'C:\Users\Administrator\Downloads\Incident-2'
Set-Location $projectRoot

Get-Process uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host 'Starting IncidentIQ backend...'
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
