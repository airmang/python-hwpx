# Hancom COM Open Oracle

This workflow verifies that Windows Hancom Office can open generated HWPX files
without UI prompts and can extract page text.

## Requirements

- Windows with Hancom Office installed.
- PowerShell 5+.
- `HWPFrame.HwpObject` COM registration available to the current user.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts/hancom_com_open_verify.ps1 `
  -Path .\samples\one.hwpx, .\samples\two.hwpx `
  -OutJson .\hancom-open-results.json
```

The script copies every input into a unique `%TEMP%` directory before opening
it. In normal Hancom Office installations this avoids file-path security
prompts. It also attempts:

```powershell
RegisterModule("FilePathCheckerModule", "FilePathCheckerModuleExample")
```

If the module registration is unavailable, the script continues and reports the
open result. Each result includes `opened`, `textLength`, a short `textPreview`,
and any exception message.

## Evidence Policy

Use the JSON output as Stage evidence. Do not commit generated sample documents
or private document text. For public corpus samples, record URL, SHA-256, and
the script result path in a local manifest.

On non-Windows machines this Stage is satisfied by keeping the script and this
runbook in the repo. Execution evidence should be added later from a Windows
machine with Hancom Office.
