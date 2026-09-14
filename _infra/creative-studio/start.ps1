$ErrorActionPreference = 'Stop'
$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$studioUrl = 'http://127.0.0.1:8765'
$studioActive = $null
try { $studioActive = Invoke-RestMethod "$studioUrl/api/bootstrap" -TimeoutSec 2 } catch {}
if ($studioActive) {
    if ([IO.Path]::GetFullPath($studioActive.root) -ne $studioRoot) {
        throw 'Port 8765 belongs to a different workspace. Stop its server before starting this Studio.'
    }
} else {
    $studioPython = (Get-Command python).Source
    Start-Process -FilePath $studioPython -ArgumentList @('_infra/creative-studio/server.py') -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server.stderr.log')
    for ($studioAttempt=0; $studioAttempt -lt 20; $studioAttempt++) {
        try { $studioActive = Invoke-RestMethod "$studioUrl/api/bootstrap" -TimeoutSec 1; break } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $studioActive) { throw 'Studio did not start. See server.stderr.log.' }
}
Start-Process $studioUrl -WindowStyle Hidden
