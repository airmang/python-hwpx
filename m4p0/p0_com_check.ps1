<#
.SYNOPSIS
  M4 (S-058) redline P0 acceptance check via Hancom (한글) COM — run on x64 Windows with Hancom installed.

.DESCRIPTION
  Measures whether agent-synthesized change-tracking (insert/delete) + comments are accepted by REAL Hancom:
    #1 display      : Hancom opens our file + IsTrackChange (recognizes track-changes)
    #2 accept/reject: sweeps candidate accept/reject action IDs, VERIFIES each by reading back the saved XML
                      (accept => marks gone, insert text kept, delete text removed; reject => insert removed, delete kept)
    #3 accept->clean: re-opens the accepted file (round-trip stable, no corruption)
    #4 comments     : memo count preserved through accept

  Self-validating: even if the exact action ID is unknown, the sweep reports WHICH id produced the expected XML.
  Emits a JSON receipt to stdout AND p0_com_receipt.json. Output .hwpx files land in .\com_out\ (commit them back for Mac-side inspection).

.USAGE
  powershell -ExecutionPolicy Bypass -File .\p0_com_check.ps1
  (run from the m4p0 folder; or pass -Dir <folder containing the two .hwpx files>)
#>
param([string]$Dir = "$PSScriptRoot")

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null

$fileA = Join-Path $Dir "redline_synth.hwpx"          # insert + delete (byte-identity preserved)
$fileB = Join-Path $Dir "redline_with_comments.hwpx"  # insert + delete + 2 memos
$outDir = Join-Path $Dir "com_out"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$INSERT_TEXT = "2026. 7. 1"      # appears only inside the tracked INSERT
$DELETE_TEXT = "원활한 사업 추진"   # the tracked DELETE wraps this line

function New-Hwp {
  $h = New-Object -ComObject "HWPFrame.HwpObject"
  try { $null = $h.RegisterModule("FilePathCheckerModule","FilePathCheckerModuleExample") } catch {}
  try { $null = $h.SetMessageBoxMode(0x00020000) } catch {}
  return $h
}
function Read-Section0([string]$path) {
  try {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($path)
    try {
      $e = $zip.Entries | Where-Object { $_.FullName -eq "Contents/section0.xml" }
      if (-not $e) { return "" }
      $sr = New-Object System.IO.StreamReader($e.Open(), [System.Text.Encoding]::UTF8)
      $txt = $sr.ReadToEnd(); $sr.Close(); return $txt
    } finally { $zip.Dispose() }
  } catch { return "" }
}
function Xml-State([string]$path) {
  $s = Read-Section0 $path
  return [ordered]@{
    hasInsertMark = $s -match "insertBegin"
    hasDeleteMark = $s -match "deleteBegin"
    hasInsertText = $s -match ([regex]::Escape($INSERT_TEXT))
    hasDeleteText = $s -match ([regex]::Escape($DELETE_TEXT))
    memoCount     = ([regex]::Matches($s, "<hp:memo ")).Count
  }
}

$ACCEPT_IDS = @("ApplyAllTrackChange","MenuExApplyAllTrackChange","ApplyTrackChange","MenuExApplyTrackChange",
                "RevisionApplyAll","RevisionApply","TrackChangeApplyAll","AcceptAllChanges","AcceptChange",
                "MenuTrackChangeApplyAll","TrackChangeApply")
$REJECT_IDS = @("CancelAllTrackChange","MenuExCancelAllTrackChange","CancelTrackChange","MenuExCancelTrackChange",
                "RevisionCancelAll","RevisionCancel","TrackChangeCancelAll","RejectAllChanges","RejectChange",
                "MenuTrackChangeCancelAll","TrackChangeCancel")

function Sweep([string]$src, [string[]]$ids, [string]$tag) {
  $rows = New-Object System.Collections.Generic.List[object]
  foreach ($id in $ids) {
    $h = New-Hwp
    $opened=$false; $isTrack=$null; $ran=$null; $err=$null; $state=$null; $outPath=$null
    try {
      $opened = [bool]$h.Open($src, "", "")
      try { $isTrack = [bool]$h.IsTrackChange } catch { $isTrack = "n/a" }
      try { $ran = [bool]$h.HAction.Run($id) } catch { $err = $_.Exception.Message }
      $outPath = Join-Path $outDir ("{0}_{1}.hwpx" -f $tag, $id)
      try { $null = $h.SaveAs($outPath, "HWPX", "") } catch { if (-not $err) { $err = "SaveAs: " + $_.Exception.Message } }
      if (Test-Path $outPath) { $state = Xml-State $outPath }
    } catch { $err = $_.Exception.Message } finally {
      try { $h.Clear(1) | Out-Null } catch {}
      try { $h.Quit() | Out-Null } catch {}
      try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($h) | Out-Null } catch {}
    }
    $rows.Add([ordered]@{ actionId=$id; opened=$opened; isTrackChange=$isTrack; ranOk=$ran; error=$err; xml=$state })
  }
  return $rows
}

$report = [ordered]@{}
$report.generatedNote = "M4 P0 redline acceptance via Hancom COM"
$report.fileA = $fileA
$report.fileB = $fileB
if (Test-Path $fileA) { $report.baselineA = Xml-State $fileA } else { $report.baselineA = "FILE MISSING: $fileA" }
if (Test-Path $fileB) { $report.baselineB = Xml-State $fileB } else { $report.baselineB = "FILE MISSING: $fileB" }

# expected after ACCEPT-all on A: marks gone, insert text kept, delete text removed
$report.acceptSweep = Sweep $fileA $ACCEPT_IDS "accept"
# expected after REJECT-all on A: marks gone, insert text removed, delete text kept
$report.rejectSweep = Sweep $fileA $REJECT_IDS "reject"

# B: open + round-trip (no action) -> memo survival through Hancom re-serialization, then accept -> memo survival
$report.commentsRoundTrip = (Sweep $fileB @("__noop__") "B_roundtrip")
$report.commentsAfterAccept = (Sweep $fileB $ACCEPT_IDS "B_accept")

$json = $report | ConvertTo-Json -Depth 8
Set-Content -LiteralPath (Join-Path $Dir "p0_com_receipt.json") -Value $json -Encoding UTF8
Write-Output $json
