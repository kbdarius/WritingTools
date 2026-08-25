# Repository instructions

- `Windows_and_Linux/version.py` is the authoritative Windows/Linux application version.
- Every code change must bump `APP_VERSION` before delivery. Use semantic versioning: patch for fixes, minor for features, and major for incompatible changes.
- Build artifacts must include the version in their filename (`Writing Tools v<version>.exe`).
- For every release, follow the build steps in `docs/build-and-release-windows.md` end-to-end before reporting completion.
- `build-windows.bat` and `Windows_and_Linux/finalize-windows-build.ps1` launch the finished executable automatically. Do not manually launch another copy after the build.
- Before delivery, verify that every older `Writing Tools v*.exe` process is stopped, every older versioned executable is deleted from the repository root, and only the current versioned executable remains.
- If an old process or executable cannot be stopped or deleted, the release is not complete; resolve the Windows lock or report the blocker instead of handing over the build.
- When creating a new release, commit the release changes and push the completed release to the GitHub `main` branch.
- Release checklist: `docs/release-checklist.md`
- Full Windows build and release runbook: `docs/build-and-release-windows.md`
