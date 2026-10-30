# Run from repository root: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_mutation.ps1
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source = Join-Path $root 'app\models.py'
$backupDir = Join-Path $root 'backups'
$reportDir = Join-Path $root 'reports'
$backup = Join-Path $backupDir 'models_before_mutation.py'
$report = Join-Path $reportDir 'mutation-test.txt'
$original = 'self.quantity < self.minimum_stock'
$mutant = 'self.quantity <= self.minimum_stock'

New-Item -ItemType Directory -Force $backupDir, $reportDir | Out-Null
if (-not (Test-Path $source)) { throw "Missing file: $source" }
if (Test-Path $backup) {
    throw "Backup already exists: $backup. Check whether an earlier run was interrupted and restore manually before retrying."
}

$sourceText = [System.IO.File]::ReadAllText($source)
$matches = [regex]::Matches($sourceText, [regex]::Escape($original)).Count
if ($matches -ne 1) { throw "Expected exactly one comparison '$original', found $matches; no files changed." }

Copy-Item -LiteralPath $source -Destination $backup -ErrorAction Stop
$restoreSuccessful = $false
try {
    $modified = $sourceText.Replace($original, $mutant)
    [System.IO.File]::WriteAllText($source, $modified, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "MUTATION ACTIVE: < changed to <= in app/models.py" -ForegroundColor Yellow
    Write-Host "Running isolated boundary test; it MUST fail for the mutation to be detected."
    Push-Location $root
    try {
        $ErrorActionPreference = 'Continue' # Docker writes routine progress to stderr on Windows PowerShell 5.1.
        & docker compose -p warehouse-lr3-test -f docker-compose.test.yml run --build --rm test-runner pytest -q tests/test_minimum_stock.py -k boundary_exactly_equal_is_not_low 2>&1 | Tee-Object -FilePath $report
        $testExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = 'Stop'
        Pop-Location
    }
}
finally {
    # Always restore exact original bytes, including encoding and line endings.
    Copy-Item -LiteralPath $backup -Destination $source -Force -ErrorAction Stop
    $restoreSuccessful = ((Get-FileHash $backup -Algorithm SHA256).Hash -eq (Get-FileHash $source -Algorithm SHA256).Hash)
    if (-not $restoreSuccessful) { throw 'CRITICAL: source restoration could not be verified. Restore manually from backups/models_before_mutation.py.' }
    Remove-Item -LiteralPath $backup -Force
    Write-Host 'Original app/models.py restored and SHA256 verified.' -ForegroundColor Green
}

if ($testExitCode -eq 0) {
    Write-Host "FAIL: mutation survived; test did not catch incorrect <= rule. See $report" -ForegroundColor Red
    exit 1
}

$reportText = [System.IO.File]::ReadAllText($report)
if ($reportText -notmatch 'FAILED\s+tests/test_minimum_stock\.py::test_boundary_exactly_equal_is_not_low') {
    Write-Host "INCONCLUSIVE: test command failed, but no expected test failure detected. Check $report" -ForegroundColor Red
    exit 2
}
if ($reportText -notmatch 'AssertionError') {
    Write-Host "INCONCLUSIVE: test failed without a visible assertion. Check $report" -ForegroundColor Red
    exit 2
}
Write-Host "PASS: boundary test caught the intentional mutation (< -> <=). Report: $report" -ForegroundColor Green
