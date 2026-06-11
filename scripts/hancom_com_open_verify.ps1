param(
    [Parameter(Mandatory = $true)]
    [string[]] $Path,

    [int] $MaxPages = 20,

    [string] $OutJson = ""
)

$ErrorActionPreference = "Stop"

function Resolve-InputPath {
    param([string] $InputPath)
    $resolved = Resolve-Path -LiteralPath $InputPath
    return $resolved.ProviderPath
}

function Copy-ToTrustedTemp {
    param([string] $InputPath)
    $name = [System.IO.Path]::GetFileName($InputPath)
    $dir = Join-Path $env:TEMP ("hwpx-com-open-" + [System.Guid]::NewGuid().ToString("N"))
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
    return $hwp
}

function Read-HwpText {
    param(
        [object] $Hwp,
        [int] $PageLimit
    )
    $parts = New-Object System.Collections.Generic.List[string]
    for ($page = 1; $page -le $PageLimit; $page++) {
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

$results = New-Object System.Collections.Generic.List[object]
$hwp = $null
try {
    $hwp = New-HwpObject
    foreach ($item in $Path) {
        $inputPath = Resolve-InputPath $item
        $trusted = Copy-ToTrustedTemp $inputPath
        $opened = $false
        $text = ""
        $errorMessage = $null
        try {
            $opened = [bool]$hwp.Open($trusted.Path)
            if ($opened) {
                $text = Read-HwpText -Hwp $hwp -PageLimit $MaxPages
            }
        } catch {
            $errorMessage = $_.Exception.Message
        } finally {
            try { $hwp.Clear(1) | Out-Null } catch {}
            Remove-Item -LiteralPath $trusted.Directory -Recurse -Force -ErrorAction SilentlyContinue
        }
        $results.Add([ordered]@{
            sourcePath = $inputPath
            opened = $opened
            textLength = $text.Length
            textPreview = if ($text.Length -gt 500) { $text.Substring(0, 500) } else { $text }
            error = $errorMessage
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
} else {
    $json
}
