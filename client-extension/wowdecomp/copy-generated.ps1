# Copies the generated files the patch series includes into the wowdecomp checkout at -Tree, under Torment/ at
# its root (the include root of every wowdecomp target): today the class power table,
# mod-diablocraft/data/generated/class_power_tokens.h, which mod-diablocraft's class resources generator writes.
# The file stays in the Torment repo; a build that lacks it stops here.
param(
    [Parameter(Mandatory)] [string] $Tree,
    [Parameter(Mandatory)] [string] $Repo
)

$ErrorActionPreference = 'Stop'

$files = @('mod-diablocraft/data/generated/class_power_tokens.h')
$dest = Join-Path $Tree 'Torment'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
foreach ($file in $files) {
    $src = Join-Path $Repo $file
    if (-not (Test-Path $src)) { throw "$file is not in $Repo" }
    Copy-Item $src -Destination (Join-Path $dest (Split-Path $file -Leaf))
    Write-Host "copied $file to $dest"
}
