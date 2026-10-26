param([string]$Target = 'worldserver', [switch]$Configure)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$lockPath = Join-Path $repo 'build.lock'
$owner = [Guid]::NewGuid().ToString()
$acquired = $false
try {
    while (-not $acquired) {
        try {
            $stream = [IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
            try {
                $bytes = [Text.Encoding]::UTF8.GetBytes("owner=$owner`npid=$PID`ncreated=$([DateTime]::UtcNow.ToString('o'))`n")
                $stream.Write($bytes,0,$bytes.Length)
                $acquired = $true
            } finally { $stream.Dispose() }
        } catch [IO.IOException] {
            if (-not (Test-Path -LiteralPath $lockPath)) { throw }
            $age = [DateTime]::UtcNow - (Get-Item -LiteralPath $lockPath).LastWriteTimeUtc
            if ($age.TotalMinutes -ge 30) { throw "build.lock is over 30 minutes old. Inspect its owner before removing a stale lock." }
            Write-Output 'Another build owns build.lock; waiting 10 seconds.'
            Start-Sleep -Seconds 10
        }
    }
    function Invoke-BuildCMake([string[]]$Arguments) {
        $info = [Diagnostics.ProcessStartInfo]::new('C:\Program Files\CMake\bin\cmake.exe')
        $info.WorkingDirectory = $repo
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
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
        while (-not $process.WaitForExit(10000)) {
            [IO.File]::SetLastWriteTimeUtc($lockPath,[DateTime]::UtcNow)
        }
        $stdout.GetAwaiter().GetResult()
        $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode) { throw "CMake failed ($($process.ExitCode)); inspect the build log." }
    }
    if ($Configure) { Invoke-BuildCMake @('-S','azerothcore-wotlk','-B','azerothcore-wotlk/build') }
    $log = Join-Path $repo 'azerothcore-wotlk/build/difficulty-locked-build.log'
    # One MSBuild worker and one compiler. Concurrent builds exhausted memory.
    Invoke-BuildCMake @('--build','azerothcore-wotlk/build','--target',$Target,'--config','Release','--','-m:1','/p:CL_MPCount=1','/fl',"/flp:logfile=$log;verbosity=normal")
} finally {
    if ($acquired -and (Test-Path -LiteralPath $lockPath)) {
        if ([IO.File]::ReadAllText($lockPath).Contains("owner=$owner")) { Remove-Item -LiteralPath $lockPath }
    }
}
