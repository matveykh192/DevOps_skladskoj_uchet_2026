# Run from repository root in VS Code PowerShell: .\scripts\verify.ps1
# Same mandatory gate as Makefile's `make verify` (Ruff, formatting, Bandit, pytest coverage).
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))

function Invoke-CheckedDocker {
    param([string]$Label, [string[]]$ComposeArgs)
    Write-Host "`n===== $Label =====" -ForegroundColor Cyan
    & docker compose -p warehouse-lr3-test -f docker-compose.test.yml @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed (exit code $LASTEXITCODE). Verification stopped."
    }
}

try {
    Invoke-CheckedDocker 'Ruff lint' @('run', '--build', '--rm', '--no-deps', 'test-runner', 'ruff', 'check', 'app', 'tests')
    Invoke-CheckedDocker 'Ruff format check' @('run', '--rm', '--no-deps', 'test-runner', 'ruff', 'format', '--check', 'app', 'tests')
    Invoke-CheckedDocker 'Bandit SAST' @('run', '--rm', '--no-deps', 'test-runner', 'bandit', '-r', 'app', '-ll')
    Invoke-CheckedDocker 'Pytest + 60% branch coverage' @('run', '--rm', 'test-runner')
    Write-Host "`nALL MANDATORY CURRENT-STAGE CHECKS PASSED" -ForegroundColor Green
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
