<#
.SYNOPSIS
    Measure the real-Hancom (한글) OPEN rate of a set of .hwpx files via COM.

.DESCRIPTION
    The hardened open-only oracle primitive for the M9 open-rate apparatus
    (specs/007-open-rate). Cloned from scripts/hancom_com_open_verify.ps1 and
    hardened per FR-002:

      (a) SetMessageBoxMode(0x00020000) so corrupt-file / repair / save modals
          do NOT block a babysat batch.
      (b) Per-file checkpoint: each verdict record is APPENDED to --OutJsonl
          IMMEDIATELY after Open(), so a mid-batch crash loses at most one file.
      (c) RESUME (FR-002, this build): a re-run does NOT truncate the JSONL. On
          startup it reads the existing checkpoint and SKIPS every file with a
          FINAL verdict (a clean load, a clean refusal, or a completed retry). A
          not-yet-retried COM-EXCEPTION error is NOT final and is re-attempted, so a
          run killed mid-retry never freezes a clean file as a permanent failure.
          After a hang/kill the owner re-runs; already-cleared clean popups are not
          shown twice. To force a clean re-measure, delete --OutJsonl first.
      (d) A single retry pass over files that errored on THIS run's pass 1; the
          retried record (retried=$true) is appended and wins the basename join, so
          the aggregator treats a retry-only open as NON-clean (never inflates the
          opens-clean headline).
      (e) Text-scan watchdog: the GetPageText loop (the free "parsed" tier signal)
          is bounded by -OpenTimeoutSec so a pathological page scan cannot stall the
          batch.

    The script reuses ONE COM session for the common path (Hancom startup
    dominates) but re-creates the session after any COM exception.

    Open uses the fixed Hancom 2022 (v12) 3-arg signature Open(path,"","")
    (auto-detect format), matching src/hwpx/visual/_render_hwpx.ps1.

    *** LIMIT — a HUNG Open() ***
    Open() is a synchronous STA COM call; it CANNOT be interrupted in-process
    without killing the Hangul process (which would also kill an unrelated Hangul
    the owner may have open). This script does NOT auto-kill on an Open() hang.
    Mitigation relies on RESUME (c): if an Open() hangs, the babysitter kills the
    run (Ctrl-C / close Hangul), re-runs, and RESUME skips every already-judged
    file. A file that hangs Open() *persistently* is moved aside by the operator
    (it stays unjudged → the aggregator reports it as unverified, coverage-visible).
    An automatic per-file process-kill watchdog is deferred to the TARGET (unattended
    CI) build and must be validated on the box before it is trusted.

    *** BOX-VERIFICATION REQUIRED (FR-002, opens-clean tier) ***
    SetMessageBoxMode(0x00020000) suppresses the modal, but the SUPPRESSED DEFAULT
    ACTION must NOT be silent auto-repair. If Hancom's default answer to the
    "손상된 파일을 복구하시겠습니까?" dialog is "복구"(repair), a corrupt input would be
    auto-repaired and Open() would return $true — miscounting a broken file as
    opens-clean. This is a Windows/Hancom-build behaviour that CANNOT be checked on
    a Mac. The negative controls (FR-005) are the real check: the must_refuse
    ``synthetic_corrupt_section`` canary is a structurally valid package whose body
    is garbage — if it reports opened=$true, the default action is auto-repair and
    the harness is INVALID (corpus_open_rate.py fails closed). Open the negatives
    FIRST (spike gate) so a leak surfaces before the full sitting.

    Per-file signal: after a successful Open() the script records ``isModifiedProbe``
    (Hwp.IsModified). This is a BOX-UNVERIFIED auto-repair hint — a clean load
    should read $false. It is recorded for audit only; it is NOT mapped to the
    aggregator's ``repaired`` (non-clean) field until the box run confirms it reads
    $false for known-clean files (measure-first: an unverified property must never
    silently collapse the headline).

    Windows-only PowerShell (5.1-compatible). Syntactically validated off-box; the
    real run happens on the .161 box.

.PARAMETER Path
    One or more .hwpx file paths to open-check.

.PARAMETER MaxPages
    Max pages to scan with GetPageText for the free "parsed" (textLength>0) signal.

