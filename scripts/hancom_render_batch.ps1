<#
.SYNOPSIS
    Scaled real-Hancom render leg for the S-063 M9 corpus (FR-003).

.DESCRIPTION
    Ports the open-rate hardening posture onto the P0 render probe: one COM
    session reused across jobs, a per-file checkpoint APPENDED immediately
    (crash loses at most one file), RESUME that skips rows already final, a
    single retry pass over this run's errored jobs (retried=$true rows win the
    join downstream), and COM-session recycle after any error. Render failures
    are DATA (unverified bucket), not run failures: the script exits 0 unless
    the job list itself cannot be read.

    PS 5.1: ConvertFrom-Json emits a JSON array as one Object[] item — jobs are
    re-enumerated explicitly (same fix as the P0 probe).
#>
param(
    [Parameter(Mandatory = $true)][string] $Jobs,
    [Parameter(Mandatory = $true)][string] $OutJsonl,
    [int] $ProgressEvery = 25
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Write-JsonLine {
    param([string] $Path, [object] $Record)
    Add-Content -LiteralPath $Path -Value ($Record | ConvertTo-Json -Depth 6 -Compress) -Encoding UTF8
}

function New-Hwp {
    $obj = New-Object -ComObject "HWPFrame.HwpObject"
    try { $null = $obj.RegisterModule("FilePathCheckerModule", "FilePathCheckerModuleExample") } catch {}
    try { $null = $obj.SetMessageBoxMode(0x00020000) } catch {}
    return $obj
}

function Close-Hwp {
    param([object] $Hwp)
    if ($null -ne $Hwp) {
        try { $Hwp.Quit() | Out-Null } catch {}
        try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Hwp) | Out-Null } catch {}
    }
}

$jobsParsed = Get-Content -LiteralPath $Jobs -Raw -Encoding UTF8 | ConvertFrom-Json
$jobsList = @($jobsParsed | ForEach-Object { $_ })
if ($jobsList.Count -lt 1) { throw "render batch requires at least one job" }

$done = @{}
if (Test-Path -LiteralPath $OutJsonl) {
    foreach ($line in Get-Content -LiteralPath $OutJsonl -Encoding UTF8) {
        if (-not $line.Trim()) { continue }
        try { $row = $line | ConvertFrom-Json } catch { continue }
        if ($row.sourceId -and $row.final) { $done[[string]$row.sourceId] = $true }
    }
}

function Invoke-RenderJob {
    param([object] $Hwp, [object] $Job, [bool] $Retried)
    $sourceId = [string]$Job.sourceId
    $src = [string]$Job.src
    $pdf = [string]$Job.pdf
    $pdfDir = Split-Path -Parent $pdf
    if ($pdfDir) { New-Item -ItemType Directory -Force -Path $pdfDir | Out-Null }
    Remove-Item -LiteralPath $pdf -Force -ErrorAction SilentlyContinue

    $opened = $false
    $saved = $false
    $errorMessage = $null
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $opened = [bool]$Hwp.Open($src, "", "")
        if ($opened) { $saved = [bool]$Hwp.SaveAs($pdf, "PDF", "") }
    } catch {
        $errorMessage = $_.Exception.Message
    } finally {
        $watch.Stop()
        try { $Hwp.Clear(1) | Out-Null } catch {}
    }
    $pdfBytes = if (Test-Path -LiteralPath $pdf) { (Get-Item -LiteralPath $pdf).Length } else { 0 }
    Write-JsonLine $OutJsonl ([ordered]@{
        sourceId = $sourceId
        sourceSha256 = [string]$Job.sourceSha256
        stratum = [string]$Job.stratum
        opened = $opened
        saved = $saved
        pdfBytes = $pdfBytes
        renderMs = [Math]::Round($watch.Elapsed.TotalMilliseconds)
        error = $errorMessage
        retried = $Retried
        final = ($null -eq $errorMessage)
        measuredAt = [DateTime]::UtcNow.ToString("o")
    })
    return $errorMessage
}

$hwp = $null
$erroredJobs = New-Object System.Collections.ArrayList
try {
    $hwp = New-Hwp
    $version = $null
    try { $version = [string]$hwp.Version } catch {}
    if (-not (Test-Path -LiteralPath $OutJsonl)) {
        Write-JsonLine $OutJsonl ([ordered]@{
            _meta = "m9-render-batch-v1"
            generatedAt = [DateTime]::UtcNow.ToString("o")
            computerName = $env:COMPUTERNAME
            hancomBuild = $version
            powershell = $PSVersionTable.PSVersion.ToString()
            jobCount = $jobsList.Count
        })
    }

    $index = 0
    foreach ($job in $jobsList) {
        $index += 1
        $sourceId = [string]$job.sourceId
        if ($done.ContainsKey($sourceId)) { continue }
        $err = Invoke-RenderJob -Hwp $hwp -Job $job -Retried $false
        if ($null -ne $err) {
            [void]$erroredJobs.Add($job)
            Close-Hwp $hwp
            $hwp = New-Hwp
        }
        if (($index % $ProgressEvery) -eq 0) {
            Write-Host "render progress: $index / $($jobsList.Count)"
        }
    }

    # Single retry pass over THIS run's errored jobs (open-rate posture (d)).
    foreach ($job in $erroredJobs) {
        $err = Invoke-RenderJob -Hwp $hwp -Job $job -Retried $true
        if ($null -ne $err) {
            Close-Hwp $hwp
            $hwp = New-Hwp
        }
    }
} finally {
    Close-Hwp $hwp
}
exit 0
