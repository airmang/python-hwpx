<#
.SYNOPSIS
    Render .hwpx files to PDF via the Hancom (한글) COM automation object.

.DESCRIPTION
    The COM backend for hwpx.visual.RenderOracle. Reads a JSON job list
    ([{ "src": "...", "pdf": "..." }, ...]) so many file paths (incl. Korean
    names) survive without argument-quoting issues, opens each through
    HWPFrame.HwpObject, exports to PDF, and writes a JSON result array.

    Hancom Office 2022 (v12) exposes Open with a fixed (filename, format, arg)
    signature -- the 1-arg form fails to bind, so pass ("", "") for auto-detect.
    SaveAs(path, "PDF", "") works as-is.

.PARAMETER Jobs
    Path to the JSON job-list file (UTF-8).

.PARAMETER ResultPath
    Optional path to write the JSON result array to; otherwise written to stdout.
#>
param(
    [Parameter(Mandatory = $true)][string] $Jobs,
    [string] $ResultPath = ""
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$jobList = Get-Content -LiteralPath $Jobs -Raw -Encoding UTF8 | ConvertFrom-Json
$results = New-Object System.Collections.Generic.List[object]
$hwp = $null
try {
    $hwp = New-Object -ComObject "HWPFrame.HwpObject"
    try { $null = $hwp.RegisterModule("FilePathCheckerModule", "FilePathCheckerModuleExample") } catch {}
    # Auto-dismiss modal dialogs so automation never blocks.
    try { $null = $hwp.SetMessageBoxMode(0x00020000) } catch {}

    foreach ($job in $jobList) {
        $src = [string]$job.src
        $pdf = [string]$job.pdf
        $opened = $false; $saved = $false; $err = $null
        try {
            $opened = [bool]$hwp.Open($src, "", "")
            if ($opened) {
                $saved = [bool]$hwp.SaveAs($pdf, "PDF", "")
            }
        } catch {
            $err = $_.Exception.Message
        } finally {
            try { $hwp.Clear(1) | Out-Null } catch {}
        }
        $results.Add([ordered]@{
            src    = $src
            pdf    = $pdf
            opened = $opened
            saved  = $saved
            error  = $err
        })
    }
} finally {
    if ($null -ne $hwp) {
        try { $hwp.Quit() | Out-Null } catch {}
        try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) | Out-Null } catch {}
    }
}

$json = $results | ConvertTo-Json -Depth 5
if ($ResultPath) {
    Set-Content -LiteralPath $ResultPath -Value $json -Encoding UTF8
} else {
    $json
}
