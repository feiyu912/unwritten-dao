<#
.SYNOPSIS
Start the world server from the repository root with the private .env file.

.DESCRIPTION
Runs: uv run uvicorn --env-file .env world_server.app:app
If .env is missing, prints copy instructions and exits. This script never
creates, edits, or overwrites .env.

Any remaining arguments are passed to uvicorn. With no arguments it listens on
127.0.0.1:8000, matching the runbook.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $UvicornArgs
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot '.env'
$templatePath = Join-Path $repoRoot '.env.example'

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    Write-Host "No .env found at $envPath"
    Write-Host "From the repository root ($repoRoot):"
    Write-Host "  Set-Location '$repoRoot'"
    Write-Host '  if (-not (Test-Path .env)) { Copy-Item .env.example .env }'
    Write-Host '  notepad .env'
    Write-Host 'Or copy directly from anywhere with absolute paths:'
    Write-Host "  if (-not (Test-Path -LiteralPath '$envPath')) { Copy-Item -LiteralPath '$templatePath' -Destination '$envPath' }"
    Write-Host 'Then run this script again.'
    Write-Host 'This script will not create or overwrite .env automatically.'
    exit 1
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uv) {
    Write-Error "uv is not on PATH. Install uv and run 'uv sync --all-packages' first."
    exit 1
}

Push-Location $repoRoot
try {
    $arguments = @('run', 'uvicorn', '--env-file', '.env', 'world_server.app:app')
    if (-not $UvicornArgs) {
        $arguments += @('--host', '127.0.0.1', '--port', '8000')
    } else {
        $arguments += $UvicornArgs
    }
    & $uv.Source @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
