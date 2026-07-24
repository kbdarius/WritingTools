param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [Parameter(Mandatory = $true)]
    [string]$ExeName
)

$ErrorActionPreference = 'Stop'

$resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path.TrimEnd('\')
$newExePath = [IO.Path]::GetFullPath((Join-Path $resolvedRepoRoot $ExeName))
$newExeDirectory = [IO.Path]::GetDirectoryName($newExePath).TrimEnd('\')

if ($newExeDirectory -ne $resolvedRepoRoot) {
    throw "The new executable must be directly inside the WritingTools repository."
}
if ($ExeName -notlike 'Writing Tools v*.exe') {
    throw "Unexpected executable name: $ExeName"
}
if (-not (Test-Path -LiteralPath $newExePath -PathType Leaf)) {
    throw "The new executable was not found: $newExePath"
}

$oldExecutables = @(
    Get-ChildItem -LiteralPath $resolvedRepoRoot -Filter 'Writing Tools v*.exe' -File |
        Where-Object { $_.FullName -ne $newExePath }
)
$oldPaths = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
foreach ($oldExecutable in $oldExecutables) {
    [void]$oldPaths.Add($oldExecutable.FullName)
}

if ($oldPaths.Count -gt 0) {
    $oldProcesses = @(
        Get-CimInstance Win32_Process |
            Where-Object { $_.ExecutablePath -and $oldPaths.Contains($_.ExecutablePath) }
    )
    foreach ($oldProcess in $oldProcesses) {
        Write-Host "Stopping $($oldProcess.Name) (PID $($oldProcess.ProcessId))..."
        Stop-Process -Id $oldProcess.ProcessId -Force -ErrorAction Stop
    }

    if ($oldProcesses.Count -gt 0) {
        Start-Sleep -Milliseconds 750
    }

    foreach ($oldExecutable in $oldExecutables) {
        if ([IO.Path]::GetDirectoryName($oldExecutable.FullName).TrimEnd('\') -ne $resolvedRepoRoot) {
            throw "Refusing to delete an executable outside the repository: $($oldExecutable.FullName)"
        }
        Remove-Item -LiteralPath $oldExecutable.FullName -Force
        Write-Host "Deleted old executable: $($oldExecutable.Name)"
    }
}

Write-Host "Starting $ExeName..."
Start-Process -FilePath $newExePath -WorkingDirectory $resolvedRepoRoot -WindowStyle Hidden
Start-Sleep -Seconds 4

$newProcess = @(
    Get-CimInstance Win32_Process |
        Where-Object { $_.ExecutablePath -eq $newExePath }
)
if ($newProcess.Count -eq 0) {
    throw "The new Writing Tools executable did not remain running."
}

Write-Host "$ExeName is running."
