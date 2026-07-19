<#
.SYNOPSIS
    Bounded five-file real-Hancom render timing spike for S-063 P0.

.DESCRIPTION
    Reads an ordered JSON job list, reuses one COM session, appends one receipt
    per file, and resumes already-final rows. Negative open controls must run
    first through hancom_open_rate.ps1; this script measures only the frozen five
    produced documents selected by m9_p0_prepare_box.py.
#>
param(
    [Parameter(Mandatory = $true)][string] $Jobs,
    [Parameter(Mandatory = $true)][string] $OutJsonl
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

# PS 5.1: ConvertFrom-Json emits a JSON array as ONE Object[] pipeline item, so
# @(...) would wrap it into a single-element list. Enumerate to get real rows.
$jobsParsed = Get-Content -LiteralPath $Jobs -Raw -Encoding UTF8 | ConvertFrom-Json
$jobsList = @($jobsParsed | ForEach-Object { $_ })
if ($jobsList.Count -ne 5) {
    throw "P0 render spike requires exactly five jobs; got $($jobsList.Count)"
}

$done = @{}
if (Test-Path -LiteralPath $OutJsonl) {
    foreach ($line in Get-Content -LiteralPath $OutJsonl -Encoding UTF8) {
        if (-not $line.Trim()) { continue }
        try { $row = $line | ConvertFrom-Json } catch { continue }
        if ($row.sourceId -and $row.final) { $done[[string]$row.sourceId] = $true }
    }
}

$hwp = $null
$failed = 0
try {
    $hwp = New-Hwp
    $version = $null
    try { $version = [string]$hwp.Version } catch {}
    if (-not (Test-Path -LiteralPath $OutJsonl)) {
        Write-JsonLine $OutJsonl ([ordered]@{
            _meta = "m9-p0-box-render-v1"
            generatedAt = [DateTime]::UtcNow.ToString("o")
            computerName = $env:COMPUTERNAME
            hancomBuild = $version
            powershell = $PSVersionTable.PSVersion.ToString()
            expectedJobs = 5
        })
    }

    foreach ($job in $jobsList) {
        $sourceId = [string]$job.sourceId
        if ($done.ContainsKey($sourceId)) { continue }
        $src = [string]$job.src
        $pdf = [string]$job.pdf
        $pdfDir = Split-Path -Parent $pdf
        if ($pdfDir) { New-Item -ItemType Directory -Force -Path $pdfDir | Out-Null }
        Remove-Item -LiteralPath $pdf -Force -ErrorAction SilentlyContinue

        $opened = $false
        $saved = $false
        $errorMessage = $null
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            $opened = [bool]$hwp.Open($src, "", "")
            if ($opened) { $saved = [bool]$hwp.SaveAs($pdf, "PDF", "") }
        } catch {
            $errorMessage = $_.Exception.Message
        } finally {
            $watch.Stop()
            try { $hwp.Clear(1) | Out-Null } catch {}
        }
        $pdfBytes = if (Test-Path -LiteralPath $pdf) { (Get-Item -LiteralPath $pdf).Length } else { 0 }
        $final = ($null -eq $errorMessage)
        if (-not $opened -or -not $saved -or $pdfBytes -le 0) { $failed += 1 }
        Write-JsonLine $OutJsonl ([ordered]@{
            sourceId = $sourceId
            sourceSha256 = [string]$job.sourceSha256
            opened = $opened
            saved = $saved
            pdfBytes = $pdfBytes
            renderMs = [Math]::Round($watch.Elapsed.TotalMilliseconds)
            error = $errorMessage
            final = $final
            measuredAt = [DateTime]::UtcNow.ToString("o")
        })

        if ($null -ne $errorMessage) {
            Close-Hwp $hwp
            $hwp = New-Hwp
        }
    }
} finally {
    Close-Hwp $hwp
}

if ($failed -gt 0) { exit 2 }
exit 0
