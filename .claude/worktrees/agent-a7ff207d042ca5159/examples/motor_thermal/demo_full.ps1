# M4 demo (P4-15): baseline -> coolant change -> diff -> plan -> run --plan latest -> status -> report --html + explain.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File examples/motor_thermal/demo_full.ps1
# Env: REVAL, DEMO_FULL=1 (keep all claims; hours), DEMO_KEEP=<dir> (copy transcript/JSON/report), DEMO_LOG=<file>.
$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = (Resolve-Path (Join-Path $Here '..\..')).Path
if ($env:REVAL) { $R = $env:REVAL }
elseif (Test-Path (Join-Path $Repo '.venv\Scripts\reval.exe')) { $R = Join-Path $Repo '.venv\Scripts\reval.exe' }
else { $R = 'reval' }
$Py = if (Test-Path (Join-Path $Repo '.venv\Scripts\python.exe')) { Join-Path $Repo '.venv\Scripts\python.exe' } else { 'python' }

$Work = Join-Path ([IO.Path]::GetTempPath()) ("reval-demo-" + [Guid]::NewGuid().ToString('N'))
$Proj = Join-Path $Work 'motor'
$Out = Join-Path $Work 'demo_output.txt'
New-Item -ItemType Directory -Path $Proj | Out-Null

try {
  & robocopy $Here $Proj /E /XD .reval __pycache__ notebooks /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }

  $env:GIT_AUTHOR_NAME = 'demo'; $env:GIT_AUTHOR_EMAIL = 'demo@example.com'
  $env:GIT_COMMITTER_NAME = 'demo'; $env:GIT_COMMITTER_EMAIL = 'demo@example.com'
  Set-Location $Proj
  git init -q
  git config core.autocrlf false
  [IO.File]::WriteAllText((Join-Path $Proj '.gitignore'), ".reval/`n__pycache__/`ndata/`nmodels/`n")

  # Trim the COPY's claims to a few subjects (ML producers take ~6 s each); the real reval.yaml is untouched.
  if (-not $env:DEMO_FULL) {
    $man = Join-Path $Proj 'reval.yaml'
    $inClaims = $false
    $kept = foreach ($line in [IO.File]::ReadAllLines($man)) {
      if ($line -match '^claims:') { $inClaims = $true }
      if ($inClaims -and $line -match '^  - \{id' -and $line -notmatch 'subject: (DC-P01|DC-R01|SHAFT-1)\}') { continue }
      $line
    }
    [IO.File]::WriteAllText($man, (($kept -join "`n") + "`n"))
  }

  function Add-Out([string]$Text) { Add-Content -Path $Out -Value $Text -Encoding utf8 }
  function Step([string]$Text) { Add-Out ''; Add-Out "`$ $Text" }
  function Set-Flow([string]$Value) {
    $p = Join-Path $Proj 'params\cooling.yaml'
    $t = [IO.File]::ReadAllText($p) -replace '(?m)^flow_scale: .*$', "flow_scale: $Value"
    [IO.File]::WriteAllText($p, $t)
  }
  function Save-Commit([string]$Msg) { git add -A; git commit -q -m $Msg }
  # Exit codes 1/2 (stale/violated) are expected results of diff/status, not failures.
  function Invoke-Reval {
    $ErrorActionPreference = 'Continue'
    $lines = & $R @args --project $Proj 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $lines | ForEach-Object { Add-Out $_ }
    if ($code -ne 0) { Add-Out "(exit code $code)" }
  }
  function Save-Json([string]$File, [string[]]$RevalArgs) {
    $ErrorActionPreference = 'Continue'
    $txt = & $R @RevalArgs --project $Proj 2>$null
    [IO.File]::WriteAllText((Join-Path $Work $File), (($txt -join "`n") + "`n"))
  }

  Step 'reval snapshot --write ; reval run --all   (baseline, flow_scale: 1.0)'
  Invoke-Reval snapshot --write
  Invoke-Reval run --all
  Save-Commit 'baseline lock'

  Set-Flow '0.95'
  Step 'flow_scale 1.0 -> 0.95 ; reval snapshot --write ; reval diff HEAD~1 HEAD'
  Invoke-Reval snapshot --write
  Save-Commit 'flow_scale 0.95'
  Invoke-Reval diff HEAD~1 HEAD

  Step 'reval status   (before restoration)'
  Invoke-Reval status
  Save-Json 'status_before.json' @('status', '--format', 'json')

  Step 'reval plan'
  Invoke-Reval plan
  Save-Json 'plan.json' @('plan', '--format', 'json')

  Step 'reval run --plan latest'
  Invoke-Reval run --plan latest

  Step 'reval status   (after restoration)'
  Invoke-Reval status
  Save-Json 'status_after.json' @('status', '--format', 'json')

  Step 'reval report --html --out report.html'
  $report = Join-Path $Work 'report.html'
  Invoke-Reval report --html --out $report
  if (-not (Test-Path $report) -or (Get-Item $report).Length -eq 0) { throw 'report.html missing or empty' }
  Add-Out "report.html: $((Get-Item $report).Length) bytes"

  $Claim = if ($env:DEMO_CLAIM) { $env:DEMO_CLAIM } else { 'C-R01-PM' }
  Step "reval explain $Claim"
  Invoke-Reval explain $Claim

  Get-Content $Out -Encoding utf8
  if ($env:DEMO_KEEP) {
    New-Item -ItemType Directory -Force -Path $env:DEMO_KEEP | Out-Null
    Copy-Item $Out (Join-Path $env:DEMO_KEEP 'demo_output.txt')
    Copy-Item (Join-Path $Work '*.json') $env:DEMO_KEEP
    Copy-Item $report $env:DEMO_KEEP
    Write-Output "kept transcript, JSON and report.html in $env:DEMO_KEEP"
  }
  if ($env:DEMO_LOG) {
    & $Py (Join-Path $Here 'scripts\demo_log.py') --plan (Join-Path $Work 'plan.json') --before (Join-Path $Work 'status_before.json') --after (Join-Path $Work 'status_after.json') --transcript $Out --out $env:DEMO_LOG
  }
  Write-Output 'demo_full: OK'
}
finally {
  Set-Location $Here
  Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
