<#
.SYNOPSIS
    Render .hwpx files to PDF using the Hancom (한글) COM automation object.

.DESCRIPTION
    The lineseg-baseline harness uses Hancom itself as the visual oracle. This
    script opens each .hwpx through HWPFrame.HwpObject and exports it to PDF, so
    the ON/OFF pair can be rasterized and compared (see rasterize_score.py).

    This is the ONLY part of the harness that requires Windows + an installed
    Hangul (한글). Everything else runs anywhere python-hwpx imports.

    Extends the existing scripts/hancom_com_open_verify.ps1 pattern with a
    SaveAs-to-PDF step and dialog suppression.

.PARAMETER Path
    One or more .hwpx files (e.g. the ON/OFF outputs from run_pairs.py).

.PARAMETER OutDir
    Directory to write <stem>.pdf into.

.PARAMETER OutJson
    Optional path for a render-manifest JSON (source -> pdf, opened, saved).

.EXAMPLE
    ./hancom_render.ps1 -Path (Get-ChildItem C:\vc-pairs\*.hwpx) `
        -OutDir C:\vc-pdfs -OutJson C:\vc-pdfs\render-manifest.json
#>
param(
    [Parameter(Mandatory = $true)][string[]] $Path,
    [Parameter(Mandatory = $true)][string]   $OutDir,
    [string] $OutJson = ""
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function New-HwpObject {
    $hwp = New-Object -ComObject "HWPFrame.HwpObject"
    try {
        $null = $hwp.RegisterModule("FilePathCheckerModule", "FilePathCheckerModuleExample")
    } catch {
        Write-Warning ("RegisterModule failed: " + $_.Exception.Message)
    }
    # Auto-dismiss modal dialogs (e.g. the PDF save-options box) so the
    # automation never blocks. 0x00020000 answers message boxes with default.
    try { $null = $hwp.SetMessageBoxMode(0x00020000) } catch {}
    return $hwp
}

$results = New-Object System.Collections.Generic.List[object]
$hwp = $null
try {
    $hwp = New-HwpObject
    foreach ($item in $Path) {
        $src  = (Resolve-Path -LiteralPath $item).ProviderPath
        $name = [System.IO.Path]::GetFileNameWithoutExtension($src)
        $pdf  = Join-Path $OutDir ($name + ".pdf")
        $opened = $false; $saved = $false; $err = $null
        try {
            $opened = [bool]$hwp.Open($src)
            if ($opened) {
                # SaveAs with explicit "PDF" format. If a particular Hangul build
                # rejects this, switch to the HAction "FileSaveAsPdf" path — this
                # is the one build-specific line in the harness.
                $saved = [bool]$hwp.SaveAs($pdf, "PDF", "")
            }
        } catch {
            $err = $_.Exception.Message
        } finally {
            try { $hwp.Clear(1) | Out-Null } catch {}
        }
        $results.Add([ordered]@{
            sourcePath = $src
            pdfPath    = $pdf
            opened     = $opened
            saved      = $saved
            error      = $err
        })
    }
} finally {
    if ($null -ne $hwp) {
        try { $hwp.Quit() | Out-Null } catch {}
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) | Out-Null
    }
}

$json = $results | ConvertTo-Json -Depth 4
if ($OutJson) {
    Set-Content -LiteralPath $OutJson -Value $json -Encoding UTF8
    Write-Host ("render-manifest -> " + $OutJson)
} else {
    $json
}
