<#
.SYNOPSIS
    Compare GetTextFile and InitScan/GetText on tracked-change HWPX documents.

.DESCRIPTION
    S-063 P0 measure-first probe. It records only extracted-text lengths and
    SHA-256 digests, never document text. Two InitScan masks and two COM call
    shapes are measured independently because tracked-change text returned empty
    through GetTextFile("TEXT", "") on the previous Hancom build.
#>
param(
    [Parameter(Mandatory = $true)][string[]] $Path,
    [Parameter(Mandatory = $true)][string] $OutJsonl,
    [int] $MaxIterations = 100000
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Get-StringSha256 {
    param([string] $Value)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        return (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join "")
    } finally { $sha.Dispose() }
}

function Get-FileSha256 {
    param([string] $Value)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Value).Hash.ToLowerInvariant()
}

function Write-JsonLine {
    param([string] $Output, [object] $Record)
    Add-Content -LiteralPath $Output -Value ($Record | ConvertTo-Json -Depth 8 -Compress) -Encoding UTF8
}

function New-Hwp {
    $obj = New-Object -ComObject "HWPFrame.HwpObject"
    try { $null = $obj.RegisterModule("FilePathCheckerModule", "FilePathCheckerModuleExample") } catch {}
    try { $null = $obj.SetMessageBoxMode(0x00020000) } catch {}
    return $obj
}

function Invoke-GetTextFileProbe {
    param([object] $Hwp, [string] $Format, [string] $Option)
    try {
        $text = [string]$Hwp.GetTextFile($Format, $Option)
        return [ordered]@{
            method = "GetTextFile"
            format = $Format
            option = $Option
            ok = $true
            textLength = $text.Length
            textSha256 = Get-StringSha256 $text
            terminalCode = $null
            iterations = 1
            error = $null
        }
    } catch {
        return [ordered]@{
            method = "GetTextFile"
            format = $Format
            option = $Option
            ok = $false
            textLength = 0
            textSha256 = Get-StringSha256 ""
            terminalCode = $null
            iterations = 0
            error = $_.Exception.Message
        }
    }
}

function Invoke-ScanProbe {
    param(
        [object] $Hwp,
        [int] $Option,
        [string] $Label,
        [string] $CallShape,
        [int] $IterationLimit
    )
    $text = New-Object System.Text.StringBuilder
    $terminal = $null
    $errorMessage = $null
    $iterations = 0
    $initialized = $false
    try {
        $initialized = [bool]$Hwp.InitScan($Option, 0x0007, 0, 0, -1, -1)
        if (-not $initialized) { throw "InitScan returned false" }
        while ($iterations -lt $IterationLimit) {
            $iterations += 1
            $chunk = ""
            if ($CallShape -eq "byref") {
                $code = [int]$Hwp.GetText([ref]$chunk)
            } else {
                $raw = $Hwp.GetText()
                if ($raw.PSObject.Properties.Name -contains "result") {
                    $code = [int]$raw.result
                    $chunk = [string]$raw.text
                } elseif ($raw -is [System.Array] -and $raw.Length -ge 2) {
                    $code = [int]$raw[0]
                    $chunk = [string]$raw[1]
                } else {
                    throw "unsupported no-argument GetText return shape"
                }
            }
            if ($chunk) { $null = $text.Append($chunk) }
            if ($code -eq 0 -or $code -eq 1 -or $code -gt 100) {
                $terminal = $code
                break
            }
        }
        if ($iterations -ge $IterationLimit -and $null -eq $terminal) {
            throw "GetText iteration limit reached"
        }
    } catch {
        $errorMessage = $_.Exception.Message
    } finally {
        try { $Hwp.ReleaseScan() | Out-Null } catch {}
    }
    $value = $text.ToString()
    return [ordered]@{
        method = "InitScan/GetText"
        label = $Label
        option = $Option
        range = 0x0007
        callShape = $CallShape
        initialized = $initialized
        ok = ($null -eq $errorMessage -and $terminal -le 100)
        textLength = $value.Length
        textSha256 = Get-StringSha256 $value
        terminalCode = $terminal
        iterations = $iterations
        error = $errorMessage
    }
}

$hwp = $null
try {
    $hwp = New-Hwp
    $version = $null
    try { $version = [string]$hwp.Version } catch {}
    if (Test-Path -LiteralPath $OutJsonl) { Remove-Item -LiteralPath $OutJsonl -Force }
    Write-JsonLine $OutJsonl ([ordered]@{
        _meta = "m9-p0-redline-text-v1"
        generatedAt = [DateTime]::UtcNow.ToString("o")
        computerName = $env:COMPUTERNAME
        hancomBuild = $version
        powershell = $PSVersionTable.PSVersion.ToString()
        documentCount = $Path.Count
        privacy = "length-and-sha256-only"
    })

    foreach ($candidate in $Path) {
        $resolved = (Resolve-Path -LiteralPath $candidate).ProviderPath
        $opened = $false
        $errorMessage = $null
        $probes = New-Object System.Collections.Generic.List[object]
        try {
            $opened = [bool]$hwp.Open($resolved, "", "")
            if ($opened) {
                $probes.Add((Invoke-GetTextFileProbe $hwp "TEXT" ""))
                $probes.Add((Invoke-GetTextFileProbe $hwp "TEXT" "saveblock"))
                $probes.Add((Invoke-ScanProbe $hwp 0x00 "normal" "byref" $MaxIterations))
                $probes.Add((Invoke-ScanProbe $hwp 0x07 "all-masks" "byref" $MaxIterations))
                $probes.Add((Invoke-ScanProbe $hwp 0x00 "normal" "noarg" $MaxIterations))
                $probes.Add((Invoke-ScanProbe $hwp 0x07 "all-masks" "noarg" $MaxIterations))
            }
        } catch {
            $errorMessage = $_.Exception.Message
        } finally {
            try { $hwp.Clear(1) | Out-Null } catch {}
        }
        Write-JsonLine $OutJsonl ([ordered]@{
            sourceId = [System.IO.Path]::GetFileName($resolved)
            sourceSha256 = Get-FileSha256 $resolved
            opened = $opened
            probes = $probes
            error = $errorMessage
            measuredAt = [DateTime]::UtcNow.ToString("o")
        })
    }
} finally {
    if ($null -ne $hwp) {
        try { $hwp.Quit() | Out-Null } catch {}
        try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) | Out-Null } catch {}
    }
}
