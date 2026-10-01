$ErrorActionPreference = 'Stop'

$frontendRoot = 'C:\Users\Administrator\Downloads\Incident-2\frontend'
Set-Location $frontendRoot

Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host 'Starting IncidentIQ frontend...'
npm run dev
