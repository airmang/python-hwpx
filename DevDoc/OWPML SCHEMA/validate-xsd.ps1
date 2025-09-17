$ErrorActionPreference = 'Stop'
$folder = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $folder

# Collect candidate schema files (.xml/.xsd that actually contain an XMLSchema)
$files = Get-ChildItem -File -Path $folder | Where-Object { $_.Extension -in '.xml', '.xsd' }

function Test-IsSchemaFile([string]$path) {
    try {
        $head = Get-Content -LiteralPath $path -Raw -ErrorAction Stop
        return ($head -match 'http://www.w3.org/2001/XMLSchema' -and $head -match '<\s*([a-zA-Z0-9_]+:)?schema')
    } catch {
        return $false
    }
}

$anyFail = $false
foreach ($f in $files) {
    if (-not (Test-IsSchemaFile $f.FullName)) {
        Write-Host ("SKIP: {0}" -f $f.Name)
        continue
    }

    $events = New-Object System.Collections.Generic.List[System.Xml.Schema.ValidationEventArgs]
    $handler = [System.Xml.Schema.ValidationEventHandler]{ param($sender, $e) [void]$events.Add($e) }

    try {
        $set = New-Object System.Xml.Schema.XmlSchemaSet
        $set.XmlResolver = New-Object System.Xml.XmlUrlResolver
        $set.add_ValidationEventHandler($handler)
        # Read schema and add (uses schema's own targetNamespace)
        $readerSettings = New-Object System.Xml.XmlReaderSettings
        $readerSettings.DtdProcessing = [System.Xml.DtdProcessing]::Ignore
        $reader = [System.Xml.XmlReader]::Create($f.FullName, $readerSettings)
        try {
            $schema = [System.Xml.Schema.XmlSchema]::Read($reader, $handler)
        } finally {
            $reader.Close()
        }
        [void]$set.Add($schema)
        $set.Compile()
        if ($events.Count -eq 0) {
            Write-Host ("PASS: {0}" -f $f.Name)
        } else {
            $sev = ($events | ForEach-Object { $_.Severity } | Group-Object | ForEach-Object { "{0} {1}" -f $_.Count, $_.Name }) -join ', '
            Write-Host ("WARN: {0} - {1}" -f $f.Name, $sev)
            foreach ($ev in $events) { Write-Host ("  {0}: {1}" -f $ev.Severity, $ev.Message) }
        }
    } catch {
        $anyFail = $true
        Write-Host ("FAIL: {0} - {1}" -f $f.Name, $_.Exception.Message)
    }
}

if ($anyFail) { exit 1 } else { exit 0 }