.PARAMETER OutJsonl
    Per-file checkpoint JSONL. One JSON object per line is APPENDED after each
    Open(); a re-run resumes from it (skips already-judged files). Strongly
    recommended for real (babysat) batches.

.PARAMETER OutJson
    Optional path to write the final consolidated JSON array (prior + this run).

.PARAMETER OpenTimeoutSec
    Bounds the per-file GetPageText scan loop (seconds). Does NOT bound a hung
    Open() (see the LIMIT note above). Default 120.

.PARAMETER ProbeRepairMode
    When set (and starting fresh), records the queried SetMessageBoxMode value in a
    leading {"_meta":...} JSONL record for the receipt.
#>
param(
    [Parameter(Mandatory = $true)]
    [string[]] $Path,

    [int] $MaxPages = 20,

    [string] $OutJsonl = "",

    [string] $OutJson = "",

    [int] $OpenTimeoutSec = 120,

    [switch] $ProbeRepairMode
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# 0x00020000 = HWP_MESSAGE_BOX_MODE: auto-answer message boxes (suppress modals).
$MESSAGE_BOX_MODE = 0x00020000

function Resolve-InputPath {
    param([string] $InputPath)
    $resolved = Resolve-Path -LiteralPath $InputPath
    return $resolved.ProviderPath
}

function Copy-ToTrustedTemp {
    param([string] $InputPath)
    $name = [System.IO.Path]::GetFileName($InputPath)
    $dir = Join-Path $env:TEMP ("hwpx-open-rate-" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $target = Join-Path $dir $name
    Copy-Item -LiteralPath $InputPath -Destination $target -Force
    return @{ Directory = $dir; Path = $target }
}

function New-HwpObject {
    $hwp = New-Object -ComObject "HWPFrame.HwpObject"
    try {
        $null = $hwp.RegisterModule("FilePathCheckerModule", "FilePathCheckerModuleExample")
    } catch {
        Write-Warning ("RegisterModule FilePathCheckerModule failed: " + $_.Exception.Message)
    }
    # FR-002a: suppress modal dialogs. The negative controls (FR-005) prove the
    # suppressed default action is NOT silent auto-repair.
    try { $null = $hwp.SetMessageBoxMode($MESSAGE_BOX_MODE) } catch {
        Write-Warning ("SetMessageBoxMode failed: " + $_.Exception.Message)
    }
    return $hwp
}

function Close-HwpObject {
    param([object] $Hwp)
    if ($null -ne $Hwp) {
        try { $Hwp.Quit() | Out-Null } catch {}
        try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Hwp) | Out-Null } catch {}
    }
}

function Read-HwpText {
    param(
        [object] $Hwp,
        [int] $PageLimit,
        [int] $TimeoutSec
    )
    # Primary: GetTextFile("TEXT","") — the canonical whole-document text extractor.
    # Box finding 2026-07-01: GetPageText(n) returned 0 chars for ALL real produced
    # docs on the .161 Hancom build (it depends on page-render state), which would
    # collapse the parsed headline to 0%. GetTextFile does not depend on rendering.
    try {
        $whole = $Hwp.GetTextFile("TEXT", "")
        if ($null -ne $whole -and -not [string]::IsNullOrWhiteSpace([string]$whole)) {
            return [string]$whole
        }
    } catch {}
    # Fallback: per-page scan (older builds where GetTextFile is unavailable).
    $parts = New-Object System.Collections.Generic.List[string]
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    for ($page = 1; $page -le $PageLimit; $page++) {
        # (e) text-scan watchdog: stop scanning if the page loop overruns.
        if ($TimeoutSec -gt 0 -and $sw.Elapsed.TotalSeconds -gt $TimeoutSec) { break }
        try {
            $text = $Hwp.GetPageText($page)
        } catch {
            break
        }
        if ($null -eq $text -or [string]::IsNullOrWhiteSpace([string]$text)) {
            continue
        }
        $parts.Add([string]$text)
    }
    return ($parts -join "`n")
}

