# Applies every *.patch in -Dir, in file-name order, to the wowdecomp checkout at -Tree.
# Each patch goes into the checkout's index first (git apply --cached), so it applies against the
# committed LF text whatever line endings the runner checked the files out with; the patched files are
# then written back out of the index. A patch that does not apply at the pin stops the build.
param(
    [Parameter(Mandatory)] [string] $Tree,
    [Parameter(Mandatory)] [string] $Dir
)

$ErrorActionPreference = 'Stop'

$patches = @(Get-ChildItem -Path $Dir -Filter *.patch -File -ErrorAction SilentlyContinue | Sort-Object Name)
foreach ($patch in $patches) {
    git -C $Tree apply --cached --check $patch.FullName
    if ($LASTEXITCODE -ne 0) { throw "$($patch.Name) does not apply to $Tree" }
    git -C $Tree apply --cached $patch.FullName
    if ($LASTEXITCODE -ne 0) { throw "applying $($patch.Name) failed" }
    Write-Host "applied $($patch.Name)"
}
if ($patches.Count -gt 0) {
    git -C $Tree checkout -- .
    if ($LASTEXITCODE -ne 0) { throw "writing the patched files out of the index failed" }
}
Write-Host "$($patches.Count) patch(es) from $Dir applied to $Tree"
