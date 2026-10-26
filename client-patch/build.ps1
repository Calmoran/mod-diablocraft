<#
.SYNOPSIS
Builds patch-4.MPQ from client-patch/dbc and client-patch/art, and optionally
installs it into the client.

The Linux build is client-patch/build.sh, and -Install does not apply there
because the client is on the designer's PC; see the Client patch bullet in AGENTS.md.

.DESCRIPTION
The 3.3.5a client only reads DBCs and art out of its MPQ chain, so anything we
change client-side has to be packaged. patch.MPQ, patch-2.MPQ and patch-3.MPQ are
Blizzard's, which makes 4 the next free slot; the client loads higher-numbered
patches last, so ours wins.

Packaging is done with Ladik's MPQ Editor, which has a command-line mode. It is
not in the repo - download it and either put MPQEditor.exe in client-patch/tools
or pass -MpqEditor.

Regenerate the DBCs before running this:

    python mod-diablocraft/scripts/generate/classes/generate_spells.py     # Spell.dbc
    python client-patch/dbc/build_currencytypes.py        # CurrencyTypes.dbc
    python client-patch/dbc/build_item.py --mysql ... --defaults-file ...   # Item.dbc

.EXAMPLE
.\client-patch\build.ps1 -Install
#>
[CmdletBinding()]
param(
    [string]$MpqEditor,
    [string]$Output,
    [string]$ClientData,
    [switch]$Install
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 can evaluate parameter defaults before PSScriptRoot
# is populated. Resolve these in the script body, where the script path exists.
if (-not $MpqEditor) { $MpqEditor = Join-Path $PSScriptRoot 'tools/MPQEditor.exe' }
if (-not $Output) { $Output = Join-Path $PSScriptRoot 'patch-4.MPQ' }
if (-not $ClientData) { $ClientData = Join-Path $PSScriptRoot '../WoW Client/Data' }

if (-not (Test-Path -LiteralPath $MpqEditor)) {
    throw "MPQ Editor not found at '$MpqEditor'. Download Ladik's MPQ Editor and put MPQEditor.exe there, or pass -MpqEditor."
}

$dbcDir = Join-Path $PSScriptRoot 'dbc'
$artDir = Join-Path $PSScriptRoot 'art'
$files = @()
foreach ($dbc in Get-ChildItem -LiteralPath $dbcDir -Filter *.dbc -File -ErrorAction SilentlyContinue) {
    $files += [pscustomobject]@{ Source = $dbc.FullName; Target = "DBFilesClient\$($dbc.Name)" }
}
foreach ($art in Get-ChildItem -LiteralPath $artDir -File -Recurse -ErrorAction SilentlyContinue |
         Where-Object { -not $_.Name.StartsWith('.') }) {
    $relative = $art.FullName.Substring($artDir.Length).TrimStart('\', '/')
    $files += [pscustomobject]@{ Source = $art.FullName; Target = $relative.Replace('/', '\') }
}
if ($files.Count -eq 0) { throw "Nothing to package: no .dbc in $dbcDir and no files in $artDir." }

# Rebuild from scratch every time; an MPQ that still holds a stale DBC is worse
# than no patch at all, because the client silently prefers it.
if (Test-Path -LiteralPath $Output) { Remove-Item -LiteralPath $Output -Force }

# MPQ Editor sizes the hash table from the file count and rounds to a power of
# two, so give it room rather than the exact number.
$capacity = [Math]::Max(16, [Math]::Pow(2, [Math]::Ceiling([Math]::Log($files.Count + 8, 2))))
& $MpqEditor new $Output $capacity | Out-Null
if (-not (Test-Path -LiteralPath $Output)) { throw "MPQ Editor did not create $Output." }

foreach ($file in $files) {
    Write-Host ("  + {0,-40} {1,10:N0} bytes" -f $file.Target, (Get-Item -LiteralPath $file.Source).Length)
    & $MpqEditor add $Output $file.Source $file.Target | Out-Null
}

# Verify by reading the archive back; the CLI is quiet on failure, so a silent
# run is not evidence that anything was stored.
$verifyDir = Join-Path ([IO.Path]::GetTempPath()) ("mpqverify_" + [Guid]::NewGuid().ToString('N'))
& $MpqEditor extract $Output "(listfile)" $verifyDir | Out-Null
$listfile = Join-Path $verifyDir '(listfile)'
if (-not (Test-Path -LiteralPath $listfile)) { throw "Could not read the listfile back from $Output." }
$stored = Get-Content -LiteralPath $listfile | Where-Object { $_ -and $_ -notmatch '^\(' }
$resolvedVerify = (Resolve-Path -LiteralPath $verifyDir).Path
$resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
if (-not $resolvedVerify.StartsWith($resolvedTemp,[StringComparison]::OrdinalIgnoreCase) -or
    (Split-Path $resolvedVerify -Leaf) -notmatch '^mpqverify_[0-9a-f]{32}$' -or
    (Get-Item -LiteralPath $resolvedVerify).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) {
    throw "Refusing cleanup outside the temporary MPQ verification directory: $resolvedVerify"
}
Remove-Item -LiteralPath $verifyDir -Recurse -Force -ErrorAction SilentlyContinue
foreach ($file in $files) {
    if ($stored -notcontains $file.Target) { throw "$($file.Target) is missing from the built archive." }
}

$size = (Get-Item -LiteralPath $Output).Length
Write-Host ("built {0} ({1:N1} MB, {2} file(s))" -f (Split-Path $Output -Leaf), ($size / 1MB), $stored.Count)

if ($Install) {
    if (-not (Test-Path -LiteralPath $ClientData)) { throw "Client Data folder not found at '$ClientData'." }
    Copy-Item -LiteralPath $Output -Destination (Join-Path $ClientData (Split-Path $Output -Leaf)) -Force
    Write-Host "installed to $ClientData"
    Write-Host "Bump client_patch in VERSION whenever this archive changes (00 section 7)."
}