# Append one record as a single JSON line to the checkpoint file (FR-002b).
function Write-Checkpoint {
    param(
        [string] $JsonlPath,
        [object] $Record
    )
    if (-not $JsonlPath) { return }
    $line = ($Record | ConvertTo-Json -Depth 4 -Compress)
    Add-Content -LiteralPath $JsonlPath -Value $line -Encoding UTF8
}

# RESUME (FR-002c): basenames with a FINAL verdict in an existing checkpoint.
# FINAL = a clean load OR a clean refusal (error is null, opened true or false),
# OR a record from the single retry pass (retried=true). A COM-EXCEPTION error
# (error != null) with retried=false is NOT final — it is a to-be-retried state,
# so a resume RE-ATTEMPTS it. (Without this, a run killed mid-pass-2 would freeze a
# pass-1 exception as a permanent open_failure and silently DEFLATE the headline —
# a wrongly-low number is exactly as damaging as a wrongly-high one.) _meta probe
# lines have no sourcePath and are skipped.
function Get-JudgedBasenames {
    param([string] $JsonlPath)
    $set = @{}
    if (-not $JsonlPath -or -not (Test-Path -LiteralPath $JsonlPath)) { return $set }
    foreach ($line in (Get-Content -LiteralPath $JsonlPath -Encoding UTF8)) {
        $line = $line.Trim()
        if (-not $line) { continue }
        try { $rec = $line | ConvertFrom-Json } catch { continue }
        if ($rec.PSObject.Properties.Name -contains '_meta') { continue }
        if (-not $rec.sourcePath) { continue }
        $hasError = ($null -ne $rec.error) -and ([string]$rec.error -ne "")
        $retried = [bool]$rec.retried
        if ($hasError -and -not $retried) { continue }   # unretried exception -> re-attempt on resume
        $set[[System.IO.Path]::GetFileName([string]$rec.sourcePath)] = $true
    }
    return $set
}

# Prior verdicts (for the consolidated OutJson array).
function Read-ExistingRecords {
    param([string] $JsonlPath)
    $list = New-Object System.Collections.Generic.List[object]
    if (-not $JsonlPath -or -not (Test-Path -LiteralPath $JsonlPath)) { return $list }
    foreach ($line in (Get-Content -LiteralPath $JsonlPath -Encoding UTF8)) {
        $line = $line.Trim()
        if (-not $line) { continue }
        try { $rec = $line | ConvertFrom-Json } catch { continue }
        if ($rec.PSObject.Properties.Name -contains '_meta') { continue }
        $list.Add($rec)
    }
    return $list
}

# Open one file and return the verdict record. A COM exception is the watchdog
# trip: the caller re-creates the HwpObject when $record.error is non-null.
function Invoke-OpenCheck {
    param(
        [object] $Hwp,
        [string] $InputPath,
        [int] $PageLimit,
        [int] $TimeoutSec,
        [bool] $Retried
    )
    $trusted = Copy-ToTrustedTemp $InputPath
    $opened = $false
    $text = ""
    $errorMessage = $null
    $isModifiedProbe = $null
    $pageCount = $null
    try {
        # Hancom 2022 (v12): Open(path, format, arg); ("","") = auto-detect.
        # NOTE (box finding 2026-07-01): Open() returns $true even for container-
        # garbage (not-a-zip/empty/truncated), loading a BLANK doc with textLength=0.
        # So 'opened' alone is NOT the headline — the aggregator uses PARSED
        # (opened AND textLength>0). pageCount is a second "content really loaded"
        # probe captured here so the headline bar can be set from real data.
        $opened = [bool]$Hwp.Open($trusted.Path, "", "")
        if ($opened) {
            # BOX-UNVERIFIED auto-repair hint (recorded for audit; not headline).
            try { $isModifiedProbe = [bool]$Hwp.IsModified } catch { $isModifiedProbe = $null }
            try { $pageCount = [int]$Hwp.PageCount } catch { $pageCount = $null }
            $text = Read-HwpText -Hwp $Hwp -PageLimit $PageLimit -TimeoutSec $TimeoutSec
        }
    } catch {
        $errorMessage = $_.Exception.Message
    } finally {
        try { $Hwp.Clear(1) | Out-Null } catch {}
        Remove-Item -LiteralPath $trusted.Directory -Recurse -Force -ErrorAction SilentlyContinue
    }
    return [ordered]@{
        sourcePath = $InputPath
        opened     = $opened
        textLength = $text.Length
        pageCount  = $pageCount
        textPreview = if ($text.Length -gt 500) { $text.Substring(0, 500) } else { $text }
        error      = $errorMessage
        retried    = $Retried
        isModifiedProbe = $isModifiedProbe
    }
}

