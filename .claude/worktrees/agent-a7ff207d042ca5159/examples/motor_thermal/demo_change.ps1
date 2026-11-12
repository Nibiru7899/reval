# Interim demo (P3-08): coolant flow_scale change on a throwaway copy of the motor project.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File examples/motor_thermal/demo_change.ps1
# Needs data/ and models/ present (see README.md). The real params/ are never touched.
$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = (Resolve-Path (Join-Path $Here '..\..')).Path
if ($env:REVAL) { $R = $env:REVAL }
elseif (Test-Path (Join-Path $Repo '.venv\Scripts\reval.exe')) { $R = Join-Path $Repo '.venv\Scripts\reval.exe' }
else { $R = 'reval' }

$Work = Join-Path ([IO.Path]::GetTempPath()) ("reval-demo-" + [Guid]::NewGuid().ToString('N'))
$Proj = Join-Path $Work 'motor'
$Out = Join-Path $Work 'demo_output.txt'
New-Item -ItemType Directory -Path $Proj | Out-Null

try {
  # Copy the project (including git-ignored data/ and models/, which the lock hashes), minus caches and stores.
  & robocopy $Here $Proj /E /XD .reval __pycache__ notebooks /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }

  $env:GIT_AUTHOR_NAME = 'demo'; $env:GIT_AUTHOR_EMAIL = 'demo@example.com'
  $env:GIT_COMMITTER_NAME = 'demo'; $env:GIT_COMMITTER_EMAIL = 'demo@example.com'
  Set-Location $Proj
  git init -q
  git config core.autocrlf false
  [IO.File]::WriteAllText((Join-Path $Proj '.gitignore'), ".reval/`n__pycache__/`ndata/`nmodels/`n")

  # The full manifest declares ~170 claims, and `run --all` over all of them takes hours. The demo trims the COPY's
  # claim list to a few subjects (set DEMO_FULL=1 to keep everything); the real reval.yaml is untouched.
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
  function Set-Flow([string]$Value) {
    $p = Join-Path $Proj 'params\cooling.yaml'
    $t = [IO.File]::ReadAllText($p) -replace '(?m)^flow_scale: .*$', "flow_scale: $Value"
    [IO.File]::WriteAllText($p, $t)
  }
  function Save-Commit([string]$Msg) { git add -A; git commit -q -m $Msg }
  # `reval diff` exits 1 or 2 when claims are stale or violated; that is the expected result here.
  function Invoke-Reval {
    $ErrorActionPreference = 'Continue'
    $lines = & $R @args --project $Proj 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $lines | ForEach-Object { Add-Out $_ }
    if ($code -ne 0) { Add-Out "(exit code $code)" }
  }

  Add-Out '$ reval snapshot --write ; reval run --all   (baseline, flow_scale: 1.0)'
  Invoke-Reval snapshot --write
  Invoke-Reval run --all
  Save-Commit 'baseline lock'

  Set-Flow '0.95'
  Add-Out ''
  Add-Out '$ flow_scale 1.0 -> 0.95 ; reval snapshot --write ; reval diff HEAD~1 HEAD'
  Invoke-Reval snapshot --write
  Save-Commit 'flow_scale 0.95'
  Invoke-Reval diff HEAD~1 HEAD

  Set-Flow '0.75'
  Add-Out ''
  Add-Out '$ flow_scale 0.95 -> 0.75 ; reval snapshot --write ; reval diff HEAD~1 HEAD'
  Invoke-Reval snapshot --write
  Save-Commit 'flow_scale 0.75'
  Invoke-Reval diff HEAD~1 HEAD

  Get-Content $Out -Encoding utf8

  # Fill the marked block of DEMO.md with this output (the only file of the real project this script edits).
  $demo = Join-Path $Here 'DEMO.md'
  $doc = [IO.File]::ReadAllText($demo)
  $body = ([IO.File]::ReadAllText($Out, [Text.Encoding]::UTF8)).TrimEnd() -replace "`r`n", "`n"
  $block = "<!-- demo-output:start -->`n" + '```text' + "`n$body`n" + '```' + "`n<!-- demo-output:end -->"
  $new = [regex]::Replace($doc, '(?s)<!-- demo-output:start -->.*?<!-- demo-output:end -->', { param($m) $block })
  [IO.File]::WriteAllText($demo, $new)
  Write-Output "demo output written to $demo"
}
finally {
  Set-Location $Here
  Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
