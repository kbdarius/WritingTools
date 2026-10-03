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
    Write-Host "Removing old versioned Writing Tools executables..."
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

    $remainingOldProcesses = @(
        Get-CimInstance Win32_Process |
            Where-Object { $_.ExecutablePath -and $oldPaths.Contains($_.ExecutablePath) }
    )
    if ($remainingOldProcesses.Count -gt 0) {
        $remaining = ($remainingOldProcesses | ForEach-Object { "$($_.Name) (PID $($_.ProcessId))" }) -join ', '
        throw "Older Writing Tools processes are still running: $remaining"
    }

    $remainingOldExecutables = @(
        Get-ChildItem -LiteralPath $resolvedRepoRoot -Filter 'Writing Tools v*.exe' -File |
            Where-Object { $_.FullName -ne $newExePath }
    )
    if ($remainingOldExecutables.Count -gt 0) {
        $remaining = ($remainingOldExecutables | ForEach-Object { $_.Name }) -join ', '
        throw "Older Writing Tools executables still exist: $remaining"
    }
} else {
    Write-Host "No previous versioned Executable found to remove."
}

# Avoid duplicate instances when a previous manual launch used this same version.
$existingNewProcesses = @(
    Get-CimInstance Win32_Process |
        Where-Object { $_.ExecutablePath -eq $newExePath }
)
foreach ($existingNewProcess in $existingNewProcesses) {
    Write-Host "Stopping existing $($existingNewProcess.Name) (PID $($existingNewProcess.ProcessId)) before relaunch..."
    Stop-Process -Id $existingNewProcess.ProcessId -Force -ErrorAction Stop
}
if ($existingNewProcesses.Count -gt 0) {
    Start-Sleep -Milliseconds 750
}

Write-Host "Launching latest executable: $ExeName..."
Write-Host "Starting $ExeName..."
# This is an interactive desktop app. Hidden startup mode suppresses Qt's
# normal windows even when Settings calls show(), raise_(), and activateWindow().
Start-Process -FilePath $newExePath -WorkingDirectory $resolvedRepoRoot -WindowStyle Normal
Start-Sleep -Seconds 4

$newProcess = @(
    Get-CimInstance Win32_Process |
        Where-Object { $_.ExecutablePath -eq $newExePath }
)
if ($newProcess.Count -eq 0) {
    throw "The new Writing Tools executable did not remain running."
}

$unexpectedOldProcesses = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ExecutablePath -and
            $_.ExecutablePath.StartsWith($resolvedRepoRoot + '\', [StringComparison]::OrdinalIgnoreCase) -and
            [IO.Path]::GetFileName($_.ExecutablePath) -like 'Writing Tools v*.exe' -and
            $_.ExecutablePath -ne $newExePath
        }
)
if ($unexpectedOldProcesses.Count -gt 0) {
    $remaining = ($unexpectedOldProcesses | ForEach-Object { "$($_.Name) (PID $($_.ProcessId))" }) -join ', '
    throw "An older Writing Tools process is still running after launch: $remaining"
}

Write-Host "$ExeName is running."