# RESUME: load prior verdicts + the already-judged basename set. Do NOT truncate.
$judged = Get-JudgedBasenames $OutJsonl
$records = New-Object System.Collections.Generic.List[object]
foreach ($r in (Read-ExistingRecords $OutJsonl)) { $records.Add($r) }
$resuming = ($judged.Count -gt 0)
if ($resuming) {
    Write-Host ("RESUME: " + $judged.Count + " file(s) already judged in " + $OutJsonl + " — skipping those.")
}

if ($ProbeRepairMode -and -not $resuming) {
    # Record the queried message-box mode for the receipt (fresh run only).
    $probeHwp = $null
    $modeValue = $null
    $modeError = $null
    try {
        $probeHwp = New-Object -ComObject "HWPFrame.HwpObject"
        try { $modeValue = $probeHwp.SetMessageBoxMode($MESSAGE_BOX_MODE) } catch { $modeError = $_.Exception.Message }
    } catch {
        $modeError = $_.Exception.Message
    } finally {
        Close-HwpObject $probeHwp
    }
    Write-Checkpoint -JsonlPath $OutJsonl -Record ([ordered]@{
        _meta = "repair-mode-probe"
        requestedMode = $MESSAGE_BOX_MODE
        previousModeReturned = $modeValue
        error = $modeError
        note = "Box must confirm suppressed default action is NOT auto-repair; the must_refuse negative controls (FR-005) are the real check."
    })
}

# Pass 1: open every not-yet-judged file, checkpoint immediately, re-create the
# session after any COM exception.
$thisRunErrorPaths = New-Object System.Collections.Generic.List[string]
$hwp = $null
try {
    $hwp = New-HwpObject
    foreach ($item in $Path) {
        $inputPath = Resolve-InputPath $item
        $base = [System.IO.Path]::GetFileName($inputPath)
        if ($judged.ContainsKey($base)) {
            Write-Host ("skip (already judged): " + $base)
            continue
        }
        $record = Invoke-OpenCheck -Hwp $hwp -InputPath $inputPath -PageLimit $MaxPages -TimeoutSec $OpenTimeoutSec -Retried $false
        Write-Checkpoint -JsonlPath $OutJsonl -Record $record
        $records.Add($record)
        $judged[$base] = $true
        if ($null -ne $record.error) {
            $thisRunErrorPaths.Add($inputPath)
            # Watchdog: a COM error may have poisoned the session — re-create it.
            Close-HwpObject $hwp
            $hwp = New-HwpObject
        }
    }
} finally {
    Close-HwpObject $hwp
    $hwp = $null
}

# Pass 2 (FR-002d): single retry over files that errored on THIS run's pass 1. A
# prior-run *unretried* exception is not treated as final — RESUME re-attempts it
# in pass 1 above (see Get-JudgedBasenames), so it flows here again if it re-errors.
# The retried record is appended and wins the aggregator's last-line basename join.
if ($thisRunErrorPaths.Count -gt 0) {
    $hwp = $null
    try {
        $hwp = New-HwpObject
        foreach ($inputPath in $thisRunErrorPaths) {
            $record = Invoke-OpenCheck -Hwp $hwp -InputPath $inputPath -PageLimit $MaxPages -TimeoutSec $OpenTimeoutSec -Retried $true
            Write-Checkpoint -JsonlPath $OutJsonl -Record $record
            $records.Add($record)
            if ($null -ne $record.error) {
                Close-HwpObject $hwp
                $hwp = New-HwpObject
            }
        }
    } finally {
        Close-HwpObject $hwp
        $hwp = $null
    }
}

# Final consolidated array (prior + this run), mirroring the legacy shape.
$json = $records | ConvertTo-Json -Depth 4
if ($OutJson) {
    Set-Content -LiteralPath $OutJson -Value $json -Encoding UTF8
} else {
    $json
}
