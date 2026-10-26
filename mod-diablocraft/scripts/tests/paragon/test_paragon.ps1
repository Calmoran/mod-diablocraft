param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
function Invoke-ParagonCheck([string]$Executable, [string[]]$Arguments) {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.WorkingDirectory = $repo
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    # MSBuild fails if the host exports both Path and PATH. Match build.ps1.
    $normalized = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in [Environment]::GetEnvironmentVariables().GetEnumerator()) {
        if ($normalized.ContainsKey([string]$entry.Key) -and [string]$entry.Key -ieq 'PATH') {
            $normalized[[string]$entry.Key] = (($normalized[[string]$entry.Key]+';'+[string]$entry.Value).Split(';') | Select-Object -Unique) -join ';'
        } else { $normalized[[string]$entry.Key] = [string]$entry.Value }
    }
    $info.Environment.Clear()
    foreach ($entry in $normalized.GetEnumerator()) { $info.Environment[$entry.Key] = $entry.Value }
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout.GetAwaiter().GetResult()
    $stderr.GetAwaiter().GetResult()
    if ($process.ExitCode) { throw "Paragon check failed: $Executable ($($process.ExitCode))" }
}
$cmake = (Get-Command cmake).Source
$ctest = Join-Path (Split-Path $cmake) 'ctest.exe'
$testBuild = 'mod-diablocraft/build/paragon-tests-clean'
$configure = @('-G','Visual Studio 17 2022','-A','x64','-S','mod-diablocraft/scripts/tests/paragon','-B',$testBuild)
$instance = 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools'
if (Test-Path -LiteralPath $instance) { $configure += "-DCMAKE_GENERATOR_INSTANCE=$instance" }
Invoke-ParagonCheck $cmake $configure
Invoke-ParagonCheck $cmake @('--build',$testBuild,'--config','Release','--','-m:1')
Invoke-ParagonCheck $ctest @('--test-dir',$testBuild,'-C','Release','--output-on-failure','--no-tests=error')
Invoke-ParagonCheck $Python @('-m','unittest','discover','-s','mod-diablocraft/scripts','-p','test_generate_sql.py')
Invoke-ParagonCheck $Python @('mod-diablocraft/scripts/tests/paragon/test_paragon_data.py')
Invoke-ParagonCheck (Join-Path $repo 'azerothcore-wotlk/build/server/lua52_interpreter.exe') @('mod-diablocraft/scripts/tests/paragon/test_paragon.lua')
