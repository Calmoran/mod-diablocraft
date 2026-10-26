$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
function Invoke-TierCheck([string]$Executable, [string[]]$Arguments) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.WorkingDirectory = $repo
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    # MSBuild rejects the host's duplicate Path/PATH keys. EnvironmentVariables
    # is case-insensitive and also available in Windows PowerShell 5.1.
    $normalized = New-Object 'Collections.Generic.Dictionary[string,string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in [Environment]::GetEnvironmentVariables().GetEnumerator()) {
        $key = [string]$entry.Key
        if ($normalized.ContainsKey($key) -and $key -ieq 'PATH') {
            $normalized[$key] = (($normalized[$key]+';'+[string]$entry.Value).Split(';') | Select-Object -Unique) -join ';'
        } else { $normalized[$key] = [string]$entry.Value }
    }
    $info.EnvironmentVariables.Clear()
    foreach ($entry in $normalized.GetEnumerator()) { $info.EnvironmentVariables[$entry.Key] = $entry.Value }
    $info.Arguments = ($Arguments | ForEach-Object { '"' + $_.Replace('"','\"') + '"' }) -join ' '
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout.GetAwaiter().GetResult()
    $stderr.GetAwaiter().GetResult()
    if ($process.ExitCode) { throw "Tier login check failed ($($process.ExitCode))" }
}
$cmake = 'C:/Program Files/CMake/bin/cmake.exe'
Invoke-TierCheck $cmake @('--fresh','-S','mod-diablocraft/src/difficulty/tests','-B','build/tier-login-tests','-G','Visual Studio 17 2022','-A','x64')
Invoke-TierCheck $cmake @('--build','build/tier-login-tests','--config','Release','--','-m:1')
Invoke-TierCheck 'C:/Program Files/CMake/bin/ctest.exe' @('--test-dir','build/tier-login-tests','-C','Release','--output-on-failure','--no-tests=error')
