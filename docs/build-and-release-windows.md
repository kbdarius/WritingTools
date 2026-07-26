# Writing Tools build and release on another Windows PC

This runbook is written for an AI agent or person setting up a fresh Windows machine. Follow the steps in order. Do not move or delete the repository after building unless you are also updating any installed shortcuts or deployment paths.

## Target result

You can double-click `build-windows.bat` from the repository root and get a versioned executable such as `Writing Tools v9.7.0.exe` in the same folder.

## Important constraints

- `Windows_and_Linux/version.py` is the authoritative version file.
- Every release or code change must bump `APP_VERSION` before delivery.
- Build artifacts must include the version in the filename.
- Keep the repository on a permanent local path if you want to rebuild later without updating shortcuts or scripts.
- The Windows build expects Python 3 to be available, ideally with `py -3` or `python` on `PATH`.

## 1. Record the starting state

Before changing anything, record:

- Windows version.
- Whether Python 3 is installed.
- Whether Git is installed.
- Existing repository location, if this checkout already exists.

Verify Python and Git from PowerShell:

```powershell
python --version
git --version
```

If `python` is not found, try:

```powershell
py -3 --version
```

If both checks fail, install Python 3 first and make sure it is available from the command line.

## 2. Clone or update the repository

Use a permanent local directory. For a fresh installation:

```powershell
New-Item -ItemType Directory -Path 'C:\Tools' -Force | Out-Null
Set-Location 'C:\Tools'
git clone https://github.com/kbdarius/WritingTools.git
Set-Location 'C:\Tools\WritingTools'
git switch main
git pull --ff-only origin main
```

For an existing checkout:

```powershell
Set-Location 'C:\Tools\WritingTools'
git status --short
git switch main
git pull --ff-only origin main
```

If `git status --short` reports local changes, do not discard or overwrite them. Report them before continuing.

## 3. Confirm the version before building

Check the current release version:

```powershell
Get-Content .\Windows_and_Linux\version.py
```

The build script names the output using that value. If you are preparing a new release, update `APP_VERSION` first and commit that change before publishing.

## 4. Build the Windows executable

From the repository root, run one of these:

```powershell
.\build-windows.bat
```

or simply double-click `build-windows.bat` in File Explorer.

What the script does:

- Creates or reuses a local build virtual environment under `Windows_and_Linux\.build-venv`.
- Installs the Python requirements from `Windows_and_Linux\requirements.txt`.
- Runs the existing PyInstaller build script.
- Copies the finished executable into the repository root.
- Stops any running `Writing Tools v*.exe` processes from previous releases in this folder, deletes old versioned executables, and launches the newly built executable.

The old executable cleanup and new launch are enforced by:

- `Windows_and_Linux/finalize-windows-build.ps1` (invoked automatically by `build-windows.bat`)
- The step that resolves old `Writing Tools v*.exe` files, stops their processes, removes them, and starts the new build artifact.

If the build succeeds, you should see a file such as:

```text
Writing Tools v9.7.0.exe
```

After build, confirm the new exe is the only versioned executable:

```powershell
Get-ChildItem '.\Writing Tools v*.exe' | Select-Object Name, LastWriteTime
```

If old versions remain, manually terminate them and re-run the finalize script:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Windows_and_Linux\finalize-windows-build.ps1 -RepoRoot . -ExeName (Get-ChildItem .\dist\* -Filter 'Writing Tools v*.exe' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
```

## 5. Verify the output

Confirm the versioned executable exists in the repository root:

```powershell
Get-ChildItem .\Writing Tools v*.exe
```

You can also check the exact versioned filename with:

```powershell
Get-ChildItem .\Writing Tools v*.exe | Select-Object Name, Length, LastWriteTime
```

## 6. Update the release before tagging or publishing

Before you cut a release, make sure the version file reflects the new release number:

```powershell
Get-Content .\Windows_and_Linux\version.py
```

Then commit the release changes and push them to the GitHub `main` branch.

## 7. Troubleshooting decision tree

### `python` is not recognized

1. Install Python 3.
2. Re-open PowerShell so the PATH refreshes.
3. Try `py -3 --version`.
4. Run the build again.

### The build script fails while installing packages

1. Confirm you have an internet connection.
2. Re-run the script from the repository root.
3. If the failure mentions a missing Python package, inspect `Windows_and_Linux\requirements.txt`.

### The executable is not in the repository root

1. Confirm the build completed without errors.
2. Check `Windows_and_Linux\dist\`.
3. Re-run `build-windows.bat`.

### The version in the filename is wrong

1. Open `Windows_and_Linux\version.py`.
2. Confirm `APP_VERSION` was updated before the build.
3. Rebuild after correcting the version.

## 8. Completion report for the AI agent

At the end, report:

- Repository path.
- Current commit (`git rev-parse --short HEAD`).
- Version from `Windows_and_Linux/version.py`.
- Build result.
- Final executable filename.
- Any build warnings or errors.
